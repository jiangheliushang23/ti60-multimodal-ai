// Pin one completed RGB565 DDR bank while the CPU samples it. No extra image RAM.
// Request/acknowledge and pinned metadata cross through explicit synchronizers.
module video_frame_lease #(parameter MAX_HOLD_CYCLES=20000000)(
 input wire mem_clk,cpu_clk,reset,
 input wire [1:0] latest_bank,input wire latest_valid,input wire [15:0] latest_seq,
 input wire [31:0] latest_count,
 input wire [31:0] latest_time_ms,
 output reg pinned_valid,output reg [1:0] pinned_bank,
 input wire [15:0] paddr,input wire psel,penable,pwrite,input wire [31:0] pwdata,
 output reg [31:0] prdata,output wire pslverror);
 reg request,ack;reg [15:0] pinned_seq;reg [25:0] age;
 reg [31:0] pinned_count,latest_gray;
 // Held with the pinned bank until release; three ACK synchronizers provide
 // payload settling time before the CPU may read this bundled-data mailbox.
 reg [31:0] pinned_time_ms;
 (* async_reg="true" *) reg [31:0] count1,count2,gray1,gray2;
 wire [31:0] latest_cpu;
 genvar n;
 generate for(n=0;n<32;n=n+1)begin:decode_count
  assign latest_cpu[n]=^(gray2>>n);
 end endgenerate
 (* async_reg="true" *) reg [2:0] request_sync,ack_sync,valid_sync;
 (* async_reg="true" *) reg [1:0] bank1,bank2;
 (* async_reg="true" *) reg [15:0] seq1,seq2;
 always @(posedge mem_clk)begin
  if(reset)begin request_sync<=0;ack<=0;pinned_valid<=0;pinned_bank<=0;pinned_seq<=0;age<=0;pinned_count<=0;latest_gray<=0;pinned_time_ms<=0;end
  else begin
   latest_gray<=latest_count^(latest_count>>1);
   request_sync<={request_sync[1:0],request};
   if(request_sync[2]!=ack)begin
    ack<=request_sync[2];age<=0;
    if(request_sync[2])begin pinned_bank<=latest_bank;pinned_seq<=latest_seq;pinned_count<=latest_count;pinned_time_ms<=latest_time_ms;pinned_valid<=latest_valid;end
    else pinned_valid<=0;
   end else if(pinned_valid)begin
    if(age==MAX_HOLD_CYCLES-1)pinned_valid<=0;
    else age<=age+1'b1;
   end
  end
 end
 always @(posedge cpu_clk)begin
  if(reset)begin request<=0;ack_sync<=0;valid_sync<=0;bank1<=0;bank2<=0;seq1<=0;seq2<=0;count1<=0;count2<=0;gray1<=0;gray2<=0;end
  else begin
   count1<=pinned_count;count2<=count1;gray1<=latest_gray;gray2<=gray1;
   ack_sync<={ack_sync[1:0],ack};valid_sync<={valid_sync[1:0],pinned_valid};
   bank1<=pinned_bank;bank2<=bank1;seq1<=pinned_seq;seq2<=seq1;
   if(psel&&penable&&pwrite&&paddr[7:0]==8'h04)request<=pwdata[0];
  end
 end
 wire ready=request&&ack_sync[2];
 always @*begin
  prdata=0;
  case(paddr[7:2])
   0:prdata=32'h59465233;
   1:prdata={31'd0,request};
   2:prdata={29'd0,ack_sync[2],ready&&valid_sync[2],ready};
   3:prdata=32'h06000000+{9'd0,bank2,21'd0};
   4:prdata={16'd0,seq2};
   5:prdata=1280;
   6:prdata=720;
   7:prdata=32'h00000565;
   8:prdata=32'h00020000;
   9:prdata=latest_cpu;
   10:prdata=count2;
   11:prdata=pinned_time_ms;
  endcase
 end
 assign pslverror=psel&&penable&&(paddr[1:0]!=0||paddr[7:2]>11||(pwrite&&paddr[7:0]!=8'h04));
endmodule
