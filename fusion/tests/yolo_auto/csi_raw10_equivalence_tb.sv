`timescale 1ns/1ps
module csi_raw10_equivalence_tb;
 reg bc=0,pc=0,reset_n=0;
 always #7 bc=~bc;
 always #5 pc=~pc;
 reg [15:0] hs=0,vs=0;
 reg [15:0] word_count=1600;
 reg [63:0] payload=0;
 reg valid=0,header=0;
 wire [63:0] pixel[0:1];wire [1:0] pixel_valid;
 wire [15:0] ho[0:1],vo[0:1];
 integer seen=0,lines=0;
 genvar g;
 generate for(g=0;g<2;g=g+1)begin:core
  efx_csi2_byte2pixel #(.PACK_TYPE(g==0?15:1),.PIXEL_FIFO_DEPTH(4096)) dut(
   .clk_byte_HS(bc),.reset_byte_HS_n(reset_n),.clk_pixel(pc),.reset_pixel_n(reset_n),
   .hsync_vc_int(hs),.vsync_vc_int(vs),.word_count(word_count),.datatype(6'h2b),.vc(2'd0),.vcx(2'd0),
   .pkt_data(payload),.valid_pkt_data(valid),.odd_line(lines[0]),
   .RAW6_r(1'b0),.RAW7_r(1'b0),.RAW8_r(1'b0),.RAW10_r(1'b1),.RAW12_r(1'b0),.RAW14_r(1'b0),
   .RAW16_r(1'b0),.RAW20_r(1'b0),.RAW24_r(1'b0),.RAW28_r(1'b0),
   .RGB444_r(1'b0),.RGB555_r(1'b0),.RGB565_r(1'b0),.RGB888_r(1'b0),
   .YUV_422_8_r(1'b0),.YUV_422_10_r(1'b0),.YUV_420_8_legacy_r(1'b0),.YUV_420_8_r(1'b0),.YUV_420_10_r(1'b0),
   .gen_long_pkt_r(1'b0),.user_define_8bit_r(1'b0),.embed_8bit_nonvideo_r(1'b0),
   .vld_pkt_header_reg(header),.short_pkt_type(1'b0),.trigger_extra_pixel(),.extra_pixel_count(),.fifo_full(),.fifo_empty(),
   .pixel_data(pixel[g]),.pixel_data_valid(pixel_valid[g]),
   .hsync_vc0_sync(ho[g][0]),.hsync_vc1_sync(ho[g][1]),.hsync_vc2_sync(ho[g][2]),.hsync_vc3_sync(ho[g][3]),
   .hsync_vc4_sync(ho[g][4]),.hsync_vc5_sync(ho[g][5]),.hsync_vc6_sync(ho[g][6]),.hsync_vc7_sync(ho[g][7]),
   .hsync_vc8_sync(ho[g][8]),.hsync_vc9_sync(ho[g][9]),.hsync_vc10_sync(ho[g][10]),.hsync_vc11_sync(ho[g][11]),
   .hsync_vc12_sync(ho[g][12]),.hsync_vc13_sync(ho[g][13]),.hsync_vc14_sync(ho[g][14]),.hsync_vc15_sync(ho[g][15]),
   .vsync_vc0_sync(vo[g][0]),.vsync_vc1_sync(vo[g][1]),.vsync_vc2_sync(vo[g][2]),.vsync_vc3_sync(vo[g][3]),
   .vsync_vc4_sync(vo[g][4]),.vsync_vc5_sync(vo[g][5]),.vsync_vc6_sync(vo[g][6]),.vsync_vc7_sync(vo[g][7]),
   .vsync_vc8_sync(vo[g][8]),.vsync_vc9_sync(vo[g][9]),.vsync_vc10_sync(vo[g][10]),.vsync_vc11_sync(vo[g][11]),
   .vsync_vc12_sync(vo[g][12]),.vsync_vc13_sync(vo[g][13]),.vsync_vc14_sync(vo[g][14]),.vsync_vc15_sync(vo[g][15])
  );
 end endgenerate
 always @(negedge pc)if(reset_n)begin
  if(pixel_valid[0]!==pixel_valid[1]||ho[0]!==ho[1]||vo[0]!==vo[1])$fatal(1,"RAW10 timing mismatch");
  if(pixel_valid[0])begin
   if(pixel[0]!==pixel[1]||(^pixel[0])===1'bx)$fatal(1,"RAW10 data mismatch");
   seen=seen+1;
  end
 end
 integer i,j;
 initial begin
  repeat(10)@(negedge bc);reset_n=1;repeat(20)@(negedge bc);
  vs=1;repeat(5)@(negedge bc);vs=0;
  for(j=0;j<12;j=j+1)begin
   lines=j;hs=1;header=1;@(negedge bc);header=0;repeat(8)@(negedge bc);
   for(i=0;i<200;i=i+1)begin valid=1;payload={$random,$random};@(negedge bc);end
   valid=0;repeat(8)@(negedge bc);hs=0;repeat(150)@(negedge bc);
  end
  repeat(1000)@(negedge bc);
  if(seen!=3840)$fatal(1,"RAW10 output count %0d expected 3840",seen);
  $display("PASS RAW10 Pack15 vs Pack1 pixels=15360 words=%0d",seen);$finish;
 end
endmodule
