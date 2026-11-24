`timescale 1ns/1ps
module multimodal_sht_values_tb;
 reg clk=0,reset=1,sample=0;always #5 clk=~clk;
 reg [2:0] status=1;reg [15:0] raw_t=0,raw_h=0;
 wire ready,negative;wire [2:0] result;wire [19:0] t_bcd,h_bcd;
 sht30_values dut(.*);
 function integer decimal;input [19:0] b;integer k;begin
  decimal=0;for(k=4;k>=0;k=k-1)begin
   if(b[k*4+:4]>9)$fatal(1,"invalid BCD digit");decimal=decimal*10+b[k*4+:4];
  end
 end endfunction
 integer n,t,h,timeout;
 initial begin
  repeat(3)@(negedge clk);reset=0;
  for(n=0;n<65536;n=n+1)begin
   raw_t=n;raw_h=65535-n;sample=1;@(negedge clk);sample=0;timeout=0;
   while(!ready&&timeout<45)begin @(negedge clk);timeout=timeout+1;end
   if(!ready||result!=1)$fatal(1,"conversion did not finish");
   t=(n*17500+32767)/65535-4500;h=((65535-n)*10000+32767)/65535;
   if((negative?-decimal(t_bcd):decimal(t_bcd))!=t||decimal(h_bcd)!=h)
    $fatal(1,"rounded value changed at raw=%d",n);
   @(negedge clk);
  end
  status=3;sample=1;@(negedge clk);sample=0;
  if(!ready||result!=3)$fatal(1,"CRC/error status was not preserved");
  $display("PASS SHT exact conversion: all 65536 raw codes, rounding, signed temperature, humidity, errors");$finish;
 end
 initial begin #30000000;$fatal(1,"timeout");end
endmodule
