// A complete SHT30 sample stays stable until the CPU clock domain acknowledges it.
module fusion_sht_cdc(
 input wire pixel_clk,pixel_reset,cpu_clk,cpu_reset,ready,
 input wire [2:0] result,input wire negative,
 input wire [15:0] raw_t,raw_h,input wire [19:0] t_bcd,h_bcd,
 output reg sample,output reg [75:0] snapshot);
 reg request,ack;
 reg [75:0] held;
 (* async_reg="true",syn_preserve=1 *) reg [2:0] request_sync,ack_sync;
 always @(posedge pixel_clk)begin
  if(pixel_reset)begin request<=0;held<=0;ack_sync<=0;end
  else begin
   ack_sync<={ack_sync[1:0],ack};
   if(ready && ack_sync[2]==request)begin
    held<={result,negative,t_bcd,h_bcd,raw_t,raw_h};request<=!request;
   end
  end
 end
 always @(posedge cpu_clk)begin
  if(cpu_reset)begin request_sync<=0;ack<=0;sample<=0;snapshot<=0;end
  else begin
   request_sync<={request_sync[1:0],request};sample<=0;
   if(request_sync[2]!=ack)begin snapshot<=held;sample<=1;ack<=request_sync[2];end
  end
 end
endmodule
