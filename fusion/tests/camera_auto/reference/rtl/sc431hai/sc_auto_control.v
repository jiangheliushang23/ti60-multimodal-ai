// Low-rate control. Runtime sensor accesses reuse sc431hai_setup's I2C engine.
module sc_auto_control #(
 parameter integer ENABLE_AEC=1, ENABLE_AWB=0, GAP_CYCLES=25000,
 parameter integer MIN_EXPOSURE=4, MAX_EXPOSURE=2989, SETTLE_FRAMES=4,
 parameter integer LOW_TARGET=48, HIGH_TARGET=64
)(
 input wire clk,reset,ready,mode_ok,frame_start,
 input wire [383:0] stats,
 input wire stats_done,
 output reg stats_request,
 output reg rt_start,rt_read,
 output reg [15:0] rt_address,
 output reg [7:0] rt_data,
 input wire rt_busy,rt_done,
 input wire [2:0] rt_result,
 input wire [7:0] rt_read_data,
 output reg [15:0] gain_r,gain_b,
 output wire [319:0] telemetry,
 output reg telemetry_valid
);
 localparam IDLE=0,SNAPSHOT=1,DIV_START=2,DIV_WAIT=3,DECIDE=4,
            FRAME_WAIT=5,BUS_START=6,BUS_WAIT=7,GAP=8,FAULT=9;
 reg [3:0] state;
 reg [383:0] held;
 reg [31:0] last_frame,updates,gap_count;
 reg [15:0] exposure,next_exposure;
 reg [6:0] gain_index,next_gain_index;
 reg [7:0] fault;
 reg [3:0] settle,command;
 reg [2:0] calculation;
 reg [7:0] ae_mean,r_mean,g_mean,b_mean;
 reg [15:0] target_r,target_b;
 reg divide_start;
 reg [31:0] numerator,denominator;
 wire divide_busy,divide_done;
 wire [31:0] quotient;
 sc_auto_divider divider(.clk(clk),.reset(reset),.start(divide_start),
  .numerator(numerator),.denominator(denominator),.busy(divide_busy),.done(divide_done),.quotient(quotient));
 // Table 2-7: 00/20..31, 80/20..3F, 81/20..3F, 83/20.
 function [15:0] gain_code;
  input [6:0] index;
  begin
   if(index<18) gain_code={8'h00,8'h20+{1'b0,index}};
   else if(index<50) gain_code={8'h80,8'h20+({1'b0,index}-8'd18)};
   else if(index<82) gain_code={8'h81,8'h20+({1'b0,index}-8'd50)};
   else gain_code=16'h8320;
  end
 endfunction
 function [15:0] smooth;
  input [15:0] current,target;
  reg [15:0] delta,step;
  begin
   delta=current>target?current-target:target-current;
   step=delta>>3;if(step==0 && delta>4) step=1;
   if(delta<=4) smooth=current;
   else smooth=current>target?current-step:current+step;
  end
 endfunction
 wire [15:0] selected_gain=gain_code(next_gain_index);
 wire [3:0] reg_index=command>=5?command-4'd5:command;
 reg [15:0] address;
 reg [7:0] expected;
 always @* begin
  case(reg_index)
   0:begin address=16'h3e00;expected={4'd0,next_exposure[15:12]};end
   1:begin address=16'h3e01;expected=next_exposure[11:4];end
   2:begin address=16'h3e02;expected={next_exposure[3:0],4'd0};end
   3:begin address=16'h3e08;expected=selected_gain[15:8];end
   default:begin address=16'h3e09;expected=selected_gain[7:0];end
  endcase
 end
 wire clipped=(held[255:224]<<6)>held[223:192];
 wire bright=ae_mean>HIGH_TARGET || clipped;
 // Increase brightness only after highlights have fallen below half the
 // clipping threshold. Otherwise low mean and highlight protection can fight.
 wire highlights_clear=(held[255:224]<<7)<=held[223:192];
 wire dark=ae_mean<LOW_TARGET && highlights_clear;
 wire [15:0] exposure_step=(exposure>>2)==0?16'd1:exposure>>2;
 wire [15:0] current_gain=gain_code(gain_index);
 assign telemetry={last_frame,{24'd0,ae_mean},{24'd0,r_mean},{24'd0,g_mean},{24'd0,b_mean},
  held[255:224],held[223:192],exposure,current_gain,gain_r,gain_b,updates[23:0],fault};
 always @(posedge clk) begin
  if(reset) begin
   state<=IDLE;held<=0;last_frame<=0;updates<=0;gap_count<=0;
   exposure<=MAX_EXPOSURE;next_exposure<=MAX_EXPOSURE;gain_index<=82;next_gain_index<=82;
   gain_r<=256;gain_b<=256;fault<=0;settle<=0;command<=0;calculation<=0;
   ae_mean<=0;r_mean<=0;g_mean<=0;b_mean<=0;target_r<=256;target_b<=256;
   divide_start<=0;numerator<=0;denominator<=0;stats_request<=0;
   rt_start<=0;rt_read<=0;rt_address<=0;rt_data<=0;telemetry_valid<=0;
  end else begin
   stats_request<=0;rt_start<=0;divide_start<=0;
   case(state)
    IDLE:if(ready) begin
     if(!mode_ok) begin fault<=8'h10;state<=FAULT;end
     else if(frame_start) begin
      if(settle!=0) settle<=settle-1'b1;
      else begin stats_request<=1;state<=SNAPSHOT;end
     end
    end
    SNAPSHOT:if(stats_done) begin
     if(stats[383:352]==last_frame || stats[287:256]==0) state<=IDLE;
     else begin held<=stats;last_frame<=stats[383:352];calculation<=0;state<=DIV_START;end
    end
    DIV_START:begin
     case(calculation)
      0:begin numerator<=held[319:288];denominator<=held[287:256];end
      1:begin numerator<=held[191:160];denominator<=held[159:128];end
      2:begin numerator<=held[127:96];denominator<=held[95:64];end
      3:begin numerator<=held[63:32];denominator<=held[31:0];end
      4:begin numerator<={16'd0,g_mean,8'd0};denominator<={24'd0,r_mean};end
      5:begin numerator<={16'd0,g_mean,8'd0};denominator<={24'd0,b_mean};end
      default:begin numerator<=0;denominator<=1;end
     endcase
     divide_start<=1;state<=DIV_WAIT;
    end
    DIV_WAIT:if(divide_done) begin
     case(calculation)
      0:ae_mean<=quotient[7:0];1:r_mean<=quotient[7:0];
      2:g_mean<=quotient[7:0];3:b_mean<=quotient[7:0];
      4:target_r<=quotient<128?16'd128:(quotient>512?16'd512:quotient[15:0]);
      5:target_b<=quotient<128?16'd128:(quotient>512?16'd512:quotient[15:0]);
     endcase
     if(calculation==5) state<=DECIDE;
     else begin calculation<=calculation+1'b1;state<=DIV_START;end
    end
    DECIDE:begin
     telemetry_valid<=1;next_exposure<=exposure;next_gain_index<=gain_index;
     if(ENABLE_AEC && bright && (gain_index!=0 || exposure>MIN_EXPOSURE)) begin
      if(gain_index!=0) next_gain_index<=gain_index>8?gain_index-7'd8:7'd0;
      else next_exposure<=exposure>MIN_EXPOSURE+exposure_step?exposure-exposure_step:MIN_EXPOSURE;
      state<=FRAME_WAIT;
     end else if(ENABLE_AEC && !bright && dark && (exposure<MAX_EXPOSURE || gain_index<82)) begin
      if(exposure<MAX_EXPOSURE) next_exposure<=exposure+exposure_step<MAX_EXPOSURE?exposure+exposure_step:MAX_EXPOSURE;
      else next_gain_index<=gain_index<78?gain_index+7'd4:7'd82;
      state<=FRAME_WAIT;
     end else begin
      // A scene below target can still have usable color samples after AEC has
      // reached its upper bound. Keep genuinely dark/noisy scenes frozen.
      if(ENABLE_AWB && ae_mean>=24 && !bright && (!dark || (exposure==MAX_EXPOSURE && gain_index==82)) &&
         r_mean>=4 && g_mean>=4 && b_mean>=4 &&
         held[159:128]>=64 && held[95:64]>=64 && held[31:0]>=64) begin
       gain_r<=smooth(gain_r,target_r);gain_b<=smooth(gain_b,target_b);
      end
      settle<=1;state<=IDLE;
     end
    end
    FRAME_WAIT:if(frame_start) begin command<=0;state<=BUS_START;end
    BUS_START:if(!rt_busy) begin
     rt_address<=address;rt_data<=expected;rt_read<=command>=5;rt_start<=1;state<=BUS_WAIT;
    end
    BUS_WAIT:if(rt_done) begin
     if(rt_result!=1 || (command>=5 && rt_read_data!=expected)) begin
      fault<=rt_result==1?8'd3:{5'd0,rt_result};state<=FAULT;
     end else if(command==9) begin
      exposure<=next_exposure;gain_index<=next_gain_index;updates<=updates+32'd1;
      settle<=SETTLE_FRAMES;state<=IDLE;
     end else begin command<=command+1'b1;gap_count<=0;state<=GAP;end
    end
    GAP:if(gap_count==GAP_CYCLES-1) state<=BUS_START;else gap_count<=gap_count+1'b1;
    FAULT:telemetry_valid<=1;
    default:state<=FAULT;
   endcase
  end
 end
endmodule
