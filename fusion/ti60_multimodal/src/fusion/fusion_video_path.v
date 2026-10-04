// Video DDR path: triple-buffered RGB565 frame store in shared DDR3.
// Structural extraction from tinyml_soc_top.v; no logic change.
// Owns AXI master port S1 of the interconnect. The frozen CPU-domain snapshot
// payload is assembled by the parent, which sees published_seq and the counters.
module fusion_video_path(
 // Camera-side input from fusion_camera_subsys (clk domain).
 input wire clk,reset,
 input wire sof,input wire [15:0] frame_seq,
 input wire in_valid,input wire [127:0] in_data,
 input wire complete,malformed,
 input wire end_valid,input wire [16:0] end_data,
 // Read side, pixel clock domain.
 input wire pixel_clk,
 input wire frame_request,output wire video_take,output wire [2:0] pixel_index,
 output wire [23:0] video_rgb,output wire video_valid,
 // Statistics, all clk domain.
 output wire [31:0] published,output wire [16:0] published_seq,output wire [31:0] dropped,
 output wire [31:0] write_errors,output wire [31:0] read_errors,output wire [31:0] underflows,
 // Interconnect S1 AXI master.
 output wire [31:0] awaddr,output wire [7:0] awlen,output wire awvalid,input wire awready,
 output wire [127:0] wdata,output wire [15:0] wstrb,output wire wlast,output wire wvalid,input wire wready,
 input wire [1:0] bresp,input wire bvalid,output wire bready,
 output wire [31:0] araddr,output wire [7:0] arlen,output wire arvalid,input wire arready,
 input wire [127:0] rdata,input wire [1:0] rresp,input wire rlast,input wire rvalid,output wire rready);

video_ddr u_video_ddr(.clk(clk),.reset(reset),.sof(sof),.frame_seq(frame_seq),
 .in_valid(in_valid),.in_data(in_data),.complete(complete),.malformed(malformed),
 .end_valid(end_valid),.end_data(end_data),.pixel_clk(pixel_clk),.frame_request(frame_request),
 .video_take(video_take),.pixel_index(pixel_index),.video_rgb(video_rgb),.video_valid(video_valid),
 .published(published),.published_seq(published_seq),.dropped(dropped),
 .write_errors(write_errors),.read_errors(read_errors),.underflows(underflows),
 .awaddr(awaddr),
 .awlen(awlen),
 .awvalid(awvalid),
 .awready(awready),
 .wdata(wdata),
 .wstrb(wstrb),
 .wlast(wlast),
 .wvalid(wvalid),
 .wready(wready),
 .bresp(bresp),
 .bvalid(bvalid),
 .bready(bready),
 .araddr(araddr),
 .arlen(arlen),
 .arvalid(arvalid),
 .arready(arready),
 .rdata(rdata),
 .rresp(rresp),
 .rlast(rlast),
 .rvalid(rvalid),
 .rready(rready));
endmodule
