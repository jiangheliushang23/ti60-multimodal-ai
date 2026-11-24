`timescale 1ns/1ps
module camera_live_hdmi_tb;
 reg cpu_clk=0,pixel_clk=0,reset=1,locked=0;
 always #5 cpu_clk=~cpu_clk;
 always #7 pixel_clk=~pixel_clk;
 reg [15:0] address=0;reg select=0,enable=0,write=0;reg [31:0] data=0;
 wire [31:0] read_data;wire error;wire led,led1;
 fusion_sensor_hdmi dut(.low_power_led(led),.low_power_led1(led1),.cpu_clk(cpu_clk),.cpu_reset(reset),.pixel_clk(pixel_clk),.pll_locked(locked),
  .paddr(address),.psel(select),.penable(enable),.pwrite(write),.pwdata(data),.prdata(read_data),.pslverror(error),
  .video_rgb(24'h123456),.video_valid(1'b1),.sht_scl_IN(1'b1),.sht_sda_IN(1'b1),.ir_scl_IN(1'b1),.ir_sda_IN(1'b1));
 task put;input [15:0] addr;input [31:0] value;
 begin
  @(negedge cpu_clk);address=addr;data=value;select=1;enable=1;write=1;
  #1;if(error)$fatal(1,"unexpected APB error");
  @(negedge cpu_clk);select=0;enable=0;write=0;
 end endtask
 integer j,scan,text_column;
 task check_bottom;input [319:0] expected;
 begin
  force dut.v=1016;
  for(text_column=0;text_column<40;text_column=text_column+1)begin
   force dut.h=32+16*text_column;#1;
   if(dut.panel.next_character!==expected[319-text_column*8-:8])
    $fatal(1,"bottom text mismatch column=%0d got=%h expected=%h status=%h",text_column,dut.panel.next_character,expected[319-text_column*8-:8],dut.power_status_frame);
  end
 end endtask
 task thermal_scan;
 begin
  force dut.v=192;
  for(scan=1344;scan<=1366;scan=scan+1)begin
   @(negedge pixel_clk);force dut.h=scan;
   @(posedge pixel_clk);#1;
  end
 end endtask
 task blank;
 begin
  @(negedge pixel_clk);force dut.h=0;force dut.v=1080;
  @(posedge pixel_clk);#1;
  @(negedge pixel_clk);release dut.h;release dut.v;
 end endtask
 initial begin
  #100;reset=0;locked=1;
  repeat(10)@(posedge cpu_clk);
  address=16'h1070;#1;if(read_data!==4)$fatal(1,"display not ready");
  address=16'h1058;#1;if(read_data!==32'h59415539)$fatal(1,"hardware identity");
  if({led1,led}!==2'b00)$fatal(1,"LED must reset off");
  put(16'h1090,1);#1;if({led1,led}!==2'b01)$fatal(1,"LED0 absent or LED1 incorrectly enabled");
  put(16'h1090,0);#1;if({led1,led}!==2'b00)$fatal(1,"normal LED not off");
  put(16'h1078,73);put(16'h1060,3);put(16'h1064,{16'd200,16'd100});put(16'h1068,{16'd600,16'd400});put(16'h106c,1);
  address=16'h1070;#1;if(!read_data[0])$fatal(1,"commit did not become busy");
  // Mode/LED control is independent of a pending or absent YOLO result.
  put(16'h1094,2);address=16'h1094;#1;if(read_data!==2)$fatal(1,"power register readback");
  repeat(10)@(posedge pixel_clk);
  if(dut.shown!==0)$fatal(1,"box changed outside vertical blank");
  blank();repeat(6)@(posedge cpu_clk);#1;
  if(dut.power_mode_frame!==2)$fatal(1,"power mode CDC missing");
  force dut.h=32;force dut.v=1016;#1;
  check_bottom("POWER LOW | YOLO OFF | CAM --.- FPS     ");
  release dut.h;release dut.v;address=16'h1070;#1;
  if(read_data[0]||!read_data[2])$fatal(1,"commit did not acknowledge");
  address=16'h107c;#1;if(read_data!==73)$fatal(1,"shown sequence ACK wrong");
  if(dut.shown!=={32'd73,16'd600,16'd400,16'd200,16'd100,32'd3})$fatal(1,"box metadata torn");
  force dut.h=100;force dut.v=250;#1;if(!dut.border)$fatal(1,"left border absent");
  force dut.h=250;#1;if(dut.border)$fatal(1,"box interior was filled");
  force dut.h=398;#1;if(!dut.border)$fatal(1,"right border absent");
  release dut.h;release dut.v;
  // FPS changes independently while inference/box commits are stopped.
  put(16'h1094,32'h050a);address=16'h1094;#1;
  if(read_data!==32'h050a)$fatal(1,"mode/FPS packed readback");
  repeat(16)@(posedge pixel_clk);
  if(dut.power_status_frame!==2)$fatal(1,"FPS changed outside blank");
  blank();force dut.h=32;force dut.v=1016;#1;
  check_bottom("POWER LOW | YOLO OFF | CAM 05.0 FPS     ");
  release dut.h;release dut.v;
  put(16'h1094,32'h049a);repeat(16)@(posedge pixel_clk);blank();
  force dut.h=32;force dut.v=1016;#1;
  check_bottom("POWER LOW | YOLO OFF | CAM 04.9 FPS     ");
  if(dut.shown[127:96]!==73)$fatal(1,"FPS unexpectedly committed a box");
  release dut.h;release dut.v;
  put(16'h1094,3);repeat(16)@(posedge pixel_clk);blank();
  force dut.h=32;force dut.v=1016;#1;
  check_bottom("POWER WAKING | RESTORING CAMERA 30 FPS  ");
  release dut.h;release dut.v;
  put(16'h1094,4);repeat(16)@(posedge pixel_clk);blank();
  force dut.h=32;force dut.v=1016;#1;
  check_bottom("POWER VERIFY | YOLO CHECKING PERSON     ");
  release dut.h;release dut.v;
  put(16'h1094,0);repeat(16)@(posedge pixel_clk);blank();
  force dut.h=32;force dut.v=1016;#1;
  check_bottom("POWER NORMAL | YOLO ON | CAMERA 30 FPS  ");
  release dut.h;release dut.v;
  put(16'h1060,0);put(16'h106c,1);repeat(10)@(posedge pixel_clk);blank();
  force dut.h=100;force dut.v=250;#1;if(dut.border)$fatal(1,"absent person still displayed");
  release dut.h;release dut.v;repeat(6)@(posedge cpu_clk);
  put(16'h1060,3);put(16'h106c,1);repeat(10)@(posedge pixel_clk);blank();
  repeat(60)blank();
  force dut.h=100;force dut.v=250;#1;if(dut.border)$fatal(1,"stale box not hidden");

  release dut.h;release dut.v;
  repeat(6)@(posedge cpu_clk);
  // Independent thermal and YOLO mailboxes may both be pending until blank.
  for(j=0;j<768;j=j+1)put(16'h6000+j*4,128);
  put(16'h1020,32'h00016001);put(16'h1024,32'h00002500);
  put(16'h1028,32'h00003600);put(16'h102c,32'h00003300);put(16'h1018,1);
  address=16'h1004;#1;if(!read_data[0])$fatal(1,"thermal commit not busy");
  put(16'h1080,32'h0050);put(16'h1084,32'h0175);put(16'h1088,32'h0095);
  put(16'h1078,74);put(16'h1060,3);put(16'h106c,1);
  // Busy sensor RAM rejects writes, without blocking the independent AI mailbox.
  @(negedge cpu_clk);address=16'h6000;select=1;enable=1;write=1;#1;
  if(!error)$fatal(1,"busy heatmap writes were accepted");
  @(negedge cpu_clk);select=0;enable=0;write=0;
  repeat(10)@(posedge pixel_clk);
  if(dut.panel.record_frame[31:0]!==0)$fatal(1,"thermal metadata changed before blank");
  blank();repeat(6)@(posedge cpu_clk);
  address=16'h1004;#1;if(read_data[0])$fatal(1,"thermal ACK missing");
  address=16'h107c;#1;if(read_data!==74)$fatal(1,"AI ACK lost to sensor commit");
  if(dut.panel.record_frame[95:0]!=={32'h3600,32'h2500,32'h00016001})$fatal(1,"thermal metadata torn");
  if(dut.metrics_shown!=={32'h0095,32'h0175,32'h0050})$fatal(1,"display metrics torn");
  thermal_scan();
  if(dut.rgb!==24'h00ff00)$fatal(1,"thermal pixel pipeline/alignment wrong");
  release dut.h;release dut.v;
  // Updating the non-displayed thermal bank cannot disturb the shown heatmap.
  for(j=0;j<768;j=j+1)put(16'h6000+j*4,255);
  thermal_scan();
  if(dut.rgb!==24'h00ff00)$fatal(1,"heatmap changed before atomic swap");
  release dut.h;release dut.v;
  put(16'h1018,1);repeat(10)@(posedge pixel_clk);blank();repeat(6)@(posedge cpu_clk);
  thermal_scan();
  if(dut.rgb!==24'hff0300)$fatal(1,"second thermal bank not displayed");
  force dut.panel.ir_age=300;#1;
  if(dut.panel.ir_ok)$fatal(1,"stale thermal map still valid");
  if(dut.panel.rgb!==24'h142237)$fatal(1,"stale thermal map not blanked");
  release dut.panel.ir_age;release dut.h;release dut.v;
  // CPU SHT snapshot comes from the unchanged cross-clock handshake.
  force dut.sht_snapshot={3'd1,1'b0,20'h02500,20'h05000,16'h6666,16'h7777};
  force dut.sht_sample=1;
  @(posedge cpu_clk);#1;release dut.sht_sample;release dut.sht_snapshot;
  address=16'h2000;#1;if(read_data!==1)$fatal(1,"SHT status missing");
  address=16'h2008;#1;if(read_data!==32'h2500)$fatal(1,"SHT temperature packing");
  address=16'h2010;#1;if(read_data!==32'h5000)$fatal(1,"SHT humidity packing");
  force dut.ready=1;force dut.result=1;force dut.negative=0;
  force dut.t_bcd=20'h02500;force dut.h_bcd=20'h05000;
  @(posedge pixel_clk);#1;release dut.ready;release dut.result;release dut.negative;release dut.t_bcd;release dut.h_bcd;
  blank();#1;
  if(dut.panel.frame_status!==1||dut.panel.frame_t!==20'h02500||dut.panel.frame_h!==20'h05000)$fatal(1,"environment footer update");
  force dut.h=1360;force dut.v=800;#1;
  if(dut.panel.next_character!==8'h43)$fatal(1,"panel text left alignment");
  release dut.h;release dut.v;

  $display("PASS multimodal HDMI: atomic blank-time commit, bounds, empty and stale hide");$finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
