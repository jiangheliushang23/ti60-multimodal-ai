`timescale 1ns/1ps
module camera_line_bridge_tb;
 reg reset=1,cam_clk=0,clk=0,run_clk=1,vs=0,de=0;reg [31:0] raw=0;
 always #10 cam_clk=~cam_clk;always #5 if(run_clk)clk=~clk;
 wire rv,rd,sof,ev;wire [15:0] pair,seq;wire [16:0] ed;
 wire [31:0] good,bad,period,overflow;
 camera_line_bridge #(.WIDTH(96),.HEIGHT(6)) dut(.reset(reset),.cam_clk(cam_clk),.clk(clk),.vs(vs),.de(de),.raw(raw),
  .vc(2'd0),.dt(6'h2b),.ppc(4'd4),.wc(16'd120),.raw_vs(rv),.raw_de(rd),.raw_pair(pair),
  .sof(sof),.sequence_out(seq),.end_valid(ev),.end_data(ed),.good_frames(good),.bad_frames(bad),.period_ticks(period),.overflow_lines(overflow));
 integer n=0,frames=0,ends=0,i,y;reg checking=1,gaps=0;
 function [7:0] sample;input integer x,y;begin sample=16+x+y*3;end endfunction
 always @(negedge clk)begin
  if(sof)begin n=0;frames=frames+1;end
  if(rd&&checking)begin
   if(pair[7:0]!==sample((n%48)*2,n/48)-8'd16||pair[15:8]!==sample((n%48)*2+1,n/48)-8'd16)
    $fatal(1,"pair mismatch n=%0d pair=%h",n,pair);
   n=n+1;
  end
  if(ev)begin ends=ends+1;if(checking&&!ed[0])$fatal(1,"valid frame rejected");end
 end
 task frame;input integer short_row;
 begin
  @(negedge cam_clk);vs=1;repeat(8)@(negedge cam_clk);
  for(y=0;y<6;y=y+1)begin
   for(i=0;i<(y==short_row?23:24);i=i+1)begin
    de=1;raw={sample(4*i+3,y),sample(4*i+2,y),sample(4*i+1,y),sample(4*i,y)};
    @(negedge cam_clk);
    if(gaps&&i%3==1)begin de=0;repeat(2)@(negedge cam_clk);end
   end
   de=0;repeat(50)@(negedge cam_clk);
  end
  vs=0;repeat(100)@(negedge cam_clk);
 end endtask
 initial begin
  repeat(10)@(negedge cam_clk);reset=0;repeat(30)@(negedge cam_clk);
  frame(-1);if(good!=1||bad!=0||n!=288||ends!=1)$fatal(1,"complete frame counts");
  gaps=1;frame(-1);if(good!=2||frames!=2)$fatal(1,"ring wrap / CSI bubbles");
  checking=0;frame(2);if(bad!=1)$fatal(1,"short row not rejected");
  checking=1;frame(-1);if(good!=3||n!=288)$fatal(1,"short-frame recovery");
  checking=0;@(negedge clk);run_clk=0;frame(-1);if(overflow==0)$fatal(1,"overflow not reported");
  run_clk=1;repeat(1000)@(negedge clk);checking=1;frame(-1);
  if(good!=4||bad!=2||n!=288)$fatal(1,"overflow recovery");
  $display("PASS camera_line_bridge: raw order/BLC, full rows, ring wrap, short frame, overflow and recovery");$finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
