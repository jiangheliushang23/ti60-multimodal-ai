module line_buffer
#(
	parameter	P_DEPTH			= 10,
	parameter	PW				= P_DEPTH*2,
	parameter	X_CNT_WIDTH		= 13
)
(
	input	i_arstn,
	input	i_pclk,

	input	i_vsync,
	input	i_hsync,
	input	i_de,
	input	i_valid,
	input	[PW-1:0]i_p,

	output	o_vsync,
	output	o_hsync,
	output	o_de,
	output	o_valid,
	output	[PW-1:0]o_p_0,		//行 N  ,即输出行 y+2
	output	[PW-1:0]o_p_1,		//行 N-1,即输出行 y+1
	output	[PW-1:0]o_p_2,		//行 N-2,即输出行 y  (中心行)
	output	[PW-1:0]o_p_3,		//行 N-3,即输出行 y-1
	output	[PW-1:0]o_p_4,		//行 N-4,即输出行 y-2

	output	[X_CNT_WIDTH-1:0]o_x
);

localparam	HOR_SYNC_POLARITY	= "POSITIVE";
localparam	VER_SYNC_POLARITY	= "POSITIVE";
wire	c_ina_vs_por;
wire	c_ina_hs_por;
wire	c_ina_de_por;

reg		r_vsync_1P;
reg		r_hsync1_1P;
reg		r_de_1P;
reg		r_valid_1P;
reg		[X_CNT_WIDTH-1:0]r_addr1;
reg		[1:0]r_addr1_sel;
reg		[X_CNT_WIDTH-1:0]r_addr2;
reg		r_addr2_sel;
reg		r_vsync_2P;
reg		r_hsync1_2P;
reg		r_de_2P;
reg		r_valid_2P;
reg		[X_CNT_WIDTH-1:0]r_addr2_r;

reg		[PW-1:0]r_p_01_0P;
reg		[PW-1:0]r_p_01_1P;
reg		[PW-1:0]r_p_01_2P;
reg		[PW-1:0]r_p_01_3P;
wire	[PW-1:0]w_p_4;		//主 RAM  A 口，READ_FIRST 读本 bank 旧内容 -> 行 N-4
wire	[PW-1:0]w_p_1;		//主 RAM  B 口                        -> 行 N-1
wire	[PW-1:0]w_p_2;		//辅助 RAM_p2                         -> 行 N-2
wire	[PW-1:0]w_p_3;		//辅助 RAM_p3                         -> 行 N-3
reg		[PW-1:0]r_p_00_2P;
reg		[PW-1:0]r_p_00_3P;

generate
	if (HOR_SYNC_POLARITY == "NEGATIVE")
	begin
		assign	c_ina_hs_por	= 1'b1;
	end
	else
	begin
		assign	c_ina_hs_por	= 1'b0;
	end

	if (VER_SYNC_POLARITY == "NEGATIVE")
	begin
		assign	c_ina_vs_por	= 1'b1;
	end
	else
	begin
		assign	c_ina_vs_por	= 1'b0;
	end
endgenerate

assign	c_ina_de_por	= 1'b0;

// One copy of each line; all four banks read the same column.
reg [1:0] bank_1P,bank_2P;
wire [PW-1:0] bank_q[0:3];
always @(posedge i_pclk) begin
 bank_1P<=r_addr1_sel; bank_2P<=bank_1P;
end
genvar bank;
generate for(bank=0;bank<4;bank=bank+1) begin: line_bank
 (* syn_ramstyle="block_ram" *) reg [PW-1:0] pixels[0:(1<<X_CNT_WIDTH)-1];
 reg [PW-1:0] q1,q2;
 always @(posedge i_pclk) begin
  if(i_valid && r_addr1_sel==bank) pixels[r_addr1]<=i_p;
  q1<=pixels[r_addr1]; q2<=q1;
 end
 assign bank_q[bank]=q2;
end endgenerate
assign w_p_4=bank_q[bank_2P];
wire [1:0] previous_1=bank_2P-2'd1,previous_2=bank_2P-2'd2,previous_3=bank_2P-2'd3;
assign w_p_1=bank_q[previous_1];
assign w_p_2=bank_q[previous_2];
assign w_p_3=bank_q[previous_3];

always@(posedge i_pclk)
begin
	if (~i_arstn)
	begin
		r_vsync_1P		<= c_ina_vs_por;
		r_vsync_2P		<= c_ina_vs_por;
		r_hsync1_1P		<= c_ina_hs_por;
		r_hsync1_2P		<= c_ina_hs_por;
		r_de_1P			<= c_ina_de_por;
		r_de_2P			<= c_ina_de_por;
		r_valid_1P		<= c_ina_de_por;
		r_valid_2P		<= c_ina_de_por;
		r_p_01_0P		<= {PW{1'b0}};
		r_p_01_1P		<= {PW{1'b0}};
	end else begin
		r_vsync_1P		<= i_vsync;
		r_vsync_2P		<= r_vsync_1P;
		r_hsync1_1P		<= i_hsync;
		r_hsync1_2P		<= r_hsync1_1P;
		r_de_1P			<= i_de;
		r_de_2P			<= r_de_1P;
		r_valid_1P		<= i_valid;
		r_valid_2P		<= r_valid_1P;
		r_p_01_0P		<= i_p;
		r_p_01_1P		<= r_p_01_0P;
	end
end
/* Resync data count and insert sync delay */
always@(posedge i_pclk)
begin
	if (~i_arstn)
	begin
		r_addr1			<= {X_CNT_WIDTH{1'b0}};
		r_addr1_sel		<= 2'b0;
		r_addr2_r		<= {X_CNT_WIDTH{1'b0}};
	end
	else
	begin
		if (r_vsync_2P && !r_vsync_1P) begin
			r_addr1		<= {X_CNT_WIDTH{1'b0}};
			r_addr1_sel	<= 2'b0;
		end else if (!r_de_1P && r_de_2P) begin
			r_addr1		<= {X_CNT_WIDTH{1'b0}};
			r_addr1_sel	<= r_addr1_sel + 2'd1;
		end else if (i_valid) begin
			r_addr1		<= r_addr1+1'b1;
		end
		r_addr2_r		<= r_addr1;//r_addr2;
	end
end

assign	o_vsync	= r_vsync_2P;
assign	o_hsync	= r_hsync1_2P;
assign	o_de	= r_de_2P;
assign	o_valid	= r_valid_2P;
assign	o_p_0	= r_p_01_1P[PW-1:0];
assign	o_p_1	= w_p_1[PW-1:0];
assign	o_p_2	= w_p_2[PW-1:0];
assign	o_p_3	= w_p_3[PW-1:0];
assign	o_p_4	= w_p_4[PW-1:0];
assign	o_x		= {r_addr2_r};

endmodule
