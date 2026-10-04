`timescale 1ns/1ps
module camera_rgb_pack_tb;
 reg clk=0,reset=1,vs=0,de=0;reg [47:0] rgb=0;
 always #5 clk=~clk;
 wire valid,complete,bad;wire [127:0] data;
 camera_rgb_pack #(.WIDTH(96),.HEIGHT(6)) dut(.clk(clk),.reset(reset),.vs(vs),.de(de),.rgb(rgb),.valid(valid),.data(data),.complete(complete),.malformed(bad));
 function [23:0] color;input integer x,y;begin color={8'(x+2*y),8'(2*x+y),8'(x+4*y)};end endfunction
 function [15:0] expected;input integer x,y;reg [23:0] c;begin c=color((x*3)/2,(y*3)/2);expected={c[7:3],c[15:10],c[23:19]};end endfunction
 integer beats=0,k,x,y;reg checking=1;
 always @(negedge clk)if(valid&&checking)begin
  for(k=0;k<8;k=k+1)if(data[k*16+:16]!==expected((beats*8+k)%64,(beats*8+k)/64))
   $fatal(1,"scale/order beat=%0d pixel=%0d got=%h exp=%h",beats,k,data[k*16+:16],expected((beats*8+k)%64,(beats*8+k)/64));
  beats=beats+1;
 end
 initial begin
  repeat(5)@(negedge clk);reset=0;vs=1;repeat(5)@(negedge clk);vs=0;
  for(y=0;y<6;y=y+1)begin
   for(x=0;x<96;x=x+2)begin de=1;rgb={color(x+1,y),color(x,y)};@(negedge clk);end
   de=0;repeat(10)@(negedge clk);
  end
  if(beats!=32||!complete||bad)$fatal(1,"frame accounting beats=%0d",beats);
  checking=0;vs=1;@(negedge clk);vs=0;de=1;repeat(17)@(negedge clk);de=0;repeat(5)@(negedge clk);
  if(!bad)$fatal(1,"short line accepted");
  $display("PASS camera_rgb_pack: all pixels versus independent coordinate reference, short-line rejection");$finish;
 end
endmodule
