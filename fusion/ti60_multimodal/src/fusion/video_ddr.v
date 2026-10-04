// Shared-memory video master. RGB565 banks: 06000000, 06200000, 06400000.
// Only complete frames with successful AXI B responses become the latest bank.
// The display bank stays reserved until the previous read burst has drained.
module video_ddr #(parameter BEATS=115200,END_GUARD=8192)(
 input wire clk,reset,sof,input wire [15:0] frame_seq,
 input wire in_valid,input wire [127:0] in_data,input wire complete,malformed,
 input wire end_valid,input wire [16:0] end_data,
 input wire pixel_clk,frame_request,video_take,input wire [2:0] pixel_index,
 output wire [23:0] video_rgb,output wire video_valid,
 output reg [31:0] published,dropped,write_errors,read_errors,underflows,
 output reg [15:0] published_seq,
 output reg [31:0] awaddr,output reg [7:0] awlen,output wire awvalid,input wire awready,
 output wire [127:0] wdata,output wire [15:0] wstrb,output wire wlast,wvalid,input wire wready,
 input wire [1:0] bresp,input wire bvalid,output wire bready,
 output reg [31:0] araddr,output wire [7:0] arlen,output wire arvalid,input wire arready,
 input wire [127:0] rdata,input wire [1:0] rresp,input wire rlast,rvalid,output wire rready);
 function [31:0] base;input [1:0] b;begin base=32'h06000000+{9'd0,b,21'd0};end endfunction
 reg active,closed,bad,end_seen,sensor_good;reg [13:0] end_timer;
 reg [15:0] seq;reg [17:0] received,written;
 reg [1:0] write_bank,read_bank,latest_bank;reg latest_valid;
 reg [22:0] frame_age;reg [26:0] latest_age;
 wire wf_full,wf_empty;wire [9:0] wf_count;wire [127:0] wf_data;
 wire push=active&&!closed&&in_valid&&received<BEATS&&!wf_full;
 reg [1:0] ws;reg [7:0] wbeat;
 wire pop=wvalid&&wready;
 DC_FIFO #(.DATA_WIDTH(128),.FIFO_DEPTH(512),.FIFO_MODE("ShowAhead")) write_fifo(
  .Reset(reset),.WrClk(clk),.WrEn(push),.WrData(in_data),.WrFull(wf_full),.WrDNum(),
  .RdClk(clk),.RdEn(pop),.RdData(wf_data),.RdEmpty(wf_empty),.RdDNum(wf_count),.DataVal());
 assign awvalid=ws==1;assign wvalid=ws==2&&!wf_empty;assign wdata=wf_data;
 assign wstrb=16'hffff;assign wlast=wbeat==awlen;assign bready=ws==3;
 integer b;
 always @(posedge clk)begin
  if(reset)begin
   active<=0;closed<=0;bad<=0;end_seen<=0;sensor_good<=0;end_timer<=0;seq<=0;
   received<=0;written<=0;write_bank<=0;latest_bank<=0;latest_valid<=0;
   ws<=0;wbeat<=0;awaddr<=0;awlen<=0;published<=0;published_seq<=0;dropped<=0;write_errors<=0;
   frame_age<=0;latest_age<=0;
  end else begin
   if(latest_age<100000000)latest_age<=latest_age+1'b1;else latest_valid<=0;
   if(sof)begin
    if(!active&&ws==0&&wf_empty)begin
     active<=1;closed<=0;bad<=0;end_seen<=0;sensor_good<=0;end_timer<=0;
     seq<=frame_seq;received<=0;written<=0;frame_age<=0;
     for(b=0;b<3;b=b+1)if(b!=read_bank&&(!latest_valid||b!=latest_bank))write_bank<=b;
    end else begin
     dropped<=dropped+1'b1;bad<=1;closed<=1;
    end
   end
   if(active&&!closed)begin
    if(frame_age==5000000)begin closed<=1;bad<=1;end
    else frame_age<=frame_age+1'b1;
    if(in_valid)begin
     if(received>=BEATS||wf_full)bad<=1;
     else received<=received+1'b1;
    end
    if(end_valid&&end_data[16:1]==seq)begin
     end_seen<=1;sensor_good<=end_data[0];end_timer<=0;
    end
    if(end_seen)begin
     if(end_timer==END_GUARD-1)begin
      closed<=1;
      if(!complete||malformed||received!=BEATS||!sensor_good)bad<=1;
     end else end_timer<=end_timer+1'b1;
    end
   end
   case(ws)
    0:if(active&&!wf_empty&&(wf_count>=32||closed))begin
     // All full bursts are 512-byte aligned and cannot cross a 4 KiB boundary.
     awaddr<=base(write_bank)+{10'd0,written,4'd0};
     awlen<=wf_count>=32?8'd31:(wf_count==0?8'd0:wf_count[7:0]-1'b1);
     wbeat<=0;ws<=1;
    end
    1:if(awready)ws<=2;
    2:if(pop)begin
     written<=written+1'b1;
     if(wlast)ws<=3;else wbeat<=wbeat+1'b1;
    end
    3:if(bvalid)begin
     if(bresp!=0)begin bad<=1;write_errors<=write_errors+1'b1;end
     ws<=0;
    end
   endcase
   if(active&&closed&&wf_empty&&ws==0)begin
    active<=0;
    if(!bad&&received==BEATS&&written==BEATS)begin
     latest_bank<=write_bank;latest_valid<=1;latest_age<=0;published<=published+1'b1;published_seq<=seq;
    end else dropped<=dropped+1'b1;
   end
  end
 end
 // Pixel-domain request is a toggle issued at the start of vertical blanking.
 (* async_reg="true" *) reg [2:0] req_sync;
 reg req_seen,pending;reg [2:0] rs;reg [5:0] reset_count;
 reg [17:0] read_count;reg [5:0] rbeat;
 reg fifo_reset,display_ok;
 wire rf_full,rf_empty;wire [9:0] rf_count;wire [127:0] rf_data;
 wire reader_reset=reset||fifo_reset;
 wire rd_pop=video_take&&pixel_index==7&&!rf_empty;
 wire rd_push=rs==2&&rvalid&&rready&&!pending;
 DC_FIFO #(.DATA_WIDTH(128),.FIFO_DEPTH(512),.FIFO_MODE("ShowAhead")) read_fifo(
  .Reset(reader_reset),.WrClk(clk),.WrEn(rd_push),.WrData(rdata),.WrFull(rf_full),.WrDNum(rf_count),
  .RdClk(pixel_clk),.RdEn(rd_pop),.RdData(rf_data),.RdEmpty(rf_empty),.RdDNum(),.DataVal());
 assign arvalid=rs==1;assign arlen=31;assign rready=rs==2&&(!rf_full||pending);
 always @(posedge clk)begin
  if(reset)begin
   req_sync<=0;req_seen<=0;pending<=0;rs<=0;read_count<=0;rbeat<=0;reset_count<=0;
   read_bank<=3;fifo_reset<=1;display_ok<=0;araddr<=0;read_errors<=0;
  end else begin
   req_sync<={req_sync[1:0],frame_request};
   if(req_sync[2]!=req_seen)begin req_seen<=req_sync[2];pending<=1;end
   case(rs)
    0:if(pending)begin
     fifo_reset<=1;display_ok<=0;reset_count<=0;rs<=3;pending<=0;
    end else if(display_ok&&read_count<BEATS&&rf_count<448)begin
     araddr<=base(read_bank)+{10'd0,read_count,4'd0};rbeat<=0;rs<=1;
    end
    1:if(arready)rs<=2;
    2:if(rvalid&&rready)begin
     if(rresp!=0||rlast!=(rbeat==31))begin display_ok<=0;read_errors<=read_errors+1'b1;end
     rbeat<=rbeat+1'b1;
     if(rlast)begin read_count<=read_count+18'd32;rs<=0;end
    end
    3:begin
     if(reset_count==15)begin
      fifo_reset<=0;reset_count<=0;read_bank<=latest_valid?latest_bank:2'd3;read_count<=0;rs<=4;
     end else reset_count<=reset_count+1'b1;
    end
    4:begin
     if(reset_count==15)begin display_ok<=read_bank!=3;rs<=0;end
     else reset_count<=reset_count+1'b1;
    end
    default:rs<=0;
   endcase
  end
 end
 (* async_reg="true" *) reg [2:0] ok_sync;
 reg pixel_bad;
 wire [15:0] pixel=rf_data[pixel_index*16+:16];
 assign video_rgb={{pixel[15:11],pixel[15:13]},{pixel[10:5],pixel[10:9]},{pixel[4:0],pixel[4:2]}};
 assign video_valid=ok_sync[2]&&!pixel_bad&&!rf_empty;
 always @(posedge pixel_clk or posedge reader_reset)begin
  if(reader_reset)begin ok_sync<=0;pixel_bad<=0;end
  else begin
   ok_sync<={ok_sync[1:0],display_ok};
   if(video_take&&ok_sync[2]&&rf_empty)pixel_bad<=1;
  end
 end
 reg bad_d;
 always @(posedge pixel_clk or posedge reset)begin
  if(reset)begin bad_d<=0;underflows<=0;end
  else begin bad_d<=pixel_bad;if(pixel_bad&&!bad_d)underflows<=underflows+1'b1;end
 end
endmodule
