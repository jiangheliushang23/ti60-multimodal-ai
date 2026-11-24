`timescale 1ns/1ps
module dual_person_hdmi_tb;
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
  #1;if(error)$fatal(1,"unexpected APB error addr=%h",addr);
  @(negedge cpu_clk);select=0;enable=0;write=0;
 end endtask
 task blank;
 begin
  @(negedge pixel_clk);force dut.h=0;force dut.v=1080;
  @(posedge pixel_clk);#1;@(negedge pixel_clk);release dut.h;release dut.v;
 end endtask
 task commit;input [31:0] seq;
 begin
  put(16'h1078,seq);put(16'h106c,1);repeat(10)@(posedge pixel_clk);blank();repeat(6)@(posedge cpu_clk);
  address=16'h107c;#1;if(read_data!==seq)$fatal(1,"shared ACK wrong");
 end endtask
 integer xpos,ypos,n;
 task color;input integer x,y;input [23:0] expected;
 begin
  xpos=x;ypos=y;@(negedge pixel_clk);force dut.h=xpos;force dut.v=ypos;
  repeat(6)@(posedge pixel_clk);#1;
  if(dut.rgb!==expected)$fatal(1,"pixel %0d,%0d got %h expected %h",x,y,dut.rgb,expected);
  @(negedge pixel_clk);release dut.h;release dut.v;
 end endtask
 initial begin
  #100;reset=0;locked=1;repeat(10)@(posedge cpu_clk);
  address=16'h1058;#1;if(read_data!==32'h59415539)$fatal(1,"YAU9 identity");
  put(16'h1060,3);put(16'h1064,{16'd200,16'd100});put(16'h1068,{16'd600,16'd400});
  put(16'h1098,1);put(16'h109c,{16'd220,16'd700});put(16'h10a0,{16'd650,16'd1050});
  address=16'h1098;#1;if(read_data!==1)$fatal(1,"second enable readback");
  address=16'h109c;#1;if(read_data!=={16'd220,16'd700})$fatal(1,"second coordinates readback");
  color(100,250,24'h123456);color(700,300,24'h123456);commit(1);
  color(100,250,24'h40ff60);color(700,300,24'h40ff60);
  color(250,300,24'h123456);color(850,300,24'h123456);color(1049,400,24'h40ff60);
  // Both boxes remain unchanged while a new shared commit is pending.
  put(16'h1060,7);put(16'h109c,{16'd220,16'd750});put(16'h1078,2);put(16'h106c,1);
  repeat(8)@(posedge pixel_clk);color(100,250,24'h40ff60);color(700,300,24'h40ff60);
  @(negedge cpu_clk);address=16'h109c;data=0;select=1;enable=1;write=1;
  #1;if(!error)$fatal(1,"second staging write accepted while busy");
  @(negedge cpu_clk);select=0;enable=0;write=0;
  blank();repeat(6)@(posedge cpu_clk);
  color(100,250,24'hff4040);color(700,300,24'h123456);color(750,300,24'h40ff60);
  // Independent colors and real ID glyph pixels share the atomic mailbox.
  put(16'h1060,32'h0000003b); // ID0001, yellow.
  put(16'h1098,32'h00000057); // ID0002, red wins.
  commit(20);color(100,250,24'hffe040);color(750,300,24'hff4040);
  // Top stroke of I, and a blank gap, for both labels.
  color(106,204,24'hffe040);color(104,204,24'h123456);
  color(756,224,24'hff4040);color(754,224,24'h123456);
  // Last digit: 1 has no top bar, 2 has a top bar.
  color(190,204,24'h123456);color(840,224,24'hff4040);
  put(16'h1060,32'h0000003f); // Both alarm/warning bits: must render red.
  put(16'h1098,32'h0000005b); // Second is yellow, with a different ID.
  commit(21);color(100,250,24'hff4040);color(750,300,24'hffe040);
  color(106,204,24'hff4040);color(756,224,24'hffe040);
  // Boundary is camera x=960 + screen offset32, confined to the video.
  color(992,248,24'hffe040);color(992,256,24'h123456);
  put(16'h1098,1);commit(22);
  // Clearing one person must leave the other visible, without red leakage.
  put(16'h1060,0);commit(3);color(100,250,24'h123456);color(750,300,24'h40ff60);
  if(!dut.panel.person_present)$fatal(1,"second-only person missing from panel");
  put(16'h1098,0);commit(4);color(750,300,24'h123456);
  if(dut.panel.person_present)$fatal(1,"empty scene still reports a person");
  // Malformed bounds never draw outside the camera window.
  put(16'h1098,1);put(16'h109c,{16'd100,16'd0});commit(5);color(0,300,24'h0b1220);
  color(750,300,24'h123456);
  put(16'h109c,{16'd220,16'd750});commit(6);
  for(n=0;n<60;n=n+1)blank();color(750,300,24'h123456);
  if(dut.panel.person_live)$fatal(1,"stale person still live");
  $display("PASS dual-person HDMI: two independent borders, video interiors, shared atomic ACK, busy rejection, independent clear, stale hide, per-ID glyphs, independent red/yellow/green, red priority, video-only danger boundary");$finish;
 end
 initial begin #1500000;$fatal(1,"dual overlay timeout");end
endmodule
