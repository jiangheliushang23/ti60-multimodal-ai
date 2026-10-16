// Passive RAW8 BGGR statistics, before WB/Gamma. Sample complete 2x2 Bayer blocks.
module sc_auto_stats #(
 parameter integer WIDTH=1920, HEIGHT=1080, SAMPLE_LOG2=4,
 parameter integer DARK=4, CLIP=232
)(
 input wire clk,reset,vs,de,format_ok,
 input wire [31:0] pixels,
 output wire [383:0] values,
 output reg frame_toggle
);
 reg vs_d,seen_blank,armed,bad;
 reg [11:0] x,y;
 reg [31:0] pixel_count,good_frames,bad_frames;
 reg [31:0] ae_sum,ae_count,clip_count,sample_count;
 reg [31:0] r_sum,r_count,g_sum,g_count,b_sum,b_count;
 reg [319:0] published;
 wire first=vs && !vs_d && seen_blank;
 wire active=(armed || first) && vs;
 wire [11:0] px=first?12'd0:x, py=first?12'd0:y;
 wire selected=active && de && format_ok && px[SAMPLE_LOG2-1:0]==0 &&
               (py[SAMPLE_LOG2-1:0]==0 || py[SAMPLE_LOG2-1:0]==1);
 wire [7:0] p0=pixels[7:0],p1=pixels[15:8];
 wire [7:0] green=py[0]?p0:p1, chroma=py[0]?p1:p0;
 wire green_ok=green>=DARK && green<CLIP;
 wire chroma_ok=chroma>=DARK && chroma<CLIP;
 assign values={good_frames,bad_frames,published};
 always @(posedge clk or posedge reset) begin
  if(reset) begin
   vs_d<=0;seen_blank<=0;armed<=0;bad<=0;x<=0;y<=0;
   pixel_count<=0;good_frames<=0;bad_frames<=0;frame_toggle<=0;published<=0;
   ae_sum<=0;ae_count<=0;clip_count<=0;sample_count<=0;
   r_sum<=0;r_count<=0;g_sum<=0;g_count<=0;b_sum<=0;b_count<=0;
  end else begin
   vs_d<=vs;
   if(!vs) seen_blank<=1;
   if(first) begin
    armed<=1;bad<=0;x<=0;y<=0;pixel_count<=0;
    frame_toggle<=~frame_toggle;
    ae_sum<=0;ae_count<=0;clip_count<=0;sample_count<=0;
    r_sum<=0;r_count<=0;g_sum<=0;g_count<=0;b_sum<=0;b_count<=0;
   end
   if(active && de) begin
    if(!format_ok || px>=WIDTH || py>=HEIGHT) bad<=1;
    // CSI DE can pause inside one line. WC/PPC identify the mode; count only
    // valid pixels to reconstruct row coordinates, as in the proven framebuffer.
    if(px==WIDTH-4) begin x<=0;y<=py+12'd1;end
    else x<=px+12'd4;
    pixel_count<=(first?32'd0:pixel_count)+32'd4;
   end
   if(selected) begin
    ae_sum<=(first?32'd0:ae_sum)+{24'd0,green};
    ae_count<=(first?32'd0:ae_count)+32'd1;
    sample_count<=(first?32'd0:sample_count)+32'd2;
    clip_count<=(first?32'd0:clip_count)+{31'd0,(p0>=CLIP)}+{31'd0,(p1>=CLIP)};
    if(green_ok) begin
     g_sum<=(first?32'd0:g_sum)+{24'd0,green};g_count<=(first?32'd0:g_count)+32'd1;
    end
    if(chroma_ok && py[0]) begin
     r_sum<=(first?32'd0:r_sum)+{24'd0,chroma};r_count<=(first?32'd0:r_count)+32'd1;
    end
    if(chroma_ok && !py[0]) begin
     b_sum<=(first?32'd0:b_sum)+{24'd0,chroma};b_count<=(first?32'd0:b_count)+32'd1;
    end
   end
   if(armed && vs_d && !vs) begin
    armed<=0;
    if(!bad && !de && pixel_count==WIDTH*HEIGHT && x==0 && y==HEIGHT) begin
     good_frames<=good_frames+32'd1;
     published<={ae_sum,ae_count,clip_count,sample_count,r_sum,r_count,g_sum,g_count,b_sum,b_count};
    end else bad_frames<=bad_frames+32'd1;
   end
  end
 end
endmodule

// A shared sequential divider keeps division out of the pixel-rate datapath.
module sc_auto_divider(
 input wire clk,reset,start,
 input wire [31:0] numerator,denominator,
 output reg busy,done,
 output reg [31:0] quotient
);
 reg [31:0] dividend,divisor;
 reg [32:0] remainder;
 reg [5:0] count;
 wire [32:0] shifted={remainder[31:0],dividend[31]};
 wire subtract=shifted>={1'b0,divisor};
 always @(posedge clk) begin
  if(reset) begin busy<=0;done<=0;quotient<=0;dividend<=0;divisor<=0;remainder<=0;count<=0;end
  else begin
   done<=0;
   if(!busy) begin
    if(start) begin
     quotient<=0;remainder<=0;dividend<=numerator;divisor<=denominator;count<=0;
     if(denominator==0) done<=1;else busy<=1;
    end
   end else begin
    remainder<=subtract?shifted-{1'b0,divisor}:shifted;
    dividend<={dividend[30:0],1'b0};quotient<={quotient[30:0],subtract};
    if(count==31) begin busy<=0;done<=1;end else count<=count+1'b1;
   end
  end
 end
endmodule
