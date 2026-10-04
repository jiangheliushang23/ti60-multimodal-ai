`timescale 1ns/1ps
module thermal_page_tb;
 reg clk=0,cpu_clk=0,reset=1;always #5 clk=~clk;always #7 cpu_clk=~cpu_clk;
 reg ready=0,negative=0,cpu_request=0,cpu_trap=0,image_we=0;
 reg [2:0] result=1;reg [19:0] t_bcd=20'h02868,h_bcd=20'h06908;
 reg [10:0] image_address=0;reg [7:0] image_data=0;reg [447:0] cpu_record=0;
 wire display_ack,hs,vs,de;wire [23:0] rgb;
 thermal_page #(.STALE_CYCLES(12000000),.IR_STALE_CYCLES(4000000)) dut(.*);
 integer i,good_file,error_file,frame=0,cycle=0,active=0,hsc=0,vsc=0,x,y;reg started=0;
 function [23:0] expected_color;
 input [7:0] n;reg [7:0] t;begin t={n[5:0],2'b00};
 case(n[7:6])0:expected_color={8'd0,t,8'd255};1:expected_color={8'd0,8'd255,8'd255-t};
 2:expected_color={t,8'd255,8'd0};3:expected_color={8'd255,8'd255-t,8'd0};endcase end endfunction
 function [23:0] matrix_color;
 input integer px,py;
 integer hx,hy,cx,cy;begin
  // Hotspot at col=31,row=0 checks the last matrix column.
  hx=px-1136;if(hx<0)hx=-hx;hy=py-208;if(hy<0)hy=-hy;
  cx=px-656;if(cx<0)cx=-cx;cy=py-592;if(cy<0)cy=-cy;
  if((hx<=1&&hy<=11)||(hy<=1&&hx<=11))matrix_color=24'hffffff;
  else if((hx<=3&&hy<=13)||(hy<=3&&hx<=13))matrix_color=0;
  else if((cx<=1&&cy<=9)||(cy<=1&&cx<=9))matrix_color=24'h00ffff;
  else if((cx<=3&&cy<=11)||(cy<=3&&cx<=11))matrix_color=0;
  else matrix_color=expected_color(((px-128)/32)*8);
 end endfunction
 initial begin
  good_file=$fopen("validation/thermal_page.ppm","wb");$fwrite(good_file,"P6\n960 540\n255\n");
  error_file=$fopen("validation/thermal_error.ppm","wb");$fwrite(error_file,"P6\n960 540\n255\n");
  repeat(10)@(negedge clk);reset=0;ready=1;@(negedge clk);ready=0;
  for(i=0;i<768;i=i+1)begin
   @(negedge cpu_clk);image_we=1;image_address=1024+i;image_data=(i%32)*8;
  end
  @(negedge cpu_clk);image_we=0;
  cpu_record={32'h0250,32'h0100,32'h0042,32'd1,32'd31,32'h00003500,32'h00002600,32'd3,32'h00000032,32'h00002500,32'h00003100,32'h00003446,32'h00002661,32'd1};
  cpu_request=1;
  wait(display_ack==1);#1;
  if(dut.v!=1080 || dut.h!=1 || dut.ir_status!=1)$fatal(1,"Bad initial frame commit");
  if(dut.record_frame!==cpu_record)$fatal(1,"Extended metadata torn or truncated");
  wait(dut.v==500&&dut.h==100);@(negedge cpu_clk);
  cpu_record[31:0]=2;cpu_record[319:224]=0;cpu_request=0;
  repeat(10)@(negedge clk);
  if(display_ack!=1||dut.ir_status!=1||dut.record_frame[319:288]!=31||dut.record_frame[255:224]!=32'h2600)$fatal(1,"Mid-frame image/metadata tear");
  wait(display_ack==0);#1;
  if(dut.ir_status!=2)$fatal(1,"Error record not committed");
  wait(dut.ir_status==9);
  cpu_trap=1;repeat(5)@(negedge clk);if(dut.ir_status!=10)$fatal(1,"CPU trap not shown");
  $fclose(good_file);$fclose(error_file);
  $display("PASS 1080p timing, exact matrix and hotspot/center markers, dual-clock bank handoff, 14-word atomic record and performance fields, error blanking, stale/trap");$finish;
 end
 always @(negedge clk)if(!reset)begin
  if(!started&&de)begin started=1;cycle=0;end
  if(started)begin
   if(cycle==2475000)begin
    if(active!=2073600||hsc!=49500||vsc!=11000)$fatal(1,"1080p totals");
    cycle=0;active=0;hsc=0;vsc=0;frame=frame+1;
   end
   if(de)begin
    x=cycle%2200;y=cycle/2200;active=active+1;
    if(x>=1920||y>=1080)$fatal(1,"DE alignment");
    if(x>=128&&x<1152&&y>=192&&y<960)begin
     if(frame==1 && rgb!==matrix_color(x,y))$fatal(1,"Pixel mismatch x=%d y=%d rgb=%h",x,y,rgb);
     if(frame==2 && rgb!==24'h142237)$fatal(1,"Error image was not blanked");
    end
    if(x%2==0&&y%2==0)begin
     if(frame==1)$fwrite(good_file,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
     if(frame==2)$fwrite(error_file,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
    end
   end else if(rgb!=0)$fatal(1,"RGB outside active frame");
   if(hs)hsc=hsc+1;if(vs)vsc=vsc+1;cycle=cycle+1;
  end
 end
 initial begin #110000000;$fatal(1,"Page timeout");end
endmodule
