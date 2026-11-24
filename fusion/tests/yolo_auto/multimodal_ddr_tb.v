`timescale 1ns/1ps
module camera_live_ddr_tb;
reg cpu_lease_valid=0;reg [1:0] cpu_lease_bank=0;
 reg clk=0,pixel_clk=0,reset=1,sof=0,in_valid=0,complete=0,malformed=0,ev=0;
 always #5 clk=~clk;always #3.367 pixel_clk=~pixel_clk;
 reg [15:0] seq=0;reg [127:0] in_data=0;reg [16:0] ed=0;
 reg request=0,take=0;reg [2:0] pi=0;
 reg [31:0] timestamp=0;wire [31:0] published_time;
 wire [23:0] rgb;wire vv;wire [31:0] published,dropped,we,re,uf;wire [15:0] pubseq;
 wire [31:0] awa,ara;wire [7:0] awl,arl;wire awv,wv,wl,br,arv,rr;
 wire [127:0] wd;wire [15:0] strb;
 reg awr=0,wr=0,bv=0,arr=0,rv=0,rl=0;reg [1:0] bp=0,rp=0;reg [127:0] data_r=0;
 video_ddr #(.BEATS(640),.END_GUARD(32)) dut(.time_gray(timestamp^(timestamp>>1)),.published_time_ms(published_time),.cpu_lease_valid(cpu_lease_valid),.cpu_lease_bank(cpu_lease_bank),.newest_bank(),.newest_valid(),.clk(clk),.reset(reset),.sof(sof),.frame_seq(seq),
  .in_valid(in_valid),.in_data(in_data),.complete(complete),.malformed(malformed),.end_valid(ev),.end_data(ed),
  .pixel_clk(pixel_clk),.frame_request(request),.video_take(take),.pixel_index(pi),.video_rgb(rgb),.video_valid(vv),
  .published(published),.published_seq(pubseq),.dropped(dropped),.write_errors(we),.read_errors(re),.underflows(uf),
  .awaddr(awa),.awlen(awl),.awvalid(awv),.awready(awr),.wdata(wd),.wstrb(strb),.wlast(wl),.wvalid(wv),.wready(wr),
  .bresp(bp),.bvalid(bv),.bready(br),.araddr(ara),.arlen(arl),.arvalid(arv),.arready(arr),
  .rdata(data_r),.rresp(rp),.rlast(rl),.rvalid(rv),.rready(rr));
 reg [127:0] memory[0:1919];integer wi=0,ri=0,wn=0,rn=0;
 reg write_busy=0,read_busy=0,inject_b=0,inject_r=0,pause_r=0,pause_w=0;
 reg [31:0] rng=32'h71394581;
 function integer index;input [31:0] a;integer bank,offset;begin
  bank=(a-32'h06000000)>>21;offset=(a&32'h001fffff)>>4;
  if(a<32'h06000000||bank>2||offset>=640||a[3:0]!=0)$fatal(1,"address outside video banks %h",a);
  index=bank*640+offset;
 end endfunction
 // Independent AXI RAM with random address/data stalls and delayed responses.
 always @(negedge clk)begin
  rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  awr=!write_busy&&!bv&&rng[0]&&!pause_w;wr=write_busy&&rng[2]&&!pause_w;arr=!read_busy&&!rv&&rng[4];
  if(read_busy&&!rv&&!pause_r&&rng[6])begin data_r=memory[ri];rv=1;rl=rn==1;rp=inject_r?2:0;end
 end
 always @(posedge clk)if(!reset)begin
  if(awv&&awr)begin
   wi=index(awa);wn=awl+1;write_busy=1;
   if((awa[11:0]+((awl+1)*16))>4096)$fatal(1,"4K crossing");
   if(cpu_lease_valid&&dut.write_bank==cpu_lease_bank)$fatal(1,"overwriting CPU bank");
if(dut.write_bank==dut.read_bank)$fatal(1,"overwriting display bank");
  end
  if(wv&&wr)begin
   if(!write_busy||strb!=16'hffff||wl!=(wn==1))$fatal(1,"bad write protocol");
   memory[wi]=wd;wi=wi+1;wn=wn-1;
   if(wn==0)begin write_busy=0;bv<=1;bp<=inject_b?2:0;end
  end
  if(bv&&br)bv<=0;
  if(arv&&arr)begin ri=index(ara);rn=arl+1;read_busy=1;end
  if(rv&&rr)begin rv<=0;ri=ri+1;rn=rn-1;if(rn==0)read_busy=0;end
 end
 function [127:0] beat;input integer id,n;integer k;begin
  for(k=0;k<8;k=k+1)beat[k*16+:16]=(id*1024+n*8+k);
 end endfunction
 function [23:0] expand;input [15:0] p;begin expand={{p[15:11],p[15:13]},{p[10:5],p[10:9]},{p[4:0],p[4:2]}};end endfunction
 task send;input integer id,count,bad_sensor;integer j;
 begin
  @(negedge clk);timestamp=id==14?32'hfffffff8:1000+id*33;repeat(6)@(negedge clk);
  seq=id;sof=1;complete=0;malformed=0;
  @(negedge clk);sof=0;timestamp=timestamp+10;repeat(20)@(negedge clk);
  for(j=0;j<count;j=j+1)begin in_valid=1;in_data=beat(id,j);@(negedge clk);in_valid=0;repeat(2)@(negedge clk);end
  in_valid=0;complete=count==640;repeat(4)@(negedge clk);
  ed={16'(id),!bad_sensor};ev=1;@(negedge clk);ev=0;
  repeat(1500)@(negedge clk);
 end endtask
 task show;input integer id;integer j;
 begin
  @(negedge pixel_clk);request=!request;repeat(1600)@(negedge pixel_clk);
  for(j=0;j<5120;j=j+1)begin
   take=1;pi=j%8;#0.01;
   if(!vv||rgb!==expand(16'(id*1024+j)))$fatal(1,"pixel %0d valid=%b got=%h expected=%h",j,vv,rgb,expand(16'(id*1024+j)));
   @(negedge pixel_clk);
  end
  take=0;
 end endtask
 integer before_pub;
 initial begin
  repeat(12)@(negedge clk);reset=0;repeat(40)@(negedge clk);
  send(1,640,0);if(published!=1||we!=0)$fatal(1,"publish normal p=%d drop=%d ws=%d written=%d fifo=%d empty=%b close=%b end=%b seq=%d",published,dropped,dut.ws,dut.written,dut.wf_count,dut.wf_empty,dut.closed,dut.end_seen,dut.seq);
  if(published_time!==1033)$fatal(1,"timestamp must be SOF, not end of frame %h",published_time);
  show(1);
  inject_b=1;send(2,640,0);inject_b=0;if(published!=1||we!=20)$fatal(1,"B error published");
  send(3,45,0);if(published!=1)$fatal(1,"short frame published");
  send(4,640,1);if(published!=1)$fatal(1,"sensor-bad frame published");
  if(published_time!==1033)$fatal(1,"bad frame changed published time");
  show(1);
  send(5,640,0);if(published!=2||pubseq!=5)$fatal(1,"frame recovery");show(5);
  send(6,640,0);show(6);send(7,640,0);show(7);
  inject_r=1;@(negedge pixel_clk);request=!request;repeat(1600)@(negedge pixel_clk);inject_r=0;
  if(re==0||vv)$fatal(1,"read errors not invalidated");
  show(7);
  // Deliberate display FIFO underrun is sticky for the rest of this scan.
  take=1;pi=0;repeat(8)@(negedge pixel_clk);take=0;
  if(uf==0||vv)$fatal(1,"underflow not detected");show(7);
  fork send(8,640,0);show(7);join
  show(8);
  if(published!=5)$fatal(1,"unexpected publication");
  pause_w=1;send(9,640,0);pause_w=0;repeat(3000)@(negedge clk);
  if(published!=5||dut.active)$fatal(1,"overflow not rejected/drained");
  send(10,640,0);show(10);if(published!=6)$fatal(1,"overflow recovery");
  cpu_lease_bank=dut.latest_bank;cpu_lease_valid=1;
  send(11,640,0);show(11);send(12,640,0);
  if(published!=8)$fatal(1,"lease blocked a free bank");
  send(13,640,0);if(published!=8)$fatal(1,"reserved bank overwritten");
  if(memory[cpu_lease_bank*640]!==beat(10,0))$fatal(1,"pinned frame changed");
  cpu_lease_valid=0;send(14,640,0);show(14);
  if(published!=9)$fatal(1,"camera did not recover after lease release");
  if(published_time!==32'hfffffff8)$fatal(1,"wrapped acquisition timestamp corrupted %h",published_time);
  $display("PASS camera_live video_ddr: randomized AXI, protected banks/address bounds, B/R errors, short frames, recovery, underflow");$finish;
 end
 initial begin #5000000;$fatal(1,"timeout ws=%d active=%b count=%d",dut.ws,dut.active,dut.wf_count);end
endmodule


