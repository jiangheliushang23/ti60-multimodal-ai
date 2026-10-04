// Single 1080p60 scan: 1280x720 video, 512x384 thermal, environment footer.
module fusion_page #(parameter STALE_CYCLES=445500000,IR_STALE_CYCLES=742500000)(
 input wire clk,reset,ready,input wire [2:0] result,input wire negative,
 input wire [19:0] t_bcd,h_bcd,
 input wire cpu_clk,cpu_request,image_we,input wire [10:0] image_address,
 input wire [7:0] image_data,input wire [447:0] cpu_record,output reg display_ack,
 input wire [23:0] video_rgb,input wire video_valid,
 output reg frame_request,output wire video_take,output wire [2:0] pixel_index,
 output reg hs,vs,de,output reg [23:0] rgb);
 reg [11:0] h,v;
 assign video_take=h>=32&&h<1312&&v>=144&&v<864;
 assign pixel_index=h[2:0];
 (* async_reg="true" *) reg [1:0] req_sync;
 reg [447:0] record_frame;reg [29:0] ir_age;reg [28:0] age;
 wire ir_ok=record_frame[3:0]==1&&ir_age<IR_STALE_CYCLES;
 reg [2:0] sht_status,frame_status;reg sign_hold,frame_sign;
 reg [19:0] temp_hold,hum_hold,frame_t,frame_h;
 reg [7:0] pixels[0:2047],pixel_q;
 wire [11:0] mx=h-12'd1360,my=v-12'd192;
 wire matrix=h>=1360&&h<1872&&v>=192&&v<576;
 always @(posedge cpu_clk)if(image_we)pixels[image_address]<=image_data;
 always @(posedge clk)pixel_q<=pixels[{display_ack,my[8:4],mx[8:4]}];
 function [23:0] palette;input [7:0] n;reg [7:0] f;begin
  f={n[5:0],2'b0};case(n[7:6])
   0:palette={8'd0,f,8'd255};1:palette={8'd0,8'd255,8'd255-f};
   2:palette={f,8'd255,8'd0};3:palette={8'd255,8'd255-f,8'd0};
  endcase
 end endfunction
 function [7:0] digit;input [3:0] n;begin digit=48+{4'd0,n};end endfunction
 function [63:0] temperature;input [31:0] n;begin
  temperature={n[31]?8'h2d:8'h20,n[19:16]==0?8'h20:digit(n[19:16]),digit(n[15:12]),digit(n[11:8]),
   8'h2e,digit(n[7:4]),digit(n[3:0]),8'h43};
 end endfunction
 wire footer=v>=904,side=h>=1360;
 wire [11:0] dx=side?h-12'd1360:h-12'd32;
 wire [11:0] dy=footer?v-12'd920:side?v-12'd608:v-12'd64;
 wire [5:0] column=dx[9:4];wire [4:0] row=dy[9:5];
 wire in_text=(!dy[4])&&(footer?(h>=32&&h<672&&v>=920&&v<1032):
  side?(h<1872&&v>=608&&v<864):(h>=32&&h<672&&v>=64&&v<112));
 reg [319:0] text_line;reg [23:0] ink;
 always @*begin
  text_line={40{8'h20}};ink=24'he8edf5;
  if(footer)case(row)
   0:begin
    text_line="ENV TEMP ---.-- C   RH ---.-- %         ";
    if(frame_status==1)text_line={"ENV ",temperature({frame_sign,11'd0,frame_t}),"  RH ",
     digit(frame_h[19:16]),digit(frame_h[15:12]),digit(frame_h[11:8]),".",digit(frame_h[7:4]),digit(frame_h[3:0])," %",{15{8'h20}}};
   end
   1:text_line=frame_status==1?"SHT30 LIVE  |  LOCAL SENSOR INPUT       ":"SHT30 WAIT / ERROR  |  CHECK SENSOR     ";
   2:text_line="AI / MOTION: NOT CONNECTED YET          ";
   3:text_line="HDMI 1080P60  |  VIDEO WINDOW 720P      ";
  endcase
  else if(side)case(row)
   0:begin text_line=ir_ok?"THERMAL LIVE  32 X 24                   ":"THERMAL WAIT / ERROR                    ";ink=ir_ok?24'h79e2b2:24'hffb17a;end
   1:begin text_line="MIN ---.-- C                            ";if(ir_ok)text_line={"MIN ",temperature(record_frame[63:32]),{28{8'h20}}};end
   2:begin text_line="MAX ---.-- C                            ";if(ir_ok)text_line={"MAX ",temperature(record_frame[95:64]),{28{8'h20}}};end
   3:begin text_line="CENTER ---.-- C                         ";if(ir_ok)text_line={"CENTER ",temperature(record_frame[127:96]),{25{8'h20}}};end
   5:text_line="EVENT: --                               ";
   6:text_line="CONFIDENCE: --                          ";
   7:text_line="FUSION NOT ACTIVE                       ";
  endcase
  else case(row)
   0:text_line="MULTIMODAL AI TERMINAL                  ";
   1:text_line="SC431HAI / THERMAL / ENVIRONMENT        ";
  endcase
 end
 reg [7:0] character,glyph2;wire [7:0] glyph;
 reg [2:0] gx1,gy1,gx2;
 reg text1,text2,matrix1,matrix2,vid1,vid2,ok1,ok2;
 reg hs1,vs1,de1,hs2,vs2,de2;
 reg [23:0] ink1,ink2,bg1,bg2,heat2,video1,video2;
 sht30_font font(.character(character),.row(gy1),.bits(glyph));
 always @(posedge clk)begin
  if(reset)begin
   h<=0;v<=0;frame_request<=0;req_sync<=0;display_ack<=0;record_frame<=0;ir_age<=0;age<=0;
   sht_status<=0;frame_status<=0;sign_hold<=0;frame_sign<=0;temp_hold<=0;hum_hold<=0;frame_t<=0;frame_h<=0;
   character<=32;glyph2<=0;gx1<=0;gy1<=0;gx2<=0;text1<=0;text2<=0;matrix1<=0;matrix2<=0;
   vid1<=0;vid2<=0;ok1<=0;ok2<=0;hs1<=0;vs1<=0;de1<=0;hs2<=0;vs2<=0;de2<=0;
   ink1<=0;ink2<=0;bg1<=0;bg2<=0;heat2<=0;video1<=0;video2<=0;hs<=0;vs<=0;de<=0;rgb<=0;
  end else begin
   if(h==2199)begin h<=0;v<=v==1124?0:v+1'b1;end else h<=h+1'b1;
   req_sync<={req_sync[0],cpu_request};
   if(ir_age<IR_STALE_CYCLES)ir_age<=ir_age+1'b1;
   if(ready)begin sht_status<=result;sign_hold<=negative;temp_hold<=t_bcd;hum_hold<=h_bcd;age<=0;end
   else if(age<STALE_CYCLES)age<=age+1'b1;else sht_status<=5;
   if(h==0&&v==1080)begin
    frame_request<=!frame_request;
    if(req_sync[1]!=display_ack)begin record_frame<=cpu_record;display_ack<=req_sync[1];ir_age<=0;end
    frame_status<=sht_status;frame_sign<=sign_hold;frame_t<=temp_hold;frame_h<=hum_hold;
   end
   character<=column<40?text_line[319-column*8-:8]:8'h20;
   gx1<=dx[3:1];gy1<=dy[3:1];text1<=in_text;ink1<=ink;
   hs1<=h>=2008&&h<2052;vs1<=v>=1084&&v<1089;de1<=h<1920&&v<1080;
   bg1<=((h>=16&&h<1328&&v>=128&&v<880)||(h>=1344&&h<1888&&v>=176&&v<880)||(h>=16&&h<1888&&v>=896&&v<1048))?24'h142237:24'h0b1220;
   matrix1<=matrix;matrix2<=matrix1;heat2<=palette(pixel_q);
   vid1<=video_take;vid2<=vid1;ok1<=video_valid;ok2<=ok1;video1<=video_rgb;video2<=video1;
   glyph2<=glyph;gx2<=gx1;text2<=text1;ink2<=ink1;bg2<=bg1;
   hs2<=hs1;vs2<=vs1;de2<=de1;hs<=hs2;vs<=vs2;de<=de2;
   rgb<=!de2?24'd0:vid2?(ok2?video2:24'h182638):matrix2?(ir_ok?heat2:24'h142237):
    (text2&&glyph2[7-gx2]?ink2:bg2);
  end
 end
endmodule
