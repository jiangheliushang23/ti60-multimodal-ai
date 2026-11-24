// Sensor panel shares the existing 1080p scanner. The video pipeline is untouched.
module multimodal_panel_reference #(
 parameter SHT_STALE_CYCLES=445500000,IR_STALE_CYCLES=742500000
)(
 input wire clk,reset,input wire [11:0] h,v,
 input wire ready,input wire [2:0] result,input wire negative,
 input wire [19:0] t_bcd,h_bcd,
 input wire cpu_clk,cpu_request,input wire [447:0] cpu_record,output reg display_ack,
 input wire image_we,input wire [10:0] image_address,input wire [7:0] image_data,
 input wire person_live,person_present,input wire [95:0] metrics,input wire [2:0] power_mode,
 input wire camera_fps_valid,input wire [11:0] camera_fps_bcd,
 output wire [23:0] rgb
);
 (* async_reg="true" *) reg [2:0] req_sync;
 reg [447:0] record_frame;
 localparam IR_STALE_FRAMES=(IR_STALE_CYCLES+2474999)/2475000;
 localparam SHT_STALE_FRAMES=(SHT_STALE_CYCLES+2474999)/2475000;
 reg [$clog2(IR_STALE_FRAMES+1)-1:0] ir_age;
 reg [$clog2(SHT_STALE_FRAMES+1)-1:0] sht_age;
 wire ir_ok=record_frame[3:0]==1&&ir_age<IR_STALE_FRAMES;
 reg [2:0] sht_status,frame_status;reg sign_hold,frame_sign;
 reg [19:0] temp_hold,hum_hold,frame_t,frame_h;
 // The non-displayed bank is writable; request+record stay stable until blank ACK.
 reg [7:0] pixels[0:2047],pixel_q,fetch_q;
 wire [11:0] mx=h-12'd1360,my=v-12'd192;
 wire matrix=h>=1360&&h<1872&&v>=192&&v<576;
 always @(posedge cpu_clk)if(image_we)pixels[image_address]<=image_data;
 // Fetch four corners of the NEXT cell through the existing RAM read port.
 // Prepare vertical blends ahead of time, then interpolate horizontally at
 // pixel rate. The two image banks and their atomic blank-time swap are kept.
 wire [11:0] fetch_offset=h-12'd1344;
 wire [4:0] fetch_x=fetch_offset[8:4],fetch_y=my[8:4];
 wire [4:0] fetch_right=fetch_x==31?fetch_x:fetch_x+1'b1;
 wire [4:0] fetch_bottom=fetch_y==23?fetch_y:fetch_y+1'b1;
 wire prefetch=h>=1344&&h<1856&&v>=192&&v<576;
 wire [10:0] fetch_address={display_ack,h[1]?fetch_bottom:fetch_y,h[0]?fetch_right:fetch_x};
 reg [7:0] corner00,corner10,corner01,corner11;
 reg [11:0] next_left,next_right,blend_left,blend_right;
 function [11:0] vertical_mix;input [7:0] a,b;input [3:0] weight;
 begin vertical_mix=a*(5'd16-{1'b0,weight})+b*{1'b0,weight};end endfunction
 wire [16:0] horizontal_mix=blend_left*(5'd16-{1'b0,mx[3:0]})+
                            blend_right*{1'b0,mx[3:0]}+17'd128;
 always @(posedge clk)if(prefetch&&h[3:2]==0)fetch_q<=pixels[fetch_address];
 always @(posedge clk)begin
  if(reset)begin
   corner00<=0;corner10<=0;corner01<=0;corner11<=0;
   next_left<=0;next_right<=0;blend_left<=0;blend_right<=0;pixel_q<=0;
  end else begin
   if(prefetch)case(h[3:0])
    1:corner00<=fetch_q;
    2:corner10<=fetch_q;
    3:corner01<=fetch_q;
    4:corner11<=fetch_q;
    6:begin next_left<=vertical_mix(corner00,corner01,my[3:0]);
            next_right<=vertical_mix(corner10,corner11,my[3:0]);end
    15:begin blend_left<=next_left;blend_right<=next_right;end
   endcase
   pixel_q<=horizontal_mix[15:8];
  end
 end
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
 wire in_text=(!dy[4])&&(footer?(h>=32&&h<992&&v>=920&&v<1032):
  side?(h<1872&&v>=608&&v<864):(h>=32&&h<992&&v>=64&&v<112));
 reg [319:0] text_line;reg [23:0] ink;
 always @*begin
  text_line={40{8'h20}};ink=24'he8edf5;
  if(footer)case(row)
   0:begin
    text_line="ENV TEMP ---.-- C   RH ---.-- %         ";
    if(frame_status==1)text_line={"ENV ",temperature({frame_sign,11'd0,frame_t}),"  RH ",
     digit(frame_h[19:16]),digit(frame_h[15:12]),digit(frame_h[11:8]),".",digit(frame_h[7:4]),digit(frame_h[3:0])," %",{15{8'h20}}};
   end
   1:text_line=frame_status==1?"SHT30 LIVE | MLX90640 | YOLO DSP        ":"SHT30 WAIT / ERROR | CHECK SENSOR       ";
   2:if(person_live)text_line={"AI INFER ",digit(metrics[47:44]),digit(metrics[43:40]),digit(metrics[39:36]),digit(metrics[35:32])," MS | GREEN PERSON",{9{8'h20}}};
     else text_line="AI WAIT | NO FRESH DETECTION RESULT     ";
   3:case(power_mode)
    0:begin text_line="POWER NORMAL | YOLO ON | CAMERA 30 FPS  ";ink=24'h79e2b2;end
    1:begin text_line="POWER ENTERING LOW | CAMERA SWITCHING   ";ink=24'hffb17a;end
    2:begin text_line={"POWER LOW | YOLO OFF | CAM ",
      camera_fps_valid?{digit(camera_fps_bcd[11:8]),digit(camera_fps_bcd[7:4]),8'h2e,digit(camera_fps_bcd[3:0])}:"--.-",
      " FPS",{5{8'h20}}};ink=24'hffb17a;end
    3:begin text_line="POWER WAKING | RESTORING CAMERA 30 FPS  ";ink=24'hffb17a;end
    4:begin text_line="POWER VERIFY | YOLO CHECKING PERSON     ";ink=24'hffb17a;end
    default:begin text_line="POWER UNKNOWN | CHECK CPU STATUS        ";ink=24'hffb17a;end
   endcase
  endcase
  else if(side)case(row)
   0:begin text_line=ir_ok?"THERMAL LIVE 32 X 24                    ":"THERMAL WAIT / ERROR                    ";ink=ir_ok?24'h79e2b2:24'hffb17a;end
   1:begin text_line={"MIN ---.-- C",{28{8'h20}}};if(ir_ok)text_line={"MIN ",temperature(record_frame[63:32]),{28{8'h20}}};end
   2:begin text_line={"MAX ---.-- C",{28{8'h20}}};if(ir_ok)text_line={"MAX ",temperature(record_frame[95:64]),{28{8'h20}}};end
   3:begin text_line={"CENTER ---.-- C",{25{8'h20}}};if(ir_ok)text_line={"CENTER ",temperature(record_frame[127:96]),{25{8'h20}}};end
   4:if(ir_ok)text_line={"THERMAL UPD ",digit(record_frame[19:16]),digit(record_frame[15:12]),".",digit(record_frame[11:8])," HZ",{21{8'h20}}};
     else text_line="THERMAL UPD --.- HZ                     ";
   5:begin
    text_line=person_live?(person_present?"PERSON: YES                             ":"PERSON: NO                              "):"PERSON: WAIT                            ";
    ink=person_live?(person_present?24'h79e2b2:24'he8edf5):24'hffb17a;
   end
   6:if(person_live)text_line={"CONFIDENCE ",digit(metrics[75:72]),digit(metrics[71:68]),digit(metrics[67:64])," %",{24{8'h20}}};
     else text_line="CONFIDENCE --- %                        ";
   7:if(person_live)text_line={"AI FPS ",digit(metrics[15:12]),digit(metrics[11:8]),digit(metrics[7:4]),".",digit(metrics[3:0]),{28{8'h20}}};
     else text_line="AI FPS --.-                             ";
  endcase
  else case(row)
   0:text_line="YOLO MULTIMODAL LIVE                    ";
   1:text_line="CAMERA / THERMAL / ENVIRONMENT          ";
  endcase
 end
 // Fixed slice selection avoids the wide subtract/barrel-select network.
 function [7:0] select_character;
 input [319:0] line;input [5:0] col;
 begin case(col)
  6'd0:select_character=line[319:312];
  6'd1:select_character=line[311:304];
  6'd2:select_character=line[303:296];
  6'd3:select_character=line[295:288];
  6'd4:select_character=line[287:280];
  6'd5:select_character=line[279:272];
  6'd6:select_character=line[271:264];
  6'd7:select_character=line[263:256];
  6'd8:select_character=line[255:248];
  6'd9:select_character=line[247:240];
  6'd10:select_character=line[239:232];
  6'd11:select_character=line[231:224];
  6'd12:select_character=line[223:216];
  6'd13:select_character=line[215:208];
  6'd14:select_character=line[207:200];
  6'd15:select_character=line[199:192];
  6'd16:select_character=line[191:184];
  6'd17:select_character=line[183:176];
  6'd18:select_character=line[175:168];
  6'd19:select_character=line[167:160];
  6'd20:select_character=line[159:152];
  6'd21:select_character=line[151:144];
  6'd22:select_character=line[143:136];
  6'd23:select_character=line[135:128];
  6'd24:select_character=line[127:120];
  6'd25:select_character=line[119:112];
  6'd26:select_character=line[111:104];
  6'd27:select_character=line[103:96];
  6'd28:select_character=line[95:88];
  6'd29:select_character=line[87:80];
  6'd30:select_character=line[79:72];
  6'd31:select_character=line[71:64];
  6'd32:select_character=line[63:56];
  6'd33:select_character=line[55:48];
  6'd34:select_character=line[47:40];
  6'd35:select_character=line[39:32];
  6'd36:select_character=line[31:24];
  6'd37:select_character=line[23:16];
  6'd38:select_character=line[15:8];
  6'd39:select_character=line[7:0];
  default:select_character=8'h20;
 endcase end endfunction
 reg [7:0] character,glyph2;wire [7:0] glyph;
 reg [2:0] gx1,gy1,gx2;
 reg text1,text2,matrix1,matrix2;reg [23:0] ink1,ink2,bg1,bg2,heat2;
 sht30_font font(.character(character),.row(gy1),.bits(glyph));
 // Two panel stages precede the shared output register in fusion_sensor_hdmi.
 assign rgb=matrix2?(ir_ok?heat2:24'h142237):(text2&&glyph2[7-gx2]?ink2:bg2);
 always @(posedge clk)begin
  if(reset)begin
   req_sync<=0;display_ack<=0;record_frame<=0;ir_age<=0;sht_age<=0;
   sht_status<=0;frame_status<=0;sign_hold<=0;frame_sign<=0;temp_hold<=0;hum_hold<=0;frame_t<=0;frame_h<=0;
   character<=32;glyph2<=0;gx1<=0;gy1<=0;gx2<=0;text1<=0;text2<=0;matrix1<=0;matrix2<=0;
   ink1<=0;ink2<=0;bg1<=0;bg2<=0;heat2<=0;
  end else begin
   req_sync<={req_sync[1:0],cpu_request};
   if(ready)begin sht_status<=result;sign_hold<=negative;temp_hold<=t_bcd;hum_hold<=h_bcd;sht_age<=0;end
   if(h==0&&v==1080)begin
    if(ir_age<IR_STALE_FRAMES)ir_age<=ir_age+1'b1;
    if(!ready)begin
     if(sht_age<SHT_STALE_FRAMES)sht_age<=sht_age+1'b1;else sht_status<=5;
    end
    if(req_sync[2]!=display_ack)begin record_frame<=cpu_record;display_ack<=req_sync[2];ir_age<=0;end
    frame_status<=sht_status;frame_sign<=sign_hold;frame_t<=temp_hold;frame_h<=hum_hold;
   end
   character<=select_character(text_line,column);
   gx1<=dx[3:1];gy1<=dy[3:1];text1<=in_text;ink1<=ink;
   bg1<=((h>=16&&h<1328&&v>=128&&v<880)||(h>=1344&&h<1888&&v>=176&&v<880)||(h>=16&&h<1888&&v>=896&&v<1048))?24'h142237:24'h0b1220;
   matrix1<=matrix;matrix2<=matrix1;heat2<=palette(pixel_q);
   glyph2<=glyph;gx2<=gx1;text2<=text1;ink2<=ink1;bg2<=bg1;
  end
 end
endmodule
