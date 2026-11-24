// RGB565 display stream -> 96x96 grayscale in independent on-chip RAMs.
// No DDR requests. SOF must be gamma VS, aligned with camera_rgb_pack.
module camera_ai_capture #(
 parameter integer SRC_WIDTH=1280, SRC_HEIGHT=720,
 parameter integer AI_WIDTH=96, AI_HEIGHT=96
)(
 input wire mem_clk,cpu_clk,mem_reset,cpu_reset,sof,
 input wire [15:0] camera_frame_seq,
 input wire packed_valid, input wire [127:0] packed_data,
 input wire packed_complete,packed_bad,
 input wire [15:0] paddr,
 input wire psel,penable,pwrite, input wire [31:0] pwdata,
 output reg [31:0] prdata, output wire pready,pslverror
);
 localparam integer PIXELS=AI_WIDTH*AI_HEIGHT, BEATS=SRC_WIDTH*SRC_HEIGHT/8;
 localparam integer H_STEP=SRC_WIDTH/AI_WIDTH, H_REM=SRC_WIDTH%AI_WIDTH;
 localparam integer V_STEP=SRC_HEIGHT/AI_HEIGHT, V_REM=SRC_HEIGHT%AI_HEIGHT;
 wire reset=mem_reset||cpu_reset;
 wire data_sel=paddr>=16'h7010 && paddr<16'h9410;
 wire ctrl_sel=paddr==16'h9410;
 wire scalar_sel=paddr==16'h7000 || paddr==16'h7004 ||
                 paddr==16'h7008 || paddr==16'h700c ||
                 paddr==16'h9414 || paddr==16'h9418 || paddr==16'h941c;
 wire valid_addr=paddr[1:0]==0 && (data_sel||ctrl_sel||scalar_sel);
 assign pready=1'b1;
 assign pslverror=psel&&penable&&(!valid_addr||(pwrite&&!ctrl_sel));

 reg active,malformed_seen,writing_bank,published_bank,published_valid;
 reg [31:0] published_seq,published_gray,dropped_frames;
 reg [15:0] source_seq,capture_seq;
 reg [17:0] beat_count;
 reg [10:0] src_x,src_y,target_x,target_y;
 reg [6:0] h_rem,v_rem;
 reg [6:0] dst_x,dst_y;
 reg [11:0] write_word_count;
 reg [23:0] pixel_accum;
 reg sof_d;
 wire sample=active&&!sof&&packed_valid && src_y==target_y &&
             target_x>=src_x && target_x<src_x+16'd8 &&
             dst_x<AI_WIDTH && dst_y<AI_HEIGHT;
 // H_STEP>=8: select once before conversion, then use one RAM write port.
 wire [2:0] lane=target_x[2:0];
 wire [15:0] selected_rgb=packed_data[lane*16+:16];
 wire [7:0] red={selected_rgb[15:11],selected_rgb[15:13]};
 wire [7:0] green={selected_rgb[10:5],selected_rgb[10:9]};
 wire [7:0] blue={selected_rgb[4:0],selected_rgb[4:2]};
 wire [15:0] weighted_gray=red*16'd77+green*16'd150+blue*16'd29;
 wire [7:0] gray=weighted_gray[15:8];
 wire ram_we=sample&&dst_x[1:0]==2'd3;
 wire [31:0] ram_wdata={gray,pixel_accum};
 wire [15:0] read_offset=paddr-16'h7010;
 wire [11:0] ram_raddr=read_offset[13:2];
 wire [31:0] ram_q0,ram_q1;
 camera_ai_frame_ram #(.WORDS(PIXELS/4)) bank0(
  .wdata(ram_wdata),.waddr(write_word_count),.we(ram_we&&!writing_bank),.wclk(mem_clk),
  .raddr(ram_raddr),.re(psel&&data_sel),.rclk(cpu_clk),.rdata(ram_q0));
 camera_ai_frame_ram #(.WORDS(PIXELS/4)) bank1(
  .wdata(ram_wdata),.waddr(write_word_count),.we(ram_we&&writing_bank),.wclk(mem_clk),
  .raddr(ram_raddr),.re(psel&&data_sel),.rclk(cpu_clk),.rdata(ram_q1));

 // CPU lease freezes publication before ACK. Writer may continue using the
 // other bank, but cannot overwrite the leased bank. Release before Invoke.
 reg pin_request,locked,pinned_bank,pinned_valid;
 reg [31:0] pinned_seq;
 reg [15:0] pinned_source;
 (* async_reg="true" *) reg [1:0] pin_sync;
 always @(posedge mem_clk or posedge reset) begin
  if(reset) begin
   pin_sync<=0;locked<=0;pinned_bank<=0;pinned_valid<=0;pinned_seq<=0;pinned_source<=0;
  end else begin
   pin_sync<={pin_sync[0],pin_request};
   if(pin_sync[1]&&!locked) begin
    locked<=1;pinned_bank<=published_bank;pinned_valid<=published_valid;
    pinned_seq<=published_seq;pinned_source<=source_seq;
   end else if(!pin_sync[1]) locked<=0;
  end
 end

 always @(posedge mem_clk or posedge reset) begin
  if(reset) begin
   active<=0;malformed_seen<=0;writing_bank<=0;published_bank<=0;published_valid<=0;
   published_seq<=0;published_gray<=0;dropped_frames<=0;source_seq<=0;capture_seq<=0;
   beat_count<=0;src_x<=0;src_y<=0;target_x<=0;target_y<=0;h_rem<=0;v_rem<=0;
   dst_x<=0;dst_y<=0;pixel_accum<=0;write_word_count<=0;sof_d<=0;
  end else begin
   sof_d<=sof;
   if(sof) begin
    if(!sof_d&&active) dropped_frames<=dropped_frames+1'b1;
    writing_bank<=~published_bank;capture_seq<=camera_frame_seq;
    active<=1;malformed_seen<=0;beat_count<=0;src_x<=0;src_y<=0;
    target_x<=0;target_y<=0;h_rem<=0;v_rem<=0;dst_x<=0;dst_y<=0;
    pixel_accum<=0;write_word_count<=0;
   end else if(active) begin
    if(packed_bad) malformed_seen<=1;
    if(packed_valid) begin
     if(beat_count<BEATS) beat_count<=beat_count+1'b1;
     else malformed_seen<=1;
     if(sample) begin
      case(dst_x[1:0])
       2'd0:pixel_accum[7:0]<=gray;
       2'd1:pixel_accum[15:8]<=gray;
       2'd2:pixel_accum[23:16]<=gray;
       2'd3:write_word_count<=write_word_count+1'b1;
      endcase
      dst_x<=dst_x+1'b1;
      if(h_rem+H_REM>=AI_WIDTH) begin
       target_x<=target_x+H_STEP+1;h_rem<=h_rem+H_REM-AI_WIDTH;
      end else begin target_x<=target_x+H_STEP;h_rem<=h_rem+H_REM;end
     end
     if(src_x==SRC_WIDTH-8) begin
      src_x<=0;src_y<=src_y+1'b1;dst_x<=0;target_x<=0;h_rem<=0;
      if(src_y==target_y) begin
       if(dst_x+(sample?1:0)!=AI_WIDTH) malformed_seen<=1;
       dst_y<=dst_y+1'b1;
       if(v_rem+V_REM>=AI_HEIGHT) begin
        target_y<=target_y+V_STEP+1;v_rem<=v_rem+V_REM-AI_HEIGHT;
       end else begin target_y<=target_y+V_STEP;v_rem<=v_rem+V_REM;end
      end
     end else src_x<=src_x+16'd8;
    end
    // complete is held high between frames. SOF has priority above and is
    // aligned to the same gamma VS which clears camera_rgb_pack.complete.
    if(packed_complete) begin
     active<=0;
     if(beat_count==BEATS && !malformed_seen && !packed_bad &&
        dst_y==AI_HEIGHT && write_word_count==PIXELS/4 && !pin_sync[1]&&!locked) begin
      published_bank<=writing_bank;published_valid<=1;source_seq<=capture_seq;
      published_seq<=published_seq+1'b1;
      published_gray<=(published_seq+1'b1)^((published_seq+1'b1)>>1);
     end else dropped_frames<=dropped_frames+1'b1;
    end
   end
  end
 end

 // Continuous sequence is Gray-coded. Pinned multi-bit metadata is held
 // stable before ACK crosses three clocks, then captured as one bundle.
 (* async_reg="true" *) reg [31:0] gray_sync1,gray_sync2;
 (* async_reg="true" *) reg [2:0] lock_sync;
 (* async_reg="true" *) reg [1:0] valid_sync,bank_sync,active_sync,bad_sync;
 reg lease_ready,lease_bank,lease_valid;
 reg [31:0] lease_seq;
 reg [15:0] lease_source;
 reg [7:0] status_divider;
 wire [31:0] dropped_cpu;
 wire [15:0] source_cpu;
 snapshot_cdc #(.WIDTH(48)) telemetry(.src_clk(mem_clk),.dst_clk(cpu_clk),.reset(reset),
  .request(status_divider==0),.src_data({dropped_frames,source_seq}),
  .dst_data({dropped_cpu,source_cpu}),.done());
 always @(posedge cpu_clk or posedge reset) begin
  if(reset) begin
   pin_request<=0;gray_sync1<=0;gray_sync2<=0;lock_sync<=0;
   valid_sync<=0;bank_sync<=0;active_sync<=0;bad_sync<=0;
   lease_ready<=0;lease_bank<=0;lease_valid<=0;lease_seq<=0;lease_source<=0;status_divider<=0;
  end else begin
   status_divider<=status_divider+1'b1;
   gray_sync1<=published_gray;gray_sync2<=gray_sync1;
   lock_sync<={lock_sync[1:0],locked};
   valid_sync<={valid_sync[0],published_valid};bank_sync<={bank_sync[0],published_bank};
   active_sync<={active_sync[0],active};bad_sync<={bad_sync[0],malformed_seen};
   if(psel&&penable&&pwrite&&ctrl_sel&&!pslverror) pin_request<=pwdata[0];
   lease_ready<=lock_sync[2];
   if(lock_sync[2]) begin
    lease_bank<=pinned_bank;lease_valid<=pinned_valid;
    lease_seq<=pinned_seq;lease_source<=pinned_source;
   end
  end
 end
 function [31:0] gray_to_bin;
  input [31:0] g;integer n;
  begin gray_to_bin[31]=g[31];
   for(n=30;n>=0;n=n-1) gray_to_bin[n]=gray_to_bin[n+1]^g[n];
  end
 endfunction
 wire read_bank=lease_ready?lease_bank:bank_sync[1];
 always @* begin
  prdata=0;
  case(paddr)
   16'h7000:prdata=32'h41493636; // AI96
   16'h7004:prdata=lease_ready?lease_seq:gray_to_bin(gray_sync2);
   16'h7008:prdata={26'd0,pin_request,lease_ready,bad_sync[1],active_sync[1],read_bank,
                   (lease_ready?lease_valid:valid_sync[1])};
   16'h700c:prdata=(AI_WIDTH<<16)|AI_HEIGHT;
   16'h9410:prdata={31'd0,pin_request};
   16'h9414:prdata=dropped_cpu;
   16'h9418:prdata={16'd0,(lease_ready?lease_source:source_cpu)};
   16'h941c:prdata=32'h43410602; // CA, revision 6, end-to-end DDR write order
   default:if(data_sel) prdata=read_bank?ram_q1:ram_q0;
  endcase
 end
endmodule

// Explicit 512-word tiles prevent speed-mode synthesis from expanding each
// frame into sixteen 4096x2 RAMs. Five 512x32 tiles use ten RAM10s per bank.
module camera_ai_frame_ram #(parameter integer WORDS=2304)(
 input wire [31:0] wdata,input wire [11:0] waddr,raddr,
 input wire we,wclk,re,rclk,output reg [31:0] rdata
);
 localparam integer BLOCKS=(WORDS+511)/512;
 wire [31:0] block_data[0:BLOCKS-1];
 reg [2:0] read_block;
 always @(posedge rclk) if(re) read_block<=raddr[11:9];
 genvar b;
 generate for(b=0;b<BLOCKS;b=b+1) begin:tile
  common_simple_dual_port_ram #(.DATA_WIDTH(32),.ADDR_WIDTH(9),.OUTPUT_REG("FALSE")) ram(
   .wdata(wdata),.waddr(waddr[8:0]),.we(we&&waddr[11:9]==b),.wclk(wclk),
   .raddr(raddr[8:0]),.re(re&&raddr[11:9]==b),.rclk(rclk),.rdata(block_data[b]));
 end endgenerate
 always @* begin
  rdata=0;
  if(read_block<BLOCKS) rdata=block_data[read_block];
 end
endmodule
