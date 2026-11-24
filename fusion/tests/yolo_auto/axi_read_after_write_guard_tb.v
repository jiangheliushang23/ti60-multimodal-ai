`timescale 1ns/1ps
module axi_read_after_write_guard_tb;
    reg clk=0, reset=1;
    always #5 clk=~clk;
    reg awvalid=0, awready=1, bvalid=0, bready=1;
    reg cpu_arvalid=0, mem_arready=1;
    wire cpu_arready, mem_arvalid;
    axi_read_after_write_guard dut(.*);
    reg [2:0] multi_awvalid=0;
    wire [2:0] multi_awready=3'b111;
    reg ddr_bvalid=0,multi_arvalid=0;
    wire multi_arready,multi_mem_arvalid;
    integer burst;
    axi_read_after_write_guard #(.WRITERS(3)) multi_dut(
        .clk(clk),.reset(reset),.awvalid(multi_awvalid),.awready(multi_awready),
        .bvalid(ddr_bvalid),.bready(1'b1),.cpu_arvalid(multi_arvalid),
        .cpu_arready(multi_arready),.mem_arvalid(multi_mem_arvalid),.mem_arready(1'b1));
    task tick; begin @(posedge clk); #1; end endtask
    task check_blocked;
        begin
            if (mem_arvalid || cpu_arready) $fatal(1,"Read passed pending write");
        end
    endtask
    initial begin
        tick; @(negedge clk); reset=0;
        // Simultaneous store and subsequent load, with a delayed B response.
        awvalid=1; cpu_arvalid=1; #1; check_blocked;
        tick; @(negedge clk); awvalid=0;
        repeat(4) begin tick; check_blocked; end
        @(negedge clk); bvalid=1; bready=0;
        tick; check_blocked; // BVALID alone does not retire the write.
        @(negedge clk); bready=1;
        tick;
        if (!mem_arvalid || !cpu_arready) $fatal(1,"Read did not resume after B");
        @(negedge clk); bvalid=0; cpu_arvalid=0;
        // Two writes: one B response cannot release a following read.
        awvalid=1; tick; tick;
        @(negedge clk); awvalid=0; cpu_arvalid=1; bvalid=1;
        tick; check_blocked;
        @(negedge clk); awvalid=1; // retire one, accept one: still one pending.
        tick; check_blocked;
        @(negedge clk); awvalid=0;
        tick;
        if (!mem_arvalid) $fatal(1,"Multiple-write drain failed");
        @(negedge clk); bvalid=0; cpu_arvalid=0; tick;
        // Preserve an already-offered ARVALID if a newer write arrives while
        // the memory slave stalls. Payload remains untouched by this module.
        @(negedge clk); cpu_arvalid=1; mem_arready=0;
        tick;
        if (!mem_arvalid) $fatal(1,"Read not offered");
        @(negedge clk); awvalid=1;
        tick;
        if (!mem_arvalid) $fatal(1,"ARVALID withdrawn under backpressure");
        @(negedge clk); awvalid=0; mem_arready=1;
        if (!mem_arvalid) $fatal(1,"Earlier read lost");
        tick; check_blocked; // A second read now waits for the newer write.
        @(negedge clk); bvalid=1;
        tick;
        if (!mem_arvalid) $fatal(1,"Read did not resume");
        @(negedge clk); reset=1;
        tick;
        if (dut.pending_writes !== 0 || dut.read_offered !== 0)
            $fatal(1,"Reset failed");
        @(negedge clk); reset=0;multi_awvalid=3'b111;multi_arvalid=1;
        tick;
        if(multi_dut.pending_writes!==3 || multi_mem_arvalid) $fatal(1,"Three masters not counted");
        @(negedge clk);multi_awvalid=0;
        // Local FIFO acknowledgement is deliberately not a retirement event.
        // Reads must stay blocked until the DDR-side B handshakes arrive.
        repeat(10) begin tick;if(multi_mem_arvalid) $fatal(1,"Posted write released read");end
        @(negedge clk);ddr_bvalid=1;
        tick;if(multi_mem_arvalid) $fatal(1,"Two DDR writes remain");
        @(negedge clk);multi_awvalid=3'b111;
        tick;if(multi_dut.pending_writes!==4) $fatal(1,"Concurrent three AW and one B");
        @(negedge clk);multi_awvalid=0;
        repeat(3) begin tick;if(multi_mem_arvalid) $fatal(1,"DDR completion drain early");end
        tick;if(!multi_mem_arvalid) $fatal(1,"DDR completion drain blocked");
        @(negedge clk);ddr_bvalid=0;multi_arvalid=0;tick;
        // A posted-write FIFO may hold more than 255 short transactions.
        @(negedge clk);multi_awvalid=3'b001;multi_arvalid=1;
        repeat(260) tick;
        if(multi_dut.pending_writes!==260) $fatal(1,"Posted-write counter overflow");
        @(negedge clk);multi_awvalid=0;ddr_bvalid=1;
        for(burst=0;burst<259;burst=burst+1) begin
            tick;if(multi_mem_arvalid) $fatal(1,"Long posted queue drain early");
        end
        tick;if(!multi_mem_arvalid) $fatal(1,"Long posted queue drain failed");
        $display("PASS axi_read_after_write_guard: delayed DDR B, three masters, 260 posted writes, concurrent completion, ARVALID stability");
        $finish;
    end
    initial begin #10000; $fatal(1,"Timeout"); end
endmodule
