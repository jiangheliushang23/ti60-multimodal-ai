`timescale 1ns/1ps
module compact_stats_tb;
 reg clk=0,reset=1,vs=0,de=0,format_ok=1,first=0,good_end=0,request=0;
 always #10 clk=~clk;
 reg [31:0] pixels;reg [9:0] x=0;reg [10:0] y=0;reg [15:0] seq=0;
 wire ack;wire [156:0] held;wire [383:0] ref_values;wire toggle;
 camera_auto_stats dut(.clk(clk),.reset(reset),.first(first),.pixel(vs&&de),
  .format_ok(format_ok),.good_end(good_end),.group_x(x),.row_y(y),.frame_seq(seq),
  .pixels(pixels[15:0]),.request(request),.acknowledge(ack),.held(held));
 sc_auto_stats reference(.clk(clk),.reset(reset),.vs(vs),.de(de),.format_ok(format_ok),
  .pixels(pixels),.values(ref_values),.frame_toggle(toggle));
 integer c,row,col;reg [156:0] prior;
 function [7:0] value;input integer column,row,pattern;
 begin case(pattern)
  0:value=(column*37+row*19)%240;
  1:value=0;
  2:value=239;
  3:value=(row%2==0)?(column%2==0?48:60):(column%2==0?60:30);
  default:value=(column+row)%2?232:4;
 endcase end endfunction
 task frame;input integer pattern,broken;
 begin
  seq=seq+1;vs=1;first=1;de=0;@(negedge clk);first=0;
  for(row=0;row<1080;row=row+1)begin
   for(col=0;col<480;col=col+1)begin
    x=col;y=row;de=1;format_ok=!(broken&&row==500&&col==200);
    pixels={value(col*4+3,row,pattern),value(col*4+2,row,pattern),value(col*4+1,row,pattern),value(col*4,row,pattern)};
    @(negedge clk);
    if(col%7==4)begin de=0;@(negedge clk);end
   end
   de=0;@(negedge clk);
  end
  vs=0;de=0;good_end=!broken;@(negedge clk);good_end=0;
  repeat(4)@(negedge clk);
 end endtask
 task compare;
 begin
  if(ack!==request)$fatal(1,"mailbox missing acknowledgement");
  if(held[156:141]!=seq||held[140:119]!=ref_values[319:288]||
   held[118:104]!=ref_values[255:224]||held[103:83]!=ref_values[191:160]||
   held[82:70]!=ref_values[159:128]||held[69:48]!=ref_values[127:96]||
   held[47:34]!=ref_values[95:64]||held[33:13]!=ref_values[63:32]||held[12:0]!=ref_values[31:0])
   $fatal(1,"compact/reference mismatch pattern=%d held=%h ref=%h",c,held,ref_values);
  if(ref_values[287:256]!=16320||ref_values[223:192]!=32640)$fatal(1,"sampling constant mismatch");
 end endtask
 initial begin
  pixels=0;repeat(4)@(negedge clk);reset=0;repeat(4)@(negedge clk);
  for(c=0;c<5;c=c+1)begin request=~request;repeat(4)@(negedge clk);frame(c,0);compare();end
  prior=held;request=~request;repeat(4)@(negedge clk);frame(0,1);
  if(ack===request)$fatal(1,"malformed frame acknowledged");
  frame(3,0);compare();
  prior=held;frame(2,0);if(held!==prior)$fatal(1,"unrequested frame changed held result");
  fork
   begin repeat(100)@(negedge clk);request=~request;end
   frame(0,0);
  join
  if(ack===request||held!==prior)$fatal(1,"mid-frame request published a partial frame");
  frame(3,0);compare();
  $display("PASS compact_stats: 1080p reference equivalence, DE holes, black/clip/color, bad frame discard, held frame identity");$finish;
 end
 initial begin #200000000;$fatal(1,"timeout");end
endmodule
