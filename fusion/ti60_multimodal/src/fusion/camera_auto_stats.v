// Sparse BGGR statistics reuse the line bridge's coordinates and frame guard.
// The source holds one complete result until the CPU requests another frame.
module camera_auto_stats(
 input wire clk,reset,first,pixel,format_ok,good_end,
 input wire [9:0] group_x,input wire [10:0] row_y,
 input wire [15:0] frame_seq,input wire [15:0] pixels,
 input wire request,output reg acknowledge,output wire [156:0] held
);
 (* async_reg="true" *) reg req1,req2;
 reg [21:0] ae_sum,g_sum;
 reg [20:0] r_sum,b_sum;
 reg [14:0] clipped;
 reg [13:0] g_count;
 reg [12:0] r_count,b_count;
 reg capturing;reg [15:0] held_seq;
 wire start=first&&req2!=acknowledge;
 wire selected=(capturing||start)&&pixel&&format_ok&&(first||group_x[1:0]==0)&&(first||row_y[3:1]==0);
 wire odd=!first&&row_y[0];
 wire [7:0] green=odd?pixels[7:0]:pixels[15:8];
 wire [7:0] chroma=odd?pixels[15:8]:pixels[7:0];
 wire green_ok=green>=4&&green<232,chroma_ok=chroma>=4&&chroma<232;
 wire [1:0] clip_add={1'b0,pixels[7:0]>=232}+{1'b0,pixels[15:8]>=232};
 // Stop accumulating after publication. The accumulator itself is the held
 // mailbox, saving a second bank of 141 bits. Resume only at a requested SOF.
 assign held={held_seq,ae_sum,clipped,r_sum,r_count,g_sum,g_count,b_sum,b_count};
 always @(posedge clk or posedge reset)begin
  if(reset)begin
   req1<=0;req2<=0;acknowledge<=0;capturing<=0;held_seq<=0;
   ae_sum<=0;g_sum<=0;r_sum<=0;b_sum<=0;clipped<=0;g_count<=0;r_count<=0;b_count<=0;
  end else begin
   req1<=request;req2<=req1;
   if(start)begin
    capturing<=1;
    ae_sum<=0;g_sum<=0;r_sum<=0;b_sum<=0;clipped<=0;g_count<=0;r_count<=0;b_count<=0;
   end
   if(selected)begin
    ae_sum<=(first?22'd0:ae_sum)+green;
    clipped<=(first?15'd0:clipped)+clip_add;
    if(green_ok)begin g_sum<=(first?22'd0:g_sum)+green;g_count<=(first?14'd0:g_count)+1'b1;end
    if(chroma_ok&&odd)begin r_sum<=r_sum+chroma;r_count<=r_count+1'b1;end
    if(chroma_ok&&!odd)begin b_sum<=(first?21'd0:b_sum)+chroma;b_count<=(first?13'd0:b_count)+1'b1;end
   end
   if(good_end&&capturing&&req2!=acknowledge)begin
    held_seq<=frame_seq;acknowledge<=req2;capturing<=0;
   end
  end
 end
endmodule
