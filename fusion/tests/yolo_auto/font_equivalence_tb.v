`timescale 1ns/1ps
module font_equivalence_tb;
 reg [7:0] character;reg [2:0] row;
 wire [7:0] current_bits,original_bits;
 sht30_font current_font(character,row,current_bits);
 font_reference original_font(character,row,original_bits);
 integer i,j;
 initial begin
  for(i=0;i<256;i=i+1)for(j=0;j<8;j=j+1)begin
   character=i;row=j;#1;
   if(current_bits!==original_bits)$fatal(1,"font differs character=%d row=%d",i,j);
  end
  $display("PASS font equivalence: all 2048 input combinations");$finish;
 end
endmodule
