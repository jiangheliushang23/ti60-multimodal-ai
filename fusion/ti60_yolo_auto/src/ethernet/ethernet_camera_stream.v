// Read-only post-gamma camera tap. No DDR, CPU or HDMI backpressure.
// 1920x1080 -> 640x360 RGB565, native source cadence (30 FPS / LOW 5 FPS).
// A small asynchronous line queue and one packet RAM replace CPU pixel copies.
module ethernet_camera_stream(
 input wire reset,cam_clk,vs,de,input wire [47:0] rgb,input wire [31:0] time_gray,
 input wire tx_clk,enable,input wire [10:0] tx_position,input wire tx_active,tx_done,
 output wire ready,output reg [7:0] data,output reg [31:0] sent_packets,dropped_frames);
 (* async_reg="true" *) reg [31:0] time1,time2;
 (* async_reg="true" *) reg [1:0] en_sync;
 wire [31:0] now_ms;genvar g;generate for(g=0;g<32;g=g+1)begin:time_decode
  assign now_ms[g]=^(time2>>g);
 end endgenerate
 reg [31:0] stamp;reg [1:0] metadata;reg [10:0] x,y;reg [1:0] xp,yp;
 reg de_d,armed,bad,footer;
 reg fifo_we;reg [17:0] fifo_in;wire full,empty;wire [17:0] head;wire [11:0] queued;
 wire sample=de&&yp==1&&xp!=1;
 wire [23:0] chosen=xp==0?rgb[47:24]:rgb[23:0];
 wire [15:0] rgb565={chosen[7:3],chosen[15:10],chosen[23:19]};
 wire pop;reg [3:0] state;reg [31:0] capture_ms;
 wire [31:0] frame_id=capture_ms^32'h80000000;
 reg [8:0] chunk;reg [10:0] pos;reg [31:0] crc;reg [7:0] byte_value;
 reg [7:0] packet[0:2047];
 // Queue words: 01=frame metadata, 00=pixel, 10=footer with validity.
 DC_FIFO #(.DATA_WIDTH(18),.FIFO_DEPTH(2048),.FIFO_MODE("ShowAhead")) camera_queue(
  .Reset(reset),.WrClk(cam_clk),.WrEn(fifo_we),.WrData(fifo_in),.WrFull(full),.WrDNum(),
  .RdClk(tx_clk),.RdEn(pop),.RdData(head),.RdEmpty(empty),.RdDNum(queued),.DataVal());
 always @(posedge cam_clk)begin
  if(reset)begin
   time1<=0;time2<=0;en_sync<=0;stamp<=0;metadata<=0;x<=0;y<=0;xp<=0;yp<=0;
   de_d<=0;armed<=0;bad<=0;footer<=0;fifo_we<=0;fifo_in<=0;
  end else begin
   time1<=time_gray;time2<=time1;en_sync<={en_sync[0],enable};de_d<=de;fifo_we<=0;
   if(vs)begin
    stamp<=now_ms;metadata<=en_sync[1]?2:0;
    x<=0;y<=0;xp<=0;yp<=0;armed<=en_sync[1];bad<=0;footer<=0;
   end else begin
    if(metadata!=0)begin
     metadata<=metadata-1'b1;
     if(!full)begin
      fifo_we<=1;
      case(metadata)
       2:fifo_in<={2'b01,stamp[15:0]};1:fifo_in<={2'b01,stamp[31:16]};
      endcase
     end else begin bad<=1;armed<=0;end
    end else if(footer)begin
     if(!full)begin fifo_we<=1;fifo_in<={2'b10,15'd0,!bad};footer<=0;end
    end else if(armed&&sample&&!bad)begin
     if(!full)begin fifo_we<=1;fifo_in<={2'b00,rgb565};end
     else bad<=1;
    end
    if(de)begin
     x<=x+1'b1;xp<=xp==2?0:xp+1'b1;
     if(x>=960||y>=1080)bad<=1;
    end
    if(de_d&&!de)begin
     if(x!=960)bad<=1;
     x<=0;xp<=0;y<=y+1'b1;yp<=yp==2?0:yp+1'b1;
     if(y==1079&&armed)begin footer<=1;armed<=0;end
    end
   end
  end
 end
 // A synchronous table replaces the wide unrolled CRC network. Each byte
 // takes two builder cycles, leaving margin for the 30 FPS source and MAC.
 (* syn_ramstyle="block_ram" *) reg [31:0] crc_rom[0:255];
 reg [31:0] crc_rom_q,init_crc;integer i,j;
 initial begin
  for(i=0;i<256;i=i+1)begin
   init_crc=i;
   for(j=0;j<8;j=j+1)init_crc=init_crc[0]?(init_crc>>1)^32'hedb88320:init_crc>>1;
   crc_rom[i]=init_crc;
  end
 end
 always @(posedge tx_clk)crc_rom_q<=crc_rom[crc[7:0]^byte_value];
 (* syn_ramstyle="block_ram" *) reg [7:0] header_rom[0:127];
 reg [7:0] header_base,header;
 wire [6:0] header_position=state==2?7'd0:state==7?pos[6:0]+1'b1:pos[6:0];
 always @(posedge tx_clk)header_base<=header_rom[header_position];
 initial begin
  for(i=0;i<128;i=i+1)header_rom[i]=0;
  header_rom[0]=8'hff;
  header_rom[1]=8'hff;
  header_rom[2]=8'hff;
  header_rom[3]=8'hff;
  header_rom[4]=8'hff;
  header_rom[5]=8'hff;
  header_rom[6]=8'h02;
  header_rom[7]=8'h54;
  header_rom[8]=8'h49;
  header_rom[9]=8'h36;
  header_rom[11]=8'h02;
  header_rom[12]=8'h08;
  header_rom[14]=8'h45;
  header_rom[16]=8'h05;
  header_rom[17]=8'hdc;
  header_rom[20]=8'h40;
  header_rom[22]=8'h40;
  header_rom[23]=8'h11;
  header_rom[24]=8'hb3;
  header_rom[25]=8'hbb;
  header_rom[26]=8'hc0;
  header_rom[27]=8'ha8;
  header_rom[29]=8'h02;
  header_rom[30]=8'hc0;
  header_rom[31]=8'ha8;
  header_rom[33]=8'h03;
  header_rom[34]=8'h1f;
  header_rom[35]=8'h90;
  header_rom[36]=8'h1f;
  header_rom[37]=8'h90;
  header_rom[38]=8'h05;
  header_rom[39]=8'hc8;
  header_rom[42]=8'h54;
  header_rom[43]=8'h43;
  header_rom[44]=8'h41;
  header_rom[45]=8'h4d;
  header_rom[46]=8'h36;
  header_rom[47]=8'h34;
  header_rom[48]=8'h30;
  header_rom[49]=8'h31;
  header_rom[58]=8'h02;
  header_rom[59]=8'h80;
  header_rom[60]=8'h01;
  header_rom[61]=8'h68;
  header_rom[64]=8'h01;
  header_rom[65]=8'h40;
  header_rom[70]=8'h05;
  header_rom[71]=8'ha0;
  header_rom[72]=8'h02;
 end
 wire [31:0] offset={23'd0,chunk}*32'd1440;
 always @*begin
  header=header_base;
  case(pos[6:0])
   50:header=frame_id[31:24];51:header=frame_id[23:16];52:header=frame_id[15:8];53:header=frame_id[7:0];
   54:header=capture_ms[31:24];55:header=capture_ms[23:16];56:header=capture_ms[15:8];57:header=capture_ms[7:0];
   62:header={7'd0,chunk[8]};63:header=chunk[7:0];
   66:header=offset[31:24];67:header=offset[23:16];68:header=offset[15:8];69:header=offset[7:0];
   default:header=header_base;
  endcase
  byte_value=pos<74?header:(pos[0]?head[15:8]:head[7:0]);
 end
 // Fill a complete packet before offering it to the MAC. An incomplete frame
 // never receives its final chunk; the host cannot publish corrupted pictures.
 assign pop=(!empty)&&((state==0)||(state==1)||(state==3&&pos>=74&&head[17:16]==0&&pos[0])||(state==4));
 assign ready=state==6;
 always @(posedge tx_clk)begin
  data<=packet[tx_position];
  if(reset)begin state<=0;capture_ms<=0;chunk<=0;pos<=0;crc<=32'hffffffff;sent_packets<=0;dropped_frames<=0;end
  else case(state)
   0:if(!empty&&head[17:16]==1)begin capture_ms[15:0]<=head[15:0];state<=1;end
   1:if(!empty)begin
    if(head[17:16]!=1)begin state<=0;dropped_frames<=dropped_frames+1'b1;end
    else begin
     capture_ms[31:16]<=head[15:0];state<=2;chunk<=0;
    end
   end
   2:if(!empty)begin
    if(head[17:16]!=0)begin state<=0;dropped_frames<=dropped_frames+1'b1;end
    else if(queued>=720)begin pos<=0;crc<=32'hffffffff;state<=3;end
   end
   3:begin
    if(pos>=74&&(empty||head[17:16]!=0))begin state<=0;dropped_frames<=dropped_frames+1'b1;end
    else begin
     packet[pos]<=byte_value;state<=7;
    end
   end
   7:begin
    crc<=(crc>>8)^crc_rom_q;
    if(pos==1513)begin pos<=1514;state<=chunk==319?4:5;end
    else begin pos<=pos+1'b1;state<=3;end
   end
   4:if(!empty)begin
    if(head[17:16]==2&&head[0])state<=5;
    else begin state<=0;dropped_frames<=dropped_frames+1'b1;end
   end
   5:begin
    packet[pos]<=~crc[7:0];crc<=crc>>8;
    if(pos==1517)state<=6;else pos<=pos+1'b1;
   end
   6:if(tx_done)begin sent_packets<=sent_packets+1'b1;if(chunk==319)state<=0;else begin chunk<=chunk+1'b1;state<=2;end end
   default:state<=0;
  endcase
 end
endmodule
