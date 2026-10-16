`timescale 1ns/1ps
module auto_apb_tb;
 reg reset=1,cpu=0,isp=0,sof=0,psel=0,penable=0,pwrite=0;
 always #7 cpu=~cpu;always #5 isp=~isp;
 reg [7:0] addr=0;reg [31:0] data=0;wire [31:0] result;wire error,request;
 reg stats_ack=0;reg [156:0] stats=0;
 wire start,read;wire [15:0] regaddr;wire [7:0] regdata;
 reg busy=0,done=0;reg [2:0] rc=0;reg [7:0] rd=0;wire [9:0] r,b;
 camera_auto_apb dut(.reset(reset),.cpu_clk(cpu),.isp_clk(isp),.sof(sof),
  .psel(psel),.penable(penable),.pwrite(pwrite),.paddr(addr),.pwdata(data),.prdata(result),.pslverror(error),
  .stats_request(request),.stats_ack(stats_ack),.stats_held(stats),.rt_start(start),.rt_read(read),
  .rt_address(regaddr),.rt_data(regdata),.rt_busy(busy),.rt_done(done),.rt_result(rc),.rt_read_data(rd),.gain_r(r),.gain_b(b));
 integer commands=0;
 always @(negedge isp)if(start)begin
  commands=commands+1;
  if(!read||regaddr!=16'h3e08||regdata!=8'h81)$fatal(1,"torn runtime command");
 end
 task write;input [7:0] a;input [31:0] d;input rejected;
 begin
  @(negedge cpu);psel=1;penable=0;pwrite=1;addr=a;data=d;
  @(negedge cpu);penable=1;#1;if(error!==rejected)$fatal(1,"APB reject a=%h",a);
  @(negedge cpu);psel=0;penable=0;pwrite=0;
 end endtask
 task frame;
 begin @(negedge isp);sof=1;@(negedge isp);sof=0;repeat(5)@(negedge cpu);end endtask
 initial begin
  repeat(5)@(negedge cpu);reset=0;repeat(5)@(negedge cpu);
  write(8'h08,1,0);write(8'h08,1,1);
  // Result is installed before the source acknowledgement crosses the clocks.
  @(negedge isp);stats={16'hfffe,22'd12345,15'd257,21'd17,13'd64,22'd111,14'd128,21'd20,13'd66};stats_ack=request;
  repeat(5)@(negedge cpu);addr=8'h08;#1;if(result!=32'hfffe)$fatal(1,"frame identity");
  addr=8'h0c;#1;if(result!=12345)$fatal(1,"sum packing");
  write(8'h38,32'h01813e08,0);write(8'h3c,1,0);write(8'h3c,1,1);write(8'h38,0,1);
  repeat(10)@(negedge isp);if(commands!=1)$fatal(1,"command launch count");
  busy=1;repeat(4)@(negedge isp);rc=2;rd=8'hab;done=1;@(negedge isp);done=0;busy=0;
  repeat(5)@(negedge cpu);addr=8'h40;#1;if(result!=32'h2ab)$fatal(1,"NACK response retained");
  write(8'h44,32'h012c0190,0);write(8'h44,32'h01000100,1);
  repeat(10)@(negedge isp);if(r!=256||b!=256)$fatal(1,"WB changed during active frame");
  frame();if(r!=400||b!=300)$fatal(1,"WB pair did not apply together at SOF");
  write(8'h44,32'h02010100,1);write(8'h00,1,1);
  frame();addr=8'h34;#1;if(result!=2)$fatal(1,"frame start counter");
  $display("PASS auto_apb: coherent CDC, single command, NACK, write rejection, frame-safe WB pair");$finish;
 end
 initial begin #100000;$fatal(1,"timeout");end
endmodule
