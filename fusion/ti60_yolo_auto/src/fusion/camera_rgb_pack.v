// Full-field 1920x1080 -> 1280x720. Nearest-neighbour 3:2 reduction after ISP.
// Four pixels selected from each six: [0,1,3,4]. Two groups form one AXI beat.
// RGB565 is a display storage format; this module does not supply AI input yet.
module camera_rgb_pack #(parameter WIDTH=1920,HEIGHT=1080)(
 input wire clk,reset,vs,de,input wire [47:0] rgb,
 output reg valid,output reg [127:0] data,output reg complete,output reg malformed);
 reg [1:0] phase,yphase;reg [10:0] x,y;reg de_d;
 reg [31:0] first;reg [15:0] third;reg [63:0] lower;reg half;
 wire [15:0] p0={rgb[7:3],rgb[15:10],rgb[23:19]};
 wire [15:0] p1={rgb[31:27],rgb[39:34],rgb[47:43]};
 always @(posedge clk)begin
  if(reset||vs)begin
   phase<=0;yphase<=0;x<=0;y<=0;de_d<=0;first<=0;third<=0;lower<=0;half<=0;
   valid<=0;data<=0;complete<=0;malformed<=0;
  end else begin
   valid<=0;de_d<=de;
   if(de)begin
    x<=x+1'b1;
    if(x>=WIDTH/2||y>=HEIGHT)malformed<=1;
    if(yphase!=2)case(phase)
     0:first<={p1,p0};
     1:third<=p1;
     2:begin
      half<=!half;
      if(!half)lower<={p0,third,first};
      else begin data<={p0,third,first,lower};valid<=1;end
     end
    endcase
    phase<=phase==2?0:phase+1'b1;
   end
   if(de_d&&!de)begin
    if(x!=WIDTH/2||phase!=0||half)malformed<=1;
    x<=0;phase<=0;y<=y+1'b1;yphase<=yphase==2?0:yphase+1'b1;
    if(y==HEIGHT-1)complete<=1;
   end
  end
 end
endmodule
