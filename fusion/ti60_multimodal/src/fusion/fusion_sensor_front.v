// Sensor + display front end: SHT30/MLX90640 APB window, HDMI page compositor and
// TMDS output. Structural extraction from tinyml_soc_top.v; no logic change.
// fusion_sensor_hdmi already wraps the APB window, page and DVI encoder; this
// module exposes it as a single subsystem with a clean port list.
module fusion_sensor_front(
 // CPU / peripheral domain.
 input wire cpu_clk,cpu_reset,
 input wire [15:0] paddr,input wire psel,penable,pwrite,
 input wire [31:0] pwdata,output wire [31:0] prdata,output wire pready,pslverror,
 // Pixel / TMDS domain.
 input wire pixel_clk,pll_locked,
 // Camera+SHT I2C pins.
 input wire sht_scl_IN,sht_sda_IN,ir_scl_IN,ir_sda_IN,
 output wire sht_scl_OUT,sht_scl_OE,sht_sda_OUT,sht_sda_OE,
 output wire ir_scl_OUT,ir_scl_OE,ir_sda_OUT,ir_sda_OE,
 // Display requests drive fusion_video_path; pixels return from it.
 output wire frame_request,video_take,output wire [2:0] pixel_index,
 input wire [23:0] video_rgb,input wire video_valid,
 // TMDS outputs.
 output wire [9:0] tmds_clk_o,tmds_data0_o,tmds_data1_o,tmds_data2_o,
 output wire tmds_clk_TX_OE,tmds_data0_TX_OE,tmds_data1_TX_OE,tmds_data2_TX_OE,
 output wire tmds_clk_TX_RST,tmds_data0_TX_RST,tmds_data1_TX_RST,tmds_data2_TX_RST);

fusion_sensor_hdmi u_fusion_sensor_hdmi(
 .sht_scl_IN(sht_scl_IN),.sht_sda_IN(sht_sda_IN),
 .sht_scl_OUT(sht_scl_OUT),.sht_scl_OE(sht_scl_OE),.sht_sda_OUT(sht_sda_OUT),.sht_sda_OE(sht_sda_OE),
 .ir_scl_IN(ir_scl_IN),.ir_sda_IN(ir_sda_IN),
 .ir_scl_OUT(ir_scl_OUT),.ir_scl_OE(ir_scl_OE),.ir_sda_OUT(ir_sda_OUT),.ir_sda_OE(ir_sda_OE),
 .cpu_clk(cpu_clk),.cpu_reset(cpu_reset),
 .pixel_clk(pixel_clk),.pll_locked(pll_locked),
 .paddr(paddr),.psel(psel),.penable(penable),.pwrite(pwrite),
 .pwdata(pwdata),.prdata(prdata),.pready(pready),.pslverror(pslverror),
 .frame_request(frame_request),.video_take(video_take),.pixel_index(pixel_index),
 .video_rgb(video_rgb),.video_valid(video_valid),
 .tmds_clk_o(tmds_clk_o),.tmds_data0_o(tmds_data0_o),.tmds_data1_o(tmds_data1_o),.tmds_data2_o(tmds_data2_o),
 .tmds_clk_TX_OE(tmds_clk_TX_OE),.tmds_data0_TX_OE(tmds_data0_TX_OE),.tmds_data1_TX_OE(tmds_data1_TX_OE),.tmds_data2_TX_OE(tmds_data2_TX_OE),
 .tmds_clk_TX_RST(tmds_clk_TX_RST),.tmds_data0_TX_RST(tmds_data0_TX_RST),.tmds_data1_TX_RST(tmds_data1_TX_RST),.tmds_data2_TX_RST(tmds_data2_TX_RST));
endmodule
