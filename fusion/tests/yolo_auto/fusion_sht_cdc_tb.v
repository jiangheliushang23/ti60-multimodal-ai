`timescale 1ns/1ps
module fusion_sht_cdc_tb;
 reg pixel_clk=0,cpu_clk=0,pixel_reset=1,cpu_reset=1,ready=0;
 always #3.367 pixel_clk=~pixel_clk;always #5 cpu_clk=~cpu_clk;
 reg [2:0] result=0;reg negative=0;reg [15:0] raw_t=0,raw_h=0;reg [19:0] t_bcd=0,h_bcd=0;
 wire sample;wire [75:0] snapshot;
 fusion_sht_cdc dut(.*);
 reg [75:0] expected;integer count=0,k;
 always @(negedge cpu_clk)if(sample)begin
  if(snapshot!==expected)$fatal(1,"torn SHT snapshot");count=count+1;
 end
 initial begin
  repeat(10)@(negedge pixel_clk);pixel_reset=0;cpu_reset=0;
  for(k=0;k<20;k=k+1)begin
   @(negedge pixel_clk);result=k%6;negative=k%2;raw_t=100+k;raw_h=200+k;t_bcd=300+k;h_bcd=400+k;
   expected={result,negative,t_bcd,h_bcd,raw_t,raw_h};ready=1;
   @(negedge pixel_clk);ready=0;result=7;raw_t=0;raw_h=0;t_bcd=0;h_bcd=0;
   repeat(20)@(negedge pixel_clk);
   if(count!=k+1)$fatal(1,"missing/duplicate sample");
  end
  pixel_reset=1;cpu_reset=1;repeat(10)@(negedge pixel_clk);pixel_reset=0;cpu_reset=0;
  repeat(20)@(negedge cpu_clk);if(count!=20||snapshot!=0)$fatal(1,"reset phantom sample");
  $display("PASS SHT CDC: 20 asynchronous full samples, held data, one pulse, reset");$finish;
 end
 initial begin #100000;$fatal(1,"CDC timeout");end
endmodule
