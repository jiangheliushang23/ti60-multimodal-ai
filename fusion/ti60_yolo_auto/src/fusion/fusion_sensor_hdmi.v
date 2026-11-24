// Shared camera, acknowledged YOLO overlay, SHT30 and MLX90640 HDMI output.
module fusion_sensor_hdmi(
 output wire [31:0] time_gray,output reg low_power_led,output wire low_power_led1,
 output reg frame_request,output wire video_take,output wire [2:0] pixel_index,
 input wire [23:0] video_rgb,input wire video_valid,
 input wire cpu_clk,cpu_reset,pixel_clk,pll_locked,
 input wire [15:0] paddr,input wire psel,penable,pwrite,
 input wire [31:0] pwdata,output reg [31:0] prdata,output wire pready,pslverror,
 input wire sht_scl_IN,sht_sda_IN,ir_scl_IN,ir_sda_IN,
 output wire sht_scl_OUT,sht_scl_OE,sht_sda_OUT,sht_sda_OE,
 output wire ir_scl_OUT,ir_scl_OE,ir_sda_OUT,ir_sda_OE,
 output wire [9:0] tmds_clk_o,tmds_data0_o,tmds_data1_o,tmds_data2_o,
 output wire tmds_clk_TX_OE,tmds_data0_TX_OE,tmds_data1_TX_OE,tmds_data2_TX_OE,
 output wire tmds_clk_TX_RST,tmds_data0_TX_RST,tmds_data1_TX_RST,tmds_data2_TX_RST);
 // LED0 indicates low power / wake confirmation. LED1 is no longer an indicator.
 assign low_power_led1=1'b0;
 assign sht_scl_OUT=0;assign sht_sda_OUT=0;assign ir_scl_OUT=0;assign ir_sda_OUT=0;
 wire reset_async=cpu_reset||!pll_locked;
 (* async_reg="true",syn_preserve=1 *) reg [2:0] release_reset=0;
 always @(posedge pixel_clk or posedge reset_async)
  if(reset_async)release_reset<=0;else release_reset<={release_reset[1:0],1'b1};
 wire pixel_reset=!release_reset[2];
 reg request,ack;
 reg [127:0] shadow,shown;
 reg [84:0] second_shadow,second_shown;
 reg [95:0] metrics_shadow,metrics_shown;
 reg [15:0] power_status,power_status_frame;
 wire [2:0] power_mode_frame=power_status_frame[2:0];
 wire [15:0] power_status_snapshot;
 // Atomic snapshot handshake: mode can change even when no YOLO mailbox is sent.
 snapshot_cdc #(.WIDTH(16)) power_status_cdc(.src_clk(cpu_clk),.dst_clk(pixel_clk),
  .reset(pixel_reset),.request(1'b1),.src_data(power_status),.dst_data(power_status_snapshot),.done());
 // All staging writes are rejected while busy. The staging words themselves
 // therefore form a stable CDC mailbox until the pixel-domain ACK returns.
 wire [127:0] mailbox=shadow;
 wire [95:0] metrics_mailbox=metrics_shadow;
 (* async_reg="true" *) reg [31:0] shown_seq1,shown_seq2;
 (* async_reg="true" *) reg [2:0] ack_sync,request_sync,ready_sync;
 wire busy=request!=ack_sync[2];
 assign pready=1'b1;
 wire box_sel=paddr>=16'h1058&&paddr<=16'h10a0;
 wire address_ok=paddr==16'h1058||paddr==16'h1070||paddr==16'h1060||
                 paddr==16'h1064||paddr==16'h1068||paddr==16'h106c||paddr==16'h1078||paddr==16'h107c||
                 paddr==16'h1080||paddr==16'h1084||paddr==16'h1088||paddr==16'h1090||paddr==16'h1094||
                 paddr==16'h1098||paddr==16'h109c||paddr==16'h10a0;
 wire box_error=psel&&penable&&(!address_ok||paddr[1:0]!=0||
                    (pwrite&&((busy&&paddr!=16'h1090&&paddr!=16'h1094)||paddr==16'h1058||paddr==16'h1070||paddr==16'h107c)));
 wire [31:0] sensor_data;wire sensor_error;
 assign pslverror=box_sel?box_error:sensor_error;
 wire sample,ready,negative;wire [2:0] status,result;
 wire [15:0] raw_t,raw_h;wire [19:0] t_bcd,h_bcd;
 sht30_reader #(.TICK_CYCLES(743),.TIMEOUT_TICKS(2000),.PERIOD_CYCLES(148500000),.CONVERT_CYCLES(2970000)) reader(
  .clk(pixel_clk),.reset(pixel_reset),.scl_in(sht_scl_IN),.sda_in(sht_sda_IN),
  .scl_low(sht_scl_OE),.sda_low(sht_sda_OE),.status(status),.sample(sample),
  .report_address(),.temperature_raw(raw_t),.humidity_raw(raw_h),.ack_seen());
 sht30_values values(.clk(pixel_clk),.reset(pixel_reset),.sample(sample),.status(status),
  .raw_t(raw_t),.raw_h(raw_h),.ready(ready),.result(result),.negative(negative),.t_bcd(t_bcd),.h_bcd(h_bcd));
 wire sht_sample;wire [75:0] sht_snapshot;
 fusion_sht_cdc snapshot(.pixel_clk(pixel_clk),.pixel_reset(pixel_reset),.cpu_clk(cpu_clk),.cpu_reset(cpu_reset),
  .ready(ready),.result(result),.negative(negative),.raw_t(raw_t),.raw_h(raw_h),.t_bcd(t_bcd),.h_bcd(h_bcd),
  .sample(sht_sample),.snapshot(sht_snapshot));
 wire sensor_request,sensor_ack,image_we;wire [447:0] sensor_record;
 wire [10:0] image_address;wire [7:0] image_data;
 // The acknowledged YOLO mailbox above owns these addresses in this design.
 fusion_apb #(.RECORD_WORDS(4),.LEGACY_AI(0),.I2C_TICK_CYCLES(63)) registers(.clk(cpu_clk),.reset(cpu_reset),.paddr(paddr),.psel(psel&&!box_sel),.penable(penable),.pwrite(pwrite),
  .pwdata(pwdata),.prdata(sensor_data),.pready(),.pslverror(sensor_error),
  .scl_in(ir_scl_IN),.sda_in(ir_sda_IN),.scl_low(ir_scl_OE),.sda_low(ir_sda_OE),
  .sht_sample(sht_sample),.sht_snapshot(sht_snapshot),.display_ack(sensor_ack),.display_ready(!pixel_reset),
  .display_request(sensor_request),.display_record(sensor_record),.ai_ack(1'b0),.ai_request(),.ai_record(),
  .image_we(image_we),.image_address(image_address),.image_data(image_data),.time_gray(time_gray));
 always @(posedge cpu_clk)begin
  if(cpu_reset)begin low_power_led<=0;power_status<=0;end
  else if(psel&&penable&&pwrite&&!box_error)begin
   if(paddr==16'h1090)low_power_led<=pwdata[0];
   if(paddr==16'h1094)power_status<=pwdata[15:0];
  end
 end
 always @*begin
  prdata=box_sel?0:sensor_data;
  case(paddr)
   16'h1058:prdata=32'h59415539; // YAU9: dual behavior plus dedicated voice UART GPIO.
   16'h1090:prdata={31'd0,low_power_led};
   16'h1094:prdata={16'd0,power_status};
   16'h1070:prdata={29'd0,ready_sync[2],ack_sync[2],busy};
   16'h1060:prdata=mailbox[31:0];
   16'h1064:prdata=mailbox[63:32];
   16'h1068:prdata=mailbox[95:64];
   16'h1078:prdata=mailbox[127:96];
   16'h107c:prdata=shown_seq2;
   16'h1080:prdata=metrics_mailbox[31:0];
   16'h1084:prdata=metrics_mailbox[63:32];
   16'h1088:prdata=metrics_mailbox[95:64];
   16'h1098:prdata={11'd0,second_shadow[84:64]};
   16'h109c:prdata=second_shadow[31:0];
   16'h10a0:prdata=second_shadow[63:32];
  endcase
 end
 always @(posedge cpu_clk)begin
  if(cpu_reset)begin request<=0;shadow<=0;second_shadow<=0;metrics_shadow<=0;ack_sync<=0;ready_sync<=0;shown_seq1<=0;shown_seq2<=0;end
  else begin
   shown_seq1<=shown[127:96];shown_seq2<=shown_seq1;
   ack_sync<={ack_sync[1:0],ack};ready_sync<={ready_sync[1:0],!pixel_reset};
   if(psel&&penable&&pwrite&&box_sel&&!box_error)case(paddr)
    16'h1060:shadow[31:0]<=pwdata&32'h001fffff;
    16'h1064:shadow[63:32]<=pwdata&32'h0fff0fff;
    16'h1068:shadow[95:64]<=pwdata&32'h0fff0fff;
    16'h1078:shadow[127:96]<=pwdata;
    16'h1080:metrics_shadow[31:0]<=pwdata&32'h0000ffff;
    16'h1084:metrics_shadow[63:32]<=pwdata&32'h0000ffff;
    16'h1088:metrics_shadow[95:64]<=pwdata&32'h00000fff;
    16'h1098:second_shadow[84:64]<=pwdata[20:0];
    16'h109c:second_shadow[31:0]<=pwdata&32'h0fff0fff;
    16'h10a0:second_shadow[63:32]<=pwdata&32'h0fff0fff;
    16'h106c:if(pwdata[0])request<=!request;
   endcase
  end
 end
 reg [11:0] h,v;
 reg [6:0] age;
 wire [11:0] left=shown[43:32],top=shown[59:48],right=shown[75:64],bottom=shown[91:80];
 assign video_take=h>=32&&h<1312&&v>=144&&v<864;
 assign pixel_index=h[2:0];
 // Reuse four subtractors per rectangle for clipping, borders and ID offsets.
 // Only pixels in the 1280x720 video can be drawn: x differences fit signed
 // 12 bits, y differences fit signed 11 bits, including all clipping edges.
 wire [11:0] dx0=h-left;wire [10:0] dy0=v[10:0]-top[10:0];
 wire [11:0] rx0=right-h;wire [10:0] by0=bottom[10:0]-v[10:0];
 wire first_valid=age<60&&shown[0]&&shown[1]&&video_take&&
  left>=32&&top>=144&&right<=1312&&bottom<=864&&right>left&&bottom>top;
 wire border=first_valid&&!dx0[11]&&!dy0[10]&&!rx0[11]&&!by0[10]&&rx0!=0&&by0!=0&&
  (dx0<3||rx0<=3||dy0<3||by0<=3);
 wire [11:0] second_left=second_shown[11:0],second_top=second_shown[27:16];
 wire [11:0] second_right=second_shown[43:32],second_bottom=second_shown[59:48];
 wire [11:0] dx1=h-second_left;wire [10:0] dy1=v[10:0]-second_top[10:0];
 wire [11:0] rx1=second_right-h;wire [10:0] by1=second_bottom[10:0]-v[10:0];
 wire second_valid=age<60&&second_shown[64]&&video_take&&
  second_left>=32&&second_top>=144&&second_right<=1312&&second_bottom<=864&&
  second_right>second_left&&second_bottom>second_top;
 wire second_border=second_valid&&!dx1[11]&&!dy1[10]&&!rx1[11]&&!by1[10]&&rx1!=0&&by1!=0&&
  (dx1<3||rx1<=3||dy1<3||by1<=3);
 // 2x glyphs, inside the video, four pixels from each box origin.
 wire [6:0] id_dx0=dx0[6:0]-7'd4,id_dx1=dx1[6:0]-7'd4;
 wire [3:0] id_dy0=dy0[3:0]-4'd4,id_dy1=dy1[3:0]-4'd4;
 wire label0=first_valid&&shown[4]&&dx0>=4&&dx0<100&&dy0>=4&&dy0<20;
 wire label1=second_valid&&second_shown[68]&&dx1>=4&&dx1<100&&dy1>=4&&dy1<20;
 wire choose_label0=label0;
 wire [6:0] label_dx=choose_label0?id_dx0[6:0]:id_dx1[6:0];
 wire [2:0] label_row=choose_label0?id_dy0[3:1]:id_dy1[3:1];
 wire [15:0] label_id=choose_label0?shown[20:5]:second_shown[84:69];
 reg [3:0] label_digit;reg [6:0] digit_segments;
 always @*begin
  case(label_dx[6:4])
   2:label_digit=label_id[15:12];3:label_digit=label_id[11:8];
   4:label_digit=label_id[7:4];default:label_digit=label_id[3:0];
  endcase
  // Seven segment decimal glyphs: a,b,c,d,e,f,g. No general ASCII ROM.
  case(label_digit)
   0:digit_segments=7'b1111110;1:digit_segments=7'b0110000;
   2:digit_segments=7'b1101101;3:digit_segments=7'b1111001;
   4:digit_segments=7'b0110011;5:digit_segments=7'b1011011;
   6:digit_segments=7'b1011111;7:digit_segments=7'b1110000;
   8:digit_segments=7'b1111111;9:digit_segments=7'b1111011;
   default:digit_segments=0;
  endcase
 end
 wire [2:0] glyph_x=label_dx[3:1];
 wire glyph_h=glyph_x>=1&&glyph_x<=5;
 wire glyph_top=label_row==0,glyph_mid=label_row==3,glyph_bottom=label_row==6;
 wire glyph_upper=label_row>=1&&label_row<=2,glyph_lower=label_row>=4&&label_row<=5;
 wire digit_ink=(glyph_h&&((digit_segments[6]&&glyph_top)||(digit_segments[0]&&glyph_mid)||(digit_segments[3]&&glyph_bottom)))||
  (glyph_x==5&&((digit_segments[5]&&glyph_upper)||(digit_segments[4]&&glyph_lower)))||
  (glyph_x==1&&((digit_segments[1]&&glyph_upper)||(digit_segments[2]&&glyph_lower)));
 wire prefix_i=(glyph_h&&(glyph_top||glyph_bottom))||(glyph_x==3&&label_row<7);
 wire prefix_d=(glyph_x==1&&label_row<7)||(glyph_h&&(glyph_top||glyph_bottom))||(glyph_x==5&&(glyph_upper||glyph_mid||glyph_lower));
 wire id_ink=(label0||label1)&&(label_dx[6:4]==0?prefix_i:label_dx[6:4]==1?prefix_d:digit_ink);
 wire id_alarm=choose_label0?shown[2]:second_shown[66];
 // Only observed person boxes and IDs are overlaid.
 wire [23:0] panel_rgb;
 multimodal_panel panel(.clk(pixel_clk),.reset(pixel_reset),.h(h),.v(v),
  .ready(ready),.result(result),.negative(negative),.t_bcd(t_bcd),.h_bcd(h_bcd),
  .cpu_clk(cpu_clk),.cpu_request(sensor_request),.cpu_record(sensor_record),.display_ack(sensor_ack),
  .image_we(image_we),.image_address(image_address),.image_data(image_data),
  .person_live(age<60),.person_present(shown[0]||second_shown[64]),.metrics(metrics_shown),.power_mode(power_mode_frame),
  .camera_fps_valid(power_status_frame[3]),.camera_fps_bcd(power_status_frame[15:4]),.rgb(panel_rgb));
 reg hs1,vs1,de1,hs2,vs2,de2,hs,vs,de;
 reg take1,take2,valid1,valid2,box1,box2,alarm1,alarm2;
 reg [23:0] video1,video2,rgb;
 always @(posedge pixel_clk)begin
  if(pixel_reset)begin
   h<=0;v<=0;frame_request<=0;request_sync<=0;ack<=0;shown<=0;second_shown<=0;metrics_shown<=0;age<=127;power_status_frame<=0;
   hs1<=0;vs1<=0;de1<=0;hs2<=0;vs2<=0;de2<=0;hs<=0;vs<=0;de<=0;
   take1<=0;take2<=0;valid1<=0;valid2<=0;box1<=0;box2<=0;alarm1<=0;alarm2<=0;
   video1<=0;video2<=0;rgb<=0;
  end else begin
   if(h==2199)begin h<=0;v<=v==1124?0:v+1'b1;end else h<=h+1'b1;
   request_sync<={request_sync[1:0],request};
   if(h==0&&v==1080)begin
    frame_request<=!frame_request;
    power_status_frame<=power_status_snapshot;
    if(request_sync[2]!=ack)begin shown<=mailbox;second_shown<=second_shadow;metrics_shown<=metrics_mailbox;ack<=request_sync[2];age<=0;end
    else if(age<127)age<=age+1'b1;
   end
   hs1<=h>=2008&&h<2052;vs1<=v>=1084&&v<1089;de1<=h<1920&&v<1080;
   take1<=video_take;take2<=take1;valid1<=video_valid;valid2<=valid1;
   box1<=border||second_border||id_ink;box2<=box1;
   alarm1<=(border&&shown[2])||(second_border&&second_shown[66])||(id_ink&&id_alarm);alarm2<=alarm1;
   video1<=video_rgb;video2<=video1;
   hs2<=hs1;vs2<=vs1;de2<=de1;hs<=hs2;vs<=vs2;de<=de2;
   rgb<=!de2?24'd0:take2?(valid2?(box2?(alarm2?24'hff4040:24'h40ff60):video2):24'h182638):panel_rgb;
  end
 end
 wire [9:0] tc,t0,t1,t2;
 dvi_encoder encoder(.pixelclk(pixel_clk),.rstin(pixel_reset),.red_din(rgb[23:16]),.green_din(rgb[15:8]),
  .blue_din(rgb[7:0]),.hsync(hs),.vsync(vs),.de(de),.tmds_clk(tc),.tmds_data0(t0),.tmds_data1(t1),.tmds_data2(t2));
 assign tmds_clk_o=~tc;assign tmds_data0_o=~t0;assign tmds_data1_o=~t1;assign tmds_data2_o=~t2;
 assign {tmds_clk_TX_OE,tmds_data0_TX_OE,tmds_data1_TX_OE,tmds_data2_TX_OE}=4'b1111;
 assign {tmds_clk_TX_RST,tmds_data0_TX_RST,tmds_data1_TX_RST,tmds_data2_TX_RST}=4'b0000;
endmodule
