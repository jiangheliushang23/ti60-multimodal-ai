module sht30_reader #(
 parameter integer TICK_CYCLES=125, TIMEOUT_TICKS=2000,
 parameter integer PERIOD_CYCLES=25000000, CONVERT_CYCLES=500000
)(input wire clk,reset,scl_in,sda_in,
 output wire scl_low,sda_low,
 output reg [2:0] status, output reg sample,
 output reg [6:0] report_address,
 output reg [15:0] temperature_raw,humidity_raw,
 output reg ack_seen);
 reg [2:0] state;
 localparam integer MAX_DELAY=PERIOD_CYCLES>CONVERT_CYCLES?PERIOD_CYCLES:CONVERT_CYCLES;
 reg [$clog2(MAX_DELAY+1)-1:0] delay_count;
 reg [6:0] address;
 reg start,read_op;
 wire done,busy; wire [2:0] result; wire [47:0] data;
 sht30_bus #(.TICK_CYCLES(TICK_CYCLES),.TIMEOUT_TICKS(TIMEOUT_TICKS)) bus
 (.clk(clk),.reset(reset),.scl_in(scl_in),.sda_in(sda_in),
 .start(start),.read_op(read_op),.address(address),.scl_low(scl_low),.sda_low(sda_low),
 .busy(busy),.done(done),.result(result),.read_data(data));
 function [7:0] crc16;
 input [15:0] value; integer i; reg [7:0] c;
 begin
  c=8'hff;
  for(i=15;i>=0;i=i-1) begin
   if(c[7]^value[i]) c={c[6:0],1'b0}^8'h31;
   else c={c[6:0],1'b0};
  end
  crc16=c;
 end endfunction
 always @(posedge clk) begin
  if(reset) begin
   state<=0; delay_count<=0; address<=7'h44; report_address<=7'h44;
   start<=0; read_op<=0; status<=0; sample<=0; ack_seen<=0;
   temperature_raw<=0; humidity_raw<=0;
  end else begin
   start<=0; sample<=0;
   case(state)
    0: if(delay_count==PERIOD_CYCLES-1) begin
       delay_count<=0; start<=1; read_op<=0; state<=1;
       ack_seen<=0; temperature_raw<=0; humidity_raw<=0;
       report_address<=address;
      end else delay_count<=delay_count+1'b1;
    1: if(done) begin
       if(result==1) begin ack_seen<=1; delay_count<=0; state<=2; end
       else begin
        status<=result; sample<=1; state<=0;
        if(result==2) address<=address^7'h01;
       end
      end
    2: if(delay_count==CONVERT_CYCLES-1) begin
       delay_count<=0; read_op<=1; start<=1; state<=3;
      end else delay_count<=delay_count+1'b1;
    3: if(done) begin
       temperature_raw<=data[47:32]; humidity_raw<=data[23:8];
       if(result!=1) status<=result;
       else if(crc16(data[47:32])!=data[31:24] || crc16(data[23:8])!=data[7:0]) status<=3;
       else status<=1;
       sample<=1; state<=0; delay_count<=0;
      end
    default: state<=0;
   endcase
  end
 end
endmodule
