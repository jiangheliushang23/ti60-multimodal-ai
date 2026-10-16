`timescale 1ns/1ps
module control_reference_tb;
 reg clk=0,reset=1,ready=0,frame=0,stats_done=0;
 always #5 clk=~clk;
 reg [383:0] stats=0;wire request;wire [15:0] gain_r,gain_b;
 sc_auto_control #(.ENABLE_AWB(1)) dut(.clk(clk),.reset(reset),.ready(ready),.mode_ok(1'b1),.frame_start(frame),
  .stats(stats),.stats_done(stats_done),.stats_request(request),.rt_busy(1'b0),.rt_done(1'b0),.rt_result(3'd0),.rt_read_data(8'd0),
  .gain_r(gain_r),.gain_b(gain_b));
 integer f,o,n,k=0,ae,ac,clip,total,rs,rc,gs,gc,bs,bc,exp,gain,r,b;
 reg [1023:0] input_path,output_path;
 initial begin
  if(!$value$plusargs("INPUT=%s",input_path)||!$value$plusargs("OUTPUT=%s",output_path))$fatal(1,"paths");
  f=$fopen(input_path,"r");o=$fopen(output_path,"w");if(!f||!o)$fatal(1,"open");
  while(!$feof(f))begin
   n=$fscanf(f,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",ae,ac,clip,total,rs,rc,gs,gc,bs,bc,exp,gain,r,b);
   if(n==14)begin
    reset=1;ready=0;stats_done=0;frame=0;repeat(2)@(negedge clk);
    reset=0;ready=1;dut.exposure=exp;dut.gain_index=gain;dut.gain_r=r;dut.gain_b=b;
    frame=1;@(negedge clk);frame=0;
    wait(request);@(negedge clk);stats={32'd1,32'd0,ae,ac,clip,total,rs,rc,gs,gc,bs,bc};stats_done=1;
    @(negedge clk);stats_done=0;
    wait(dut.state==4);repeat(2)@(negedge clk);
    $fwrite(o,"%0d %0d %0d %0d %0d\n",dut.next_exposure,dut.next_gain_index,gain_r,gain_b,dut.state==5);
    k=k+1;
   end
  end
  $fclose(f);$fclose(o);$display("PASS %0d CPU comparison reference cases",k);$finish;
 end
 initial begin #100000000;$fatal(1,"timeout");end
endmodule
