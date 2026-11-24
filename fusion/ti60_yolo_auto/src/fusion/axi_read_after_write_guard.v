// Order CPU DDR reads after accepted writes have completed at the DDR slave.
// The legacy interconnect acknowledges upstream writes from local FIFOs; its
// local bus has no downstream B-response return channel. Observe ALL upstream
// AW handshakes and the real DDR B response, never a posted upstream response.
// All ports use the same 128-bit width, hence one downstream burst per input AW.
module axi_read_after_write_guard #(parameter WRITERS=1)(
    input wire clk,
    input wire reset,
    input wire [WRITERS-1:0] awvalid,
    input wire [WRITERS-1:0] awready,
    input wire bvalid,
    input wire bready,
    input wire cpu_arvalid,
    output wire cpu_arready,
    output wire mem_arvalid,
    input wire mem_arready
);
    // Covers all three masters' bounded queues, including short posted bursts.
    reg [15:0] pending_writes;
    reg read_offered;
    reg [15:0] writes_accepted;
    integer writer;
    always @* begin
        writes_accepted=0;
        for(writer=0;writer<WRITERS;writer=writer+1)
            writes_accepted=writes_accepted+(awvalid[writer]&&awready[writer]);
    end
    wire write_completed = bvalid && bready;
    wire read_allowed = read_offered || (pending_writes == 0 && !(|awvalid));
    assign mem_arvalid = cpu_arvalid && read_allowed;
    assign cpu_arready = mem_arready && read_allowed;

    always @(posedge clk or posedge reset) begin
        if (reset) begin
            pending_writes <= 0;
            read_offered <= 0;
        end else begin
            if(writes_accepted!=0 || write_completed)
                pending_writes<=pending_writes+writes_accepted-
                    ((write_completed&&(pending_writes!=0||writes_accepted!=0))?16'd1:16'd0);
            // Once ARVALID is offered, preserve it through backpressure. A
            // write arriving later must not withdraw an earlier read offer.
            if (mem_arvalid)
                read_offered <= !mem_arready;
        end
    end
endmodule
