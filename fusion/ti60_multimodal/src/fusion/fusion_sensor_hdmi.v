// Shared scanner for real camera and sensor inputs. No test image ROM.
module fusion_sensor_hdmi(
 output wire frame_request,video_take,output wire [2:0] pixel_index,
 input wire [23:0] video_rgb,input wire video_valid,
 input wire cpu_clk,cpu_reset,pixel_clk,pll_locked,
 input wire [15:0] paddr,input wire psel,penable,pwrite,
 input wire [31:0] pwdata,output wire [31:0] prdata,output wire pready,pslverror,
 input wire sht_scl_IN,sht_sda_IN,ir_scl_IN,ir_sda_IN,
 output wire sht_scl_OUT,sht_scl_OE,sht_sda_OUT,sht_sda_OE,
 output wire ir_scl_OUT,ir_scl_OE,ir_sda_OUT,ir_sda_OE,
 output wire [9:0] tmds_clk_o,tmds_data0_o,tmds_data1_o,tmds_data2_o,
 output wire tmds_clk_TX_OE,tmds_data0_TX_OE,tmds_data1_TX_OE,tmds_data2_TX_OE,
 output wire tmds_clk_TX_RST,tmds_data0_TX_RST,tmds_data1_TX_RST,tmds_data2_TX_RST);
 wire reset_async=cpu_reset||!pll_locked;
 (* async_reg="true",syn_preserve=1 *) reg [2:0] reset_release=0;
 always @(posedge pixel_clk or posedge reset_async)
  if(reset_async)reset_release<=0;else reset_release<={reset_release[1:0],1'b1};
 wire pixel_reset=!reset_release[2];
 wire sample,ack_seen,ready,negative;
 wire [2:0] status,result;
 wire [6:0] address;
 wire [15:0] raw_t,raw_h;
 wire [19:0] t_bcd,h_bcd;
 assign sht_scl_OUT=0;assign sht_sda_OUT=0;assign ir_scl_OUT=0;assign ir_sda_OUT=0;
 sht30_reader #(.TICK_CYCLES(743),.TIMEOUT_TICKS(2000),.PERIOD_CYCLES(148500000),.CONVERT_CYCLES(2970000)) reader(
  .clk(pixel_clk),.reset(pixel_reset),.scl_in(sht_scl_IN),.sda_in(sht_sda_IN),
  .scl_low(sht_scl_OE),.sda_low(sht_sda_OE),.status(status),.sample(sample),
  .report_address(address),.temperature_raw(raw_t),.humidity_raw(raw_h),.ack_seen(ack_seen));
 sht30_values values(.clk(pixel_clk),.reset(pixel_reset),.sample(sample),.status(status),
  .raw_t(raw_t),.raw_h(raw_h),.ready(ready),.result(result),.negative(negative),.t_bcd(t_bcd),.h_bcd(h_bcd));
 wire sht_cpu_sample;
 wire [75:0] sht_snapshot;
 fusion_sht_cdc snapshot(.pixel_clk(pixel_clk),.pixel_reset(pixel_reset),.cpu_clk(cpu_clk),.cpu_reset(cpu_reset),
  .ready(ready),.result(result),.negative(negative),.raw_t(raw_t),.raw_h(raw_h),.t_bcd(t_bcd),.h_bcd(h_bcd),
  .sample(sht_cpu_sample),.snapshot(sht_snapshot));
 wire request,ack,image_we;
 wire [447:0] record;
 wire [10:0] image_address;
 wire [7:0] image_data;
 fusion_apb registers(.clk(cpu_clk),.reset(cpu_reset),.paddr(paddr),.psel(psel),.penable(penable),.pwrite(pwrite),
  .pwdata(pwdata),.prdata(prdata),.pready(pready),.pslverror(pslverror),
  .scl_in(ir_scl_IN),.sda_in(ir_sda_IN),.scl_low(ir_scl_OE),.sda_low(ir_sda_OE),
  .sht_sample(sht_cpu_sample),.sht_snapshot(sht_snapshot),.display_ack(ack),.display_ready(!pixel_reset),
  .display_request(request),.display_record(record),.image_we(image_we),.image_address(image_address),.image_data(image_data));
 wire hs,vs,de;wire [23:0] rgb;
 fusion_page page(.clk(pixel_clk),.reset(pixel_reset),.ready(ready),.result(result),.negative(negative),.t_bcd(t_bcd),.h_bcd(h_bcd),
  .cpu_clk(cpu_clk),.cpu_request(request),.image_we(image_we),.image_address(image_address),.image_data(image_data),
  .video_rgb(video_rgb),.video_valid(video_valid),.frame_request(frame_request),.video_take(video_take),.pixel_index(pixel_index),
  .cpu_record(record),.display_ack(ack),.hs(hs),.vs(vs),.de(de),.rgb(rgb));
 wire [9:0] tc,t0,t1,t2;
 dvi_encoder encoder(.pixelclk(pixel_clk),.rstin(pixel_reset),.red_din(rgb[23:16]),.green_din(rgb[15:8]),
  .blue_din(rgb[7:0]),.hsync(hs),.vsync(vs),.de(de),.tmds_clk(tc),.tmds_data0(t0),.tmds_data1(t1),.tmds_data2(t2));
 assign tmds_clk_o=~tc;assign tmds_data0_o=~t0;assign tmds_data1_o=~t1;assign tmds_data2_o=~t2;
 assign {tmds_clk_TX_OE,tmds_data0_TX_OE,tmds_data1_TX_OE,tmds_data2_TX_OE}=4'b1111;
 assign {tmds_clk_TX_RST,tmds_data0_TX_RST,tmds_data1_TX_RST,tmds_data2_TX_RST}=4'b0000;
endmodule
