// Sensor panel shares the existing 1080p scanner. The video pipeline is untouched.
module multimodal_panel #(
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
 reg [4:0] text_id;reg [23:0] ink;
 always @*begin
  text_id=0;ink=24'he8edf5;
  if(footer)case(row)
   0:text_id=frame_status==1?2:1;
   1:text_id=frame_status==1?3:4;
   2:text_id=person_live?5:6;
   3:begin
    ink=power_mode==0?24'h79e2b2:24'hffb17a;
    case(power_mode)
     0:text_id=7;1:text_id=8;2:text_id=9;3:text_id=10;4:text_id=11;default:text_id=12;
    endcase
   end
  endcase
  else if(side)case(row)
   0:begin text_id=ir_ok?13:14;ink=ir_ok?24'h79e2b2:24'hffb17a;end
   1:text_id=ir_ok?18:15;
   2:text_id=ir_ok?19:16;
   3:text_id=ir_ok?20:17;
   4:text_id=ir_ok?21:22;
   5:begin
    text_id=person_live?(person_present?23:24):25;
    ink=person_live?(person_present?24'h79e2b2:24'he8edf5):24'hffb17a;
   end
   6:text_id=person_live?26:27;
   7:text_id=person_live?28:29;
  endcase
  else case(row)
   0:text_id=30;1:text_id=31;
  endcase
 end
 // Fixed text is a compact combinational character ROM. Dynamic digits are
 // inserted after lookup, rather than multiplexing a full 320-bit text row.

 // Select the character first, then insert a single numeric character. This
 // avoids routing all dynamic digits through a 320-bit row multiplexer.
 function [7:0] temperature_character;
 input [31:0] value;input [5:0] pos;
 begin case(pos)
  0:temperature_character=value[31]?8'h2d:8'h20;
  1:temperature_character=value[19:16]==0?8'h20:digit(value[19:16]);
  2:temperature_character=digit(value[15:12]);
  3:temperature_character=digit(value[11:8]);
  4:temperature_character=8'h2e;
  5:temperature_character=digit(value[7:4]);
  6:temperature_character=digit(value[3:0]);
  default:temperature_character=8'h43;
 endcase end endfunction
 reg [7:0] next_character;
 reg [31:0] number;reg [5:0] number_start;reg number_enabled;
 always @*begin
  next_character=0; // Zero means use the original static text ROM.
  number=0;number_start=0;number_enabled=0;
  if(footer)case(row)
   0:if(frame_status==1)begin
    number={frame_sign,11'd0,frame_t};number_start=4;number_enabled=1;
    case(column)
     17:next_character=digit(frame_h[19:16]);18:next_character=digit(frame_h[15:12]);
     19:next_character=digit(frame_h[11:8]);20:next_character=8'h2e;
     21:next_character=digit(frame_h[7:4]);22:next_character=digit(frame_h[3:0]);
    endcase
   end
   2:if(person_live)case(column)
    9:next_character=digit(metrics[47:44]);10:next_character=digit(metrics[43:40]);
    11:next_character=digit(metrics[39:36]);12:next_character=digit(metrics[35:32]);
   endcase
   3:if(power_mode==2&&camera_fps_valid)case(column)
    27:next_character=digit(camera_fps_bcd[11:8]);28:next_character=digit(camera_fps_bcd[7:4]);
    30:next_character=digit(camera_fps_bcd[3:0]);
   endcase
  endcase
  else if(side)case(row)
   1:begin number=record_frame[63:32];number_start=4;number_enabled=ir_ok;end
   2:begin number=record_frame[95:64];number_start=4;number_enabled=ir_ok;end
   3:begin number=record_frame[127:96];number_start=7;number_enabled=ir_ok;end
   4:if(ir_ok)case(column)
    12:next_character=digit(record_frame[19:16]);13:next_character=digit(record_frame[15:12]);
    15:next_character=digit(record_frame[11:8]);
   endcase
   6:if(person_live)case(column)
    11:next_character=digit(metrics[75:72]);12:next_character=digit(metrics[71:68]);
    13:next_character=digit(metrics[67:64]);
   endcase
   7:if(person_live)case(column)
    7:next_character=digit(metrics[15:12]);8:next_character=digit(metrics[11:8]);
    9:next_character=digit(metrics[7:4]);11:next_character=digit(metrics[3:0]);
   endcase
  endcase
  if(number_enabled&&column>=number_start&&column<number_start+8)
   next_character=temperature_character(number,column-number_start);
 end
 reg [7:0] dynamic_character;wire [7:0] static_character_q;
 wire [7:0] character=dynamic_character!=0?dynamic_character:static_character_q;wire [7:0] glyph2;
 multimodal_text_rom text_rom(.clk(clk),.text_id(text_id),.column(column),.character(static_character_q));
 reg [2:0] gx1,gy1,gx2;
 reg text1,text2,matrix1,matrix2;reg [23:0] ink1,ink2,bg1,bg2,heat2;
 sht30_font_sync font(.clk(clk),.reset(reset),.character(character),.row(gy1),.bits(glyph2));
 // Two panel stages precede the shared output register in fusion_sensor_hdmi.
 assign rgb=matrix2?(ir_ok?heat2:24'h142237):(text2&&glyph2[7-gx2]?ink2:bg2);
 always @(posedge clk)begin
  if(reset)begin
   req_sync<=0;display_ack<=0;record_frame<=0;ir_age<=0;sht_age<=0;
   sht_status<=0;frame_status<=0;sign_hold<=0;frame_sign<=0;temp_hold<=0;hum_hold<=0;frame_t<=0;frame_h<=0;
   dynamic_character<=32;gx1<=0;gy1<=0;gx2<=0;text1<=0;text2<=0;matrix1<=0;matrix2<=0;
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
   dynamic_character<=next_character;
   gx1<=dx[3:1];gy1<=dy[3:1];text1<=in_text;ink1<=ink;
   bg1<=((h>=16&&h<1328&&v>=128&&v<880)||(h>=1344&&h<1888&&v>=176&&v<880)||(h>=16&&h<1888&&v>=896&&v<1048))?24'h142237:24'h0b1220;
   matrix1<=matrix;matrix2<=matrix1;heat2<=palette(pixel_q);
   gx2<=gx1;text2<=text1;ink2<=ink1;bg2<=bg1;
  end
 end
endmodule
