// 1920x1080p60, positive HS/VS. A three-stage text pipeline keeps RGB and sync aligned.
module thermal_page #(parameter integer STALE_CYCLES=445500000,IR_STALE_CYCLES=742500000)(
 input wire clk,reset,ready, input wire [2:0] result,
 input wire negative, input wire [19:0] t_bcd,h_bcd,
 input wire cpu_clk,cpu_request,cpu_trap,image_we,
 input wire [10:0] image_address,input wire [7:0] image_data,
 input wire [447:0] cpu_record,output reg display_ack,
 output reg hs,vs,de, output reg [23:0] rgb);
 reg [11:0] h,v;
 (* async_reg="true" *) reg [1:0] request_sync,trap_sync;
 reg [447:0] record_frame;
 reg [29:0] ir_age;
 wire [3:0] ir_status=trap_sync[1]?4'd10:(ir_age>=IR_STALE_CYCLES?4'd9:record_frame[3:0]);
 reg [7:0] pixels[0:2047];reg [7:0] pixel_q;
 wire [11:0] mx=h-12'd128,my=v-12'd192;
 wire matrix=h>=128&&h<1152&&v>=192&&v<960;
 wire legend=h>=1168&&h<1184&&v>=192&&v<960;
 wire [11:0] hot_x=12'd144+{2'd0,record_frame[292:288],5'd0};
 wire [11:0] hot_y=12'd208+{2'd0,record_frame[297:293],5'd0};
 wire [11:0] hot_dx=h>=hot_x?h-hot_x:hot_x-h,hot_dy=v>=hot_y?v-hot_y:hot_y-v;
 wire [11:0] center_dx=h>=656?h-12'd656:12'd656-h,center_dy=v>=592?v-12'd592:12'd592-v;
 wire hot_mark=(hot_dx<=1&&hot_dy<=11)||(hot_dy<=1&&hot_dx<=11);
 wire hot_border=(hot_dx<=3&&hot_dy<=13)||(hot_dy<=3&&hot_dx<=13);
 wire center_mark=(center_dx<=1&&center_dy<=9)||(center_dy<=1&&center_dx<=9);
 wire center_border=(center_dx<=3&&center_dy<=11)||(center_dy<=3&&center_dx<=11);
 // Hotspot wins if it overlaps the center marker. Markers never affect data.
 wire [1:0] marker=hot_mark?2'd2:hot_border?2'd1:center_mark?2'd3:center_border?2'd1:2'd0;
 always @(posedge cpu_clk) if(image_we)pixels[image_address]<=image_data;
 always @(posedge clk)pixel_q<=pixels[{display_ack,my[9:5],mx[9:5]}];
 function [23:0] palette;
 input [7:0] x;reg [7:0] f;begin f={x[5:0],2'b00};
 case(x[7:6])
 0:palette={8'd0,f,8'd255};1:palette={8'd0,8'd255,8'd255-f};
 2:palette={f,8'd255,8'd0};3:palette={8'd255,8'd255-f,8'd0};
 endcase end endfunction
 function [7:0] hex_digit;
 input [3:0] n;begin hex_digit=n<10?48+{4'd0,n}:55+{4'd0,n};end endfunction
 function [63:0] temperature;
 input [31:0] n;begin temperature={n[31]?8'h2d:8'h20,
 n[19:16]==0?8'h20:8'd48+{4'd0,n[19:16]},8'd48+{4'd0,n[15:12]},8'd48+{4'd0,n[11:8]},
 8'h2e,8'd48+{4'd0,n[7:4]},8'd48+{4'd0,n[3:0]},8'h43};end endfunction
 reg [28:0] age;
 reg [2:0] latest_status,frame_status;
 reg latest_sign,frame_sign;
 reg [19:0] latest_t,latest_h,frame_t,frame_h;
 reg latest_beat,frame_beat;
 wire top_text=v<160;
 wire [11:0] dx=top_text?h-12'd128:h-12'd1216;
 wire [11:0] dy=top_text?v-12'd64:v-12'd192;
 wire [5:0] column=dx[9:4];
 wire [4:0] row=dy[9:5];
 wire in_text=top_text?(h>=128&&h<768&&v>=64&&v<144&&!dy[4]):
   (h>=1216&&h<1856&&v>=192&&v<960&&!dy[4]);
 reg [319:0] line_text;
 reg [23:0] ink;
 function [7:0] digit;
 input [3:0] n; begin digit=8'd48+{4'd0,n}; end
 endfunction
 function [31:0] milliseconds;
 input [15:0] n;begin milliseconds={digit(n[15:12]),digit(n[11:8]),digit(n[7:4]),digit(n[3:0])};end
 endfunction
 always @* begin
  line_text={40{8'h20}}; ink=24'he8edf5;
  if(top_text)begin
   case(row)
    0:line_text="MULTIMODAL - SENSOR BRINGUP             ";
    1:begin
     line_text="SHT30: WAITING                          ";
     if(frame_status==1)line_text={"SHT30 ",temperature({frame_sign,11'd0,frame_t})," H ",
       digit(frame_h[19:16]),digit(frame_h[15:12]),digit(frame_h[11:8]),".",digit(frame_h[7:4]),digit(frame_h[3:0])," %RH",{13{8'h20}}};
     else if(frame_status!=0)line_text="SHT30: CHECK SENSOR                     ";
    end
    2:line_text="32 X 24  -  NATIVE SENSOR RESOLUTION    ";
    default:begin end
   endcase
  end else case(row)
   0:begin
    ink=ir_status==1?24'h79e2b2:24'hffb17a;
    case(ir_status)
     0:line_text="IR: WAITING FOR BOTH PAGES              ";
     1:line_text="IR: LIVE                                ";
     2:line_text="IR: NO RESPONSE                         ";
     3:line_text="IR: RAM OVERRUN                         ";
     4:line_text="IR: BUS TIMEOUT                         ";
     5:line_text="IR: NO NEW DATA                         ";
     6:line_text="IR: CALIBRATION ERROR                   ";
     7:line_text="IR: INVALID TEMPERATURE                 ";
     8:line_text="IR: READING CALIBRATION                 ";
     9:line_text="IR: DATA STALE                          ";
     default:line_text="IR: CPU STOPPED                         ";
    endcase
   end
   2:line_text="MINIMUM                                 ";
   3:begin line_text="---.-- C                                ";if(ir_status==1)line_text={temperature(record_frame[63:32]),{32{8'h20}}};end
   5:line_text="MAXIMUM - WHITE MARK                    ";
   6:begin line_text="---.-- C                                ";if(ir_status==1)line_text={temperature(record_frame[95:64]),{32{8'h20}}};end
   8:line_text="CENTER - CYAN MARK                      ";
   9:begin line_text="---.-- C                                ";if(ir_status==1)line_text={temperature(record_frame[127:96]),{32{8'h20}}};end
   11:line_text="IR SENSOR AMBIENT                       ";
   12:begin line_text="---.-- C                                ";if(ir_status==1)line_text={temperature(record_frame[159:128]),{32{8'h20}}};end
   14:begin
    line_text="COLOR SCALE: ---                        ";
    if(ir_status==1)line_text=record_frame[320]?"COLOR SCALE: AUTO                       ":"COLOR SCALE: FIXED                      ";
   end
   15:begin
    line_text="---.-- C TO ---.-- C                    ";
    if(ir_status==1)line_text={temperature(record_frame[255:224])," TO ",temperature(record_frame[287:256]),{20{8'h20}}};
   end
   16:line_text="BLUE: COOL    RED: WARM                 ";
   17:line_text="FILTER: MEAN + MOTION                   ";
   18:begin
    line_text="I2C ---- MS   CALC ---- MS              ";
    if(ir_status==1)line_text={"I2C ",milliseconds(record_frame[367:352])," MS   CALC ",milliseconds(record_frame[399:384])," MS",{14{8'h20}}};
   end
   19:begin
    line_text="UPDATE ---- MS / SUBPAGE                ";
    if(ir_status==1)line_text={"UPDATE ",milliseconds(record_frame[431:416])," MS / SUBPAGE",{16{8'h20}}};
   end
   20:line_text={"SUBFRAMES:",hex_digit(record_frame[175:172]),hex_digit(record_frame[171:168]),
     hex_digit(record_frame[167:164]),hex_digit(record_frame[163:160]),{26{8'h20}}};
   21:line_text="SENSOR: 4 HZ SUBPAGES                   ";
   22:line_text="EMISSIVITY .95  REFLECTED TA-8 C        ";
   default:begin end
  endcase
 end
 reg [7:0] character;
 reg [2:0] gx1,gy1,gx2;
 reg matrix1,matrix2,legend1,legend2;reg [7:0] legend_color1,legend_color2;reg [23:0] heat2;
 reg [1:0] marker1,marker2;
 reg text1,text2,hs1,vs1,de1,hs2,vs2,de2;
 reg [23:0] ink1,ink2,bg1,bg2;
 wire [7:0] glyph_row;
 sht30_font font(.character(character),.row(gy1),.bits(glyph_row));
 reg [7:0] glyph2;
 always @(posedge clk) begin
  if(reset) begin
   request_sync<=0;trap_sync<=0;display_ack<=0;record_frame<=0;ir_age<=0;
   matrix1<=0;matrix2<=0;legend1<=0;legend2<=0;legend_color1<=0;legend_color2<=0;heat2<=0;
   marker1<=0;marker2<=0;
   h<=0; v<=0; age<=0; latest_status<=0; frame_status<=0;
   latest_sign<=0; frame_sign<=0; latest_t<=0; latest_h<=0; frame_t<=0; frame_h<=0;
   latest_beat<=0; frame_beat<=0;
   character<=32; gx1<=0; gy1<=0; gx2<=0; glyph2<=0;
   text1<=0; text2<=0; hs1<=0; vs1<=0; de1<=0; hs2<=0; vs2<=0; de2<=0;
   ink1<=0; ink2<=0; bg1<=0; bg2<=0; hs<=0; vs<=0; de<=0; rgb<=0;
  end else begin
   request_sync<={request_sync[0],cpu_request};trap_sync<={trap_sync[0],cpu_trap};
   if(ir_age<IR_STALE_CYCLES)ir_age<=ir_age+1'b1;
   if(h==2199) begin h<=0; if(v==1124) v<=0; else v<=v+1'b1; end
   else h<=h+1'b1;
   if(ready) begin
    latest_status<=result; latest_t<=t_bcd; latest_h<=h_bcd; latest_sign<=negative;
    latest_beat<=!latest_beat; age<=0;
   end else if(age<STALE_CYCLES) age<=age+1'b1;
   else latest_status<=5;
   // Sample the whole record only in vertical blank; never tear a visible number.
   if(h==0 && v==1080) begin
    if(request_sync[1]!=display_ack)begin
     display_ack<=request_sync[1];record_frame<=cpu_record;ir_age<=0;
    end
    frame_status<=latest_status; frame_t<=latest_t; frame_h<=latest_h;
    frame_sign<=latest_sign; frame_beat<=latest_beat;
   end
   character<=column<40 ? line_text[319-column*8 -:8] : 8'h20;
   gx1<=dx[3:1]; gy1<=dy[3:1]; text1<=in_text; ink1<=ink;
   hs1<=h>=2008 && h<2052; vs1<=v>=1084 && v<1089; de1<=h<1920 && v<1080;
   if(h>=1200 && h<1872 && v>=176 && v<976) bg1<=24'h142237;
   else bg1<=24'h0b1220;
   matrix1<=matrix;legend1<=legend;
   marker1<=marker;marker2<=marker1;
   legend_color1<=8'd255-(my/3);
   matrix2<=matrix1;legend2<=legend1;legend_color2<=legend_color1;
   heat2<=palette(pixel_q);
   if(h>=1824 && h<1856 && v>=912 && v<944)
    bg1<=frame_beat?24'h79e2b2:24'h29413f;
   glyph2<=glyph_row; gx2<=gx1; text2<=text1; ink2<=ink1; bg2<=bg1;
   hs2<=hs1; vs2<=vs1; de2<=de1;
   hs<=hs2; vs<=vs2; de<=de2;
   rgb<=!de2?24'd0:(matrix2?(ir_status==1?
    (marker2==2?24'hffffff:marker2==3?24'h00ffff:marker2==1?24'h000000:heat2):24'h142237):
    (legend2?palette(legend_color2):(text2&&glyph2[7-gx2]?ink2:bg2)));
  end
 end
endmodule
