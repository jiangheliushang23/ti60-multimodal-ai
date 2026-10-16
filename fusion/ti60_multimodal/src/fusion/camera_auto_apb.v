// 0xF8105100: software AE/AWB controls. Single outstanding operation per mailbox.
// Bundled data remains held before the request/ack crosses two synchronizers.
// APB reads held data only after busy clears; no full-width duplicate CDC bank.
module camera_auto_apb(
 input wire reset,cpu_clk,isp_clk,sof,
 input wire psel,penable,pwrite,input wire [7:0] paddr,input wire [31:0] pwdata,
 output reg [31:0] prdata,output wire pslverror,
 output reg stats_request,input wire stats_ack,input wire [156:0] stats_held,
 output reg rt_start,rt_read,output reg [15:0] rt_address,output reg [7:0] rt_data,
 input wire rt_busy,rt_done,input wire [2:0] rt_result,input wire [7:0] rt_read_data,
 output reg [9:0] gain_r,gain_b
);
 reg rt_req,rt_ack,wb_req,wb_ack;
 reg [24:0] command;
 reg [19:0] wb_command;
 reg [10:0] response;
 reg sof_toggle;
 (* async_reg="true" *) reg sa1,sa2,ra1,ra2,wa1,wa2,sf1,sf2,busy1,busy2;
 (* async_reg="true" *) reg rq1,rq2,wq1,wq2;
 reg sf_seen,rt_pending;
 reg [15:0] frame_starts;
 wire stats_busy=stats_request!=sa2,command_busy=rt_req!=ra2,wb_busy=wb_req!=wa2;
 wire access=psel&&penable,write=access&&pwrite;
 wire [5:0] index=paddr[7:2];
 wire bad_wb=pwdata[15:0]<128||pwdata[15:0]>512||pwdata[31:16]<128||pwdata[31:16]>512;
 assign pslverror=access&&(paddr[1:0]!=0||
  (pwrite? !(index==2||index==14||index==15||index==17)||
    (index==2&&stats_busy)||(index==14&&command_busy)||
    (index==15&&(command_busy||busy2))||(index==17&&(wb_busy||bad_wb)):
    index>17));
 always @*begin
  prdata=0;
  case(index)
   0:prdata=32'h41555431;
   1:prdata={28'd0,busy2,wb_busy,command_busy,stats_busy};
   2:prdata={16'd0,stats_held[156:141]};
   3:prdata={10'd0,stats_held[140:119]}; // AE green sum, all selected green pixels
   4:prdata={17'd0,stats_held[118:104]}; // both sampled pixels >=232
   5:prdata={11'd0,stats_held[103:83]};
   6:prdata={19'd0,stats_held[82:70]};
   7:prdata={10'd0,stats_held[69:48]};
   8:prdata={18'd0,stats_held[47:34]};
   9:prdata={11'd0,stats_held[33:13]};
   10:prdata={19'd0,stats_held[12:0]};
   11:prdata=16320; // fixed 1920x1080, every 16px and first two rows of each 16
   12:prdata=32640;
   13:prdata={16'd0,frame_starts};
   14:prdata={7'd0,command};
   16:prdata={21'd0,response};
   17:prdata={6'd0,gain_b,6'd0,gain_r};
  endcase
 end
 always @(posedge cpu_clk or posedge reset)begin
  if(reset)begin
   stats_request<=0;rt_req<=0;wb_req<=0;command<=0;wb_command<={10'd256,10'd256};
   sa1<=0;sa2<=0;ra1<=0;ra2<=0;wa1<=0;wa2<=0;sf1<=0;sf2<=0;sf_seen<=0;
   busy1<=1;busy2<=1;frame_starts<=0;
  end else begin
   sa1<=stats_ack;sa2<=sa1;ra1<=rt_ack;ra2<=ra1;wa1<=wb_ack;wa2<=wa1;
   sf1<=sof_toggle;sf2<=sf1;busy1<=rt_busy;busy2<=busy1;
   if(sf_seen!=sf2)begin sf_seen<=sf2;frame_starts<=frame_starts+1'b1;end
   if(write&&!pslverror)case(index)
    2:stats_request<=~stats_request;
    14:command<=pwdata[24:0];
    15:rt_req<=~rt_req;
    17:begin wb_command<={pwdata[25:16],pwdata[9:0]};wb_req<=~wb_req;end
   endcase
  end
 end
 always @(posedge isp_clk or posedge reset)begin
  if(reset)begin
   rq1<=0;rq2<=0;wq1<=0;wq2<=0;rt_ack<=0;wb_ack<=0;rt_pending<=0;
   rt_start<=0;rt_read<=0;rt_address<=0;rt_data<=0;response<=0;
   sof_toggle<=0;gain_r<=256;gain_b<=256;
  end else begin
   rq1<=rt_req;rq2<=rq1;wq1<=wb_req;wq2<=wq1;rt_start<=0;
   if(sof)begin
    sof_toggle<=~sof_toggle;
    if(wq2!=wb_ack)begin gain_r<=wb_command[9:0];gain_b<=wb_command[19:10];wb_ack<=wq2;end
   end
   if(!rt_pending&&rq2!=rt_ack&&!rt_busy)begin
    {rt_read,rt_data,rt_address}<=command;rt_start<=1;rt_pending<=1;
   end
   if(rt_pending&&rt_done)begin response<={rt_result,rt_read_data};rt_ack<=rq2;rt_pending<=0;end
  end
 end
endmodule
