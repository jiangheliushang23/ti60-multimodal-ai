// Retry camera initialization after a transient I2C/ID/readback error. Only the
// camera frontend is reset; an outstanding DDR burst is allowed to drain.
module camera_setup_retry #(
 parameter WAIT_CYCLES=50000000, RESET_CYCLES=1000000, MAX_RETRIES=3
)(
 input wire clk,reset,input wire [31:0] setup_status,
 output wire frontend_reset,output reg [3:0] retries
);
 reg resetting;
 reg [25:0] counter;
 assign frontend_reset=reset||resetting;
 always @(posedge clk)begin
  if(reset)begin resetting<=0;counter<=0;retries<=0;end
  else if(resetting)begin
   if(counter==RESET_CYCLES-1)begin resetting<=0;counter<=0;end
   else counter<=counter+1'b1;
  end else if(setup_status[4]&&setup_status[7:5]!=0&&retries<MAX_RETRIES)begin
   if(counter==WAIT_CYCLES-1)begin resetting<=1;counter<=0;retries<=retries+1'b1;end
   else counter<=counter+1'b1;
  end else counter<=0;
 end
endmodule
