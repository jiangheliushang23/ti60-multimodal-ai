// Source data is captured before ACK; it stays stable until the next request.
// A stopped source clock leaves pending asserted, so requests never alias.
module snapshot_cdc #(parameter WIDTH=32)(
 input wire src_clk,dst_clk,reset,request,
 input wire [WIDTH-1:0] src_data,
 output reg [WIDTH-1:0] dst_data,
 output reg done
);
 reg req,ack,pending;
 reg [WIDTH-1:0] held;
 (* async_reg="true" *) reg [1:0] req_sync;
 (* async_reg="true" *) reg [2:0] ack_sync;
 always @(posedge src_clk or posedge reset) begin
   if(reset) begin req_sync<=0;ack<=0;held<=0;end
   else begin
     req_sync<={req_sync[0],req};
     if(req_sync[1]!=ack) begin held<=src_data;ack<=req_sync[1];end
   end
 end
 always @(posedge dst_clk or posedge reset) begin
   if(reset) begin req<=0;pending<=0;ack_sync<=0;dst_data<=0;done<=0;end
   else begin
     ack_sync<={ack_sync[1:0],ack};done<=0;
     if(request && !pending) begin req<=~req;pending<=1;end
     if(pending && ack_sync[2]==req) begin dst_data<=held;pending<=0;done<=1;end
   end
 end
endmodule

