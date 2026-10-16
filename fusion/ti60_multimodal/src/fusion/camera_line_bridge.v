// Four complete RAW8 lines. A slot is released only AFTER its last pixel is read.
// CSI has no backpressure: malformed/overflowed frames are reported, never published.
module camera_line_bridge #(parameter WIDTH=1920,HEIGHT=1080)(
 input wire reset,cam_clk,clk,vs,de,input wire [31:0] raw,
 input wire [1:0] vc,input wire [5:0] dt,input wire [3:0] ppc,input wire [15:0] wc,
 output reg raw_vs,output wire raw_de,output wire [15:0] raw_pair,
 output reg sof,output reg [15:0] sequence_out,
 output wire end_valid,output wire [16:0] end_data,
 output reg [31:0] good_frames,bad_frames,period_ticks,overflow_lines,
 input wire stats_request,output wire stats_ack,output wire [156:0] stats_held,
 output reg [31:0] last_pixels,last_format,last_de_runs,last_packing);
 localparam GROUPS=WIDTH/4,PAIRS=WIDTH/2;
 reg [31:0] memory[0:2047];reg [26:0] desc[0:3];
 reg [2:0] wp,rp,wgray,rgray;
 (* async_reg="true" *) reg [2:0] rg1,rg2,wg1,wg2;
 wire full=wgray=={~rg2[2:1],rg2[0]};wire empty=rgray==wg2;
 reg vs_d,de_d,armed,bad,line_accept,line_bad;
 reg [10:0] y;reg [9:0] x;reg [15:0] seq;
 reg [31:0] ticks,start_tick;
 reg [31:0] frame_pixels,de_runs;
 wire pixel=de&&vs&&vc==0&&dt==6'h2b;
 wire format_ok=wc==WIDTH*10/8&&ppc==4;
 reg end_we;reg [16:0] end_word;wire end_full,end_empty;
 assign end_valid=!end_empty;
 DC_FIFO #(.DATA_WIDTH(17),.FIFO_DEPTH(16),.FIFO_MODE("ShowAhead")) ends(
  .Reset(reset),.WrClk(cam_clk),.WrEn(end_we),.WrData(end_word),.WrDNum(),.WrFull(end_full),
  .RdClk(clk),.RdEn(end_valid),.RdDNum(),.RdEmpty(end_empty),.DataVal(),.RdData(end_data));
 function [7:0] black;input [7:0] n;begin black=n>16?n-8'd16:8'd0;end endfunction
 wire good_end=vs_d&&!vs&&armed&&!bad&&y==HEIGHT&&x==0&&frame_pixels==WIDTH*HEIGHT&&!de&&!end_full;
 camera_auto_stats auto_stats(.clk(cam_clk),.reset(reset),.first(vs&&!vs_d),
  .pixel(pixel),.format_ok(format_ok),.good_end(good_end),.group_x(x),.row_y(y),
  .frame_seq(seq),.pixels({black(raw[15:8]),black(raw[7:0])}),
  .request(stats_request),.acknowledge(stats_ack),.held(stats_held));
 always @(posedge cam_clk or posedge reset) begin
  if(reset)begin
   wp<=0;wgray<=0;rg1<=0;rg2<=0;vs_d<=0;de_d<=0;armed<=0;bad<=0;
   line_accept<=0;line_bad<=0;y<=0;x<=0;seq<=0;ticks<=0;start_tick<=0;
   good_frames<=0;bad_frames<=0;period_ticks<=0;overflow_lines<=0;end_we<=0;end_word<=0;
   frame_pixels<=0;de_runs<=0;last_pixels<=0;last_format<=0;last_de_runs<=0;last_packing<=0;
  end else begin
   rg1<=rgray;rg2<=rg1;vs_d<=vs;de_d<=pixel;ticks<=ticks+1'b1;end_we<=0;
   if(vs&&!vs_d)begin
    seq<=seq+1'b1;armed<=1;bad<=0;y<=0;x<=0;
    period_ticks<=ticks-start_tick;start_tick<=ticks;
    frame_pixels<=0;de_runs<=0;
   end
   if(de&&vs&&dt!=6'h12&&(!pixel||!format_ok))bad<=1;
   if(pixel)begin
    frame_pixels<=(vs&&!vs_d)?32'd4:frame_pixels+32'd4;
    last_format<={4'd0,vc,dt,ppc,wc};
    if(!de_d)de_runs<=(vs&&!vs_d)?32'd1:de_runs+1'b1;
    // CSI pixel_data_valid can contain bubbles INSIDE a packet. Accumulate
    // WIDTH/4 valid groups, not DE runs. WC and the exact frame total guard it.
    if(x==0)begin
     line_accept<=!full;line_bad<=!format_ok;
     if(full)begin bad<=1;overflow_lines<=overflow_lines+1'b1;end
    end
    if(!format_ok||y>=HEIGHT)begin line_bad<=1;bad<=1;end
    if((x==0?!full:line_accept)&&y<HEIGHT)
     memory[{wp[1:0],x[8:0]}]<=
      {black(raw[31:24]),black(raw[23:16]),black(raw[15:8]),black(raw[7:0])};
    if(x==GROUPS-1)begin
     if(line_accept&&!line_bad&&format_ok&&y<HEIGHT)begin
      desc[wp[1:0]]<={seq,y};wp<=wp+1'b1;wgray<=((wp+3'd1)>>1)^(wp+3'd1);
     end else bad<=1;
     if(y<2047)y<=y+1'b1;
     x<=0;
    end else x<=x+1'b1;
   end
   if(vs_d&&!vs&&armed)begin
    armed<=0;
    last_pixels<=frame_pixels;last_de_runs<=de_runs;last_packing<={11'd0,y,x};
    x<=0;y<=0;
    end_word<={seq,(!bad&&y==HEIGHT&&x==0&&frame_pixels==WIDTH*HEIGHT&&!de)};
    if(!end_full)end_we<=1;
    if(!bad&&y==HEIGHT&&x==0&&frame_pixels==WIDTH*HEIGHT&&!de&&!end_full)good_frames<=good_frames+1'b1;
    else bad_frames<=bad_frames+1'b1;
   end
  end
 end
 reg [2:0] state;reg [4:0] wait_count;reg [9:0] pair_index;
 reg [26:0] desc_q;reg [31:0] raw_q;reg half_q,valid_q;
 assign raw_pair=half_q?raw_q[31:16]:raw_q[15:0];assign raw_de=valid_q;
 // Continuous 960-cycle rows meet the inherited ISP's DE-as-line convention.
 always @(posedge clk)begin
  desc_q<=desc[rp[1:0]];
  raw_q<=memory[{rp[1:0],pair_index[9:1]}];
 end
 always @(posedge clk or posedge reset)begin
  if(reset)begin
   rp<=0;rgray<=0;wg1<=0;wg2<=0;state<=0;wait_count<=0;pair_index<=0;
   half_q<=0;valid_q<=0;raw_vs<=0;sof<=0;sequence_out<=0;
  end else begin
   wg1<=wgray;wg2<=wg1;sof<=0;valid_q<=0;half_q<=pair_index[0];
   case(state)
    0:if(!empty)state<=1;
    1:begin
     pair_index<=0;wait_count<=0;
     if(desc_q[10:0]==0)begin raw_vs<=1;sof<=1;sequence_out<=desc_q[26:11];state<=2;end
     else state<=3;
    end
    2:begin
     if(wait_count==7)begin raw_vs<=0;state<=3;end
     else wait_count<=wait_count+1'b1;
    end
    3:begin
     valid_q<=1;
     if(pair_index==PAIRS-1)begin pair_index<=0;wait_count<=0;state<=4;end
     else pair_index<=pair_index+1'b1;
    end
    4:begin
     if(wait_count==15)begin rp<=rp+1'b1;rgray<=((rp+3'd1)>>1)^(rp+3'd1);state<=0;end
     else wait_count<=wait_count+1'b1;
    end
    default:state<=0;
   endcase
  end
 end
endmodule
