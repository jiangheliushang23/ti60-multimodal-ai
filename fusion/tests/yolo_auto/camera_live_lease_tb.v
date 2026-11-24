`timescale 1ns/1ps
module camera_live_lease_tb;
 reg mem_clk=0,cpu_clk=0,reset=1;always #5 mem_clk=~mem_clk;always #7 cpu_clk=~cpu_clk;
 reg [1:0] bank=1;reg valid=1;reg [15:0] seq=65535;reg [31:0] count=70000;reg [31:0] timestamp=12345;
 reg [15:0] addr=0;reg sel=0,enable=0,write=0;reg [31:0] data=0;
 wire pinned;wire [1:0] held;wire [31:0] readback;wire error;
 video_frame_lease #(.MAX_HOLD_CYCLES(500)) dut(.mem_clk(mem_clk),.cpu_clk(cpu_clk),.reset(reset),
 .latest_bank(bank),.latest_valid(valid),.latest_seq(seq),.latest_count(count),.latest_time_ms(timestamp),.pinned_valid(pinned),.pinned_bank(held),
 .paddr(addr),.psel(sel),.penable(enable),.pwrite(write),.pwdata(data),.prdata(readback),.pslverror(error));
 task request;input value;begin
  @(negedge cpu_clk);addr=16'h5104;data=value;sel=1;enable=1;write=1;
  @(negedge cpu_clk);sel=0;enable=0;write=0;repeat(12)@(negedge cpu_clk);
 end endtask
 initial begin
  repeat(8)@(negedge cpu_clk);reset=0;repeat(4)@(negedge cpu_clk);
  addr=16'h5100;#1;if(readback!=32'h59465233)$fatal(1,"signature");
  request(1);addr=16'h5108;#1;if(readback[1:0]!=3||!pinned||held!=1)$fatal(1,"pin handshake");
  bank=2;seq=0;count=70001;timestamp=12456;repeat(25)@(negedge cpu_clk);
  addr=16'h510c;#1;if(readback!=32'h06200000)$fatal(1,"unstable bank");
  addr=16'h5110;#1;if(readback!=65535)$fatal(1,"unstable sequence");
  addr=16'h5128;#1;if(readback!=70000)$fatal(1,"pinned publication count changed");
  addr=16'h512c;#1;if(readback!=12345)$fatal(1,"pinned timestamp changed with latest frame");
  addr=16'h5124;#1;if(readback!=70001)$fatal(1,"latest count CDC wrong");
  request(0);if(pinned)$fatal(1,"release handshake");
  request(1);if(!pinned||held!=2)$fatal(1,"new pin");
  addr=16'h5128;#1;if(readback!=70001)$fatal(1,"publication count did not advance across seq wrap");
  addr=16'h512c;#1;if(readback!=12456)$fatal(1,"new timestamp missing");
  repeat(550)@(negedge mem_clk);repeat(8)@(negedge cpu_clk);
  addr=16'h5108;#1;if(readback[1]||pinned)$fatal(1,"lease timeout");
  request(0);valid=0;request(1);addr=16'h5108;#1;if(readback[1:0]!=1)$fatal(1,"invalid latest pinned");
  addr=16'h5100;sel=1;enable=1;write=1;#1;if(!error)$fatal(1,"invalid write accepted");
  $display("PASS yolo DDR lease: coherent metadata, release, timeout and invalid frames");$finish;
 end
 initial begin #30000;$fatal(1,"timeout");end
endmodule
