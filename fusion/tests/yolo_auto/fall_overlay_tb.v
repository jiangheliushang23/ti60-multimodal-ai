`timescale 1ns/1ps
module fall_overlay_tb;
 reg cpu_clk=0,pixel_clk=0,reset=1,locked=0;
 always #5 cpu_clk=~cpu_clk;
 always #7 pixel_clk=~pixel_clk;
 reg [15:0] address=0;reg select=0,enable=0,write=0;reg [31:0] data=0;
 wire [31:0] read_data;wire error;
 fusion_sensor_hdmi dut(.cpu_clk(cpu_clk),.cpu_reset(reset),.pixel_clk(pixel_clk),.pll_locked(locked),
  .paddr(address),.psel(select),.penable(enable),.pwrite(write),.pwdata(data),.prdata(read_data),.pslverror(error),
  .video_rgb(24'h123456),.video_valid(1'b1),.sht_scl_IN(1'b1),.sht_sda_IN(1'b1),.ir_scl_IN(1'b1),.ir_sda_IN(1'b1));
 task put;input [15:0] addr;input [31:0] value;
 begin
  @(negedge cpu_clk);address=addr;data=value;select=1;enable=1;write=1;
  #1;if(error)$fatal(1,"unexpected APB error");
  @(negedge cpu_clk);select=0;enable=0;write=0;
 end endtask
 task blank;
 begin
  @(negedge pixel_clk);force dut.h=0;force dut.v=1080;
  @(posedge pixel_clk);#1;@(negedge pixel_clk);release dut.h;release dut.v;
 end endtask
 task color;input [23:0] expected;
 begin
  @(negedge pixel_clk);force dut.h=100;force dut.v=250;
  repeat(6)@(posedge pixel_clk);#1;
  if(dut.rgb!==expected)$fatal(1,"wrong border RGB: got %h expected %h",dut.rgb,expected);
  @(negedge pixel_clk);release dut.h;release dut.v;
 end endtask
 task commit;input [31:0] control;input [31:0] seq;
 begin
  put(16'h1060,control);put(16'h1078,seq);put(16'h106c,1);
  repeat(8)@(posedge pixel_clk);blank();repeat(6)@(posedge cpu_clk);
  address=16'h107c;#1;if(read_data!==seq)$fatal(1,"shown-sequence ACK mismatch");
 end endtask
 initial begin
  #100;reset=0;locked=1;repeat(10)@(posedge cpu_clk);
  put(16'h1064,{16'd200,16'd100});put(16'h1068,{16'd600,16'd400});
  commit(3,1);color(24'h40ff60);
  // The red mailbox must not affect active pixels before a blank-time commit.
  put(16'h1060,7);put(16'h1078,2);put(16'h106c,1);
  repeat(8)@(posedge pixel_clk);color(24'h40ff60);
  blank();repeat(6)@(posedge cpu_clk);color(24'hff4040);
  force dut.h=250;force dut.v=250;repeat(6)@(posedge pixel_clk);#1;
  if(dut.rgb!==24'h123456)$fatal(1,"alarm filled the box instead of coloring its border");
  release dut.h;release dut.v;
  commit(3,3);color(24'h40ff60);
  commit(0,4);color(24'h123456);
  commit(7,5);color(24'hff4040);
  repeat(60)blank();color(24'h123456);
  $display("PASS fall overlay: green, red, blank-time atomic swap, video interior, recovery, no-person clear, stale hide");$finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
