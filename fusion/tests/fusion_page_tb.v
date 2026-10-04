`timescale 1ns/1ps
module fusion_page_tb;
 reg clk=0,cpu_clk=0,reset=1,ready=0,request=0,image_we=0;
 always #3.367 clk=~clk;always #5 cpu_clk=~cpu_clk;
 reg [10:0] address=0;reg [7:0] image_data=0;reg [447:0] record=0;
 wire ack,fr,take;wire [2:0] pi;wire hs,vs,de;wire [23:0] rgb;
 wire [23:0] camera_rgb={dut.h,dut.v};
 fusion_page dut(.clk(clk),.reset(reset),.ready(ready),.result(3'd1),.negative(1'b0),.t_bcd(20'h02500),.h_bcd(20'h05000),
  .cpu_clk(cpu_clk),.cpu_request(request),.image_we(image_we),.image_address(address),.image_data(image_data),
  .cpu_record(record),.display_ack(ack),.video_rgb(camera_rgb),.video_valid(1'b1),
  .frame_request(fr),.video_take(take),.pixel_index(pi),.hs(hs),.vs(vs),.de(de),.rgb(rgb));
 integer hx[0:2],vy[0:2],i,checked=0,videos=0,heats=0;reg enabled=0;integer ppm;
 function [23:0] palette;input [7:0] n;reg [7:0] f;begin f={n[5:0],2'b0};case(n[7:6])
  0:palette={8'd0,f,8'd255};1:palette={8'd0,8'd255,8'd255-f};
  2:palette={f,8'd255,8'd0};3:palette={8'd255,8'd255-f,8'd0};endcase end endfunction
 always @(posedge clk)begin
  hx[2]=hx[1];hx[1]=hx[0];hx[0]=dut.h;vy[2]=vy[1];vy[1]=vy[0];vy[0]=dut.v;
  #1;
  if(enabled)begin
   if(de!==(hx[2]<1920&&vy[2]<1080)||hs!==(hx[2]>=2008&&hx[2]<2052)||vs!==(vy[2]>=1084&&vy[2]<1089))$fatal(1,"scan alignment");
   if(hx[2]>=32&&hx[2]<1312&&vy[2]>=144&&vy[2]<864)begin
    if(rgb!=={12'(hx[2]),12'(vy[2])})$fatal(1,"video offset %d %d rgb=%h",hx[2],vy[2],rgb);videos=videos+1;
   end
   if(hx[2]>=1360&&hx[2]<1872&&vy[2]>=192&&vy[2]<576)begin
    if(rgb!==palette(8'((((vy[2]-192)/16)*32+(hx[2]-1360)/16))))$fatal(1,"heat coordinate");heats=heats+1;
   end
   if(de)$fwrite(ppm,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
   checked=checked+1;
   if(checked==2200*1125)begin
    $fclose(ppm);
    if(videos!=1280*720||heats!=512*384)$fatal(1,"window dimensions");
    $display("PASS fusion_page: full 1080p60 timing, all video/thermal pixels, atomic blanking commit");$finish;
   end
  end
 end
 initial begin
  ppm=$fopen("validation/fusion_page_simulation.ppm","wb");$fwrite(ppm,"P6\n1920 1080\n255\n");
  repeat(8)@(negedge clk);reset=0;ready=1;@(negedge clk);ready=0;
  for(i=0;i<768;i=i+1)begin @(negedge cpu_clk);image_we=1;address=1024+i;image_data=i;end
  @(negedge cpu_clk);image_we=0;record[31:0]=1;record[63:32]=32'h02500;record[95:64]=32'h03000;record[127:96]=32'h02700;request=1;
  wait(ack);if(dut.v!=1080)$fatal(1,"torn commit");
  wait(dut.h==2199&&dut.v==1124);repeat(3)@(negedge clk);enabled=1;
 end
 initial begin #35000000;$fatal(1,"page timeout");end
endmodule
