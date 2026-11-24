`timescale 1ns/1ps
module panel_text_equivalence_tb;
 reg clk=0,reset=1;
 always #5 clk=~clk;
 reg [11:0] h=0,v=0;
 reg [447:0] record_data=0;
 reg [95:0] metrics=0;
 reg [19:0] temp=0,hum=0;
 reg [2:0] mode=0,status=0;
 reg valid=0,live=0,present=0,sign_value=0;
 reg [11:0] fps=0;
 wire [23:0] rgb,reference_rgb;
 multimodal_panel dut(.clk(clk),.reset(reset),.h(h),.v(v),.ready(1'b0),.result(3'd0),.negative(1'b0),
  .t_bcd(20'd0),.h_bcd(20'd0),.cpu_clk(clk),.cpu_request(1'b0),.cpu_record(448'd0),.display_ack(),
  .image_we(1'b0),.image_address(11'd0),.image_data(8'd0),.person_live(live),.person_present(present),
  .metrics(metrics),.power_mode(mode),.camera_fps_valid(valid),.camera_fps_bcd(fps),.rgb(rgb));
 multimodal_panel_reference reference(.clk(clk),.reset(reset),.h(h),.v(v),.ready(1'b0),.result(3'd0),.negative(1'b0),
  .t_bcd(20'd0),.h_bcd(20'd0),.cpu_clk(clk),.cpu_request(1'b0),.cpu_record(448'd0),.display_ack(),
  .image_we(1'b0),.image_address(11'd0),.image_data(8'd0),.person_live(live),.person_present(present),
  .metrics(metrics),.power_mode(mode),.camera_fps_valid(valid),.camera_fps_bcd(fps),.rgb(reference_rgb));
 integer sample,line,col,checks=0;
 reg [7:0] expected;
 initial begin
  repeat(5)@(negedge clk);reset=0;
  force dut.record_frame=record_data;force reference.record_frame=record_data;
  force dut.ir_age=0;force reference.ir_age=0;
  force dut.frame_status=status;force reference.frame_status=status;
  force dut.frame_sign=sign_value;force reference.frame_sign=sign_value;
  force dut.frame_t=temp;force reference.frame_t=temp;
  force dut.frame_h=hum;force reference.frame_h=hum;
  for(sample=0;sample<64;sample=sample+1)begin
   status=sample%3;sign_value=sample%2;live=(sample/2)%2;present=(sample/4)%2;
   valid=(sample/8)%2;mode=sample%6;
   temp={$random};hum={$random};fps={$random};metrics={$random,$random,$random};
   record_data={$random,$random,$random,$random,$random,$random,$random,$random,$random,$random,$random,$random,$random,$random};
   record_data[3:0]=sample%2;
   for(line=0;line<14;line=line+1)for(col=0;col<40;col=col+1)begin
    @(negedge clk);
    if(line<4)begin h=32+col*16;v=920+line*32;end
    else if(line<12)begin h=1360+col*16;v=608+(line-4)*32;end
    else begin h=32+col*16;v=64+(line-12)*32;end
    #1;expected=reference.select_character(reference.text_line,col);
    if(dut.next_character!==expected)$fatal(1,"text differs sample=%0d line=%0d col=%0d got=%h expected=%h",sample,line,col,dut.next_character,expected);
    @(posedge clk);#1;
    if(dut.character!==expected)$fatal(1,"registered character differs");
    checks=checks+1;
   end
  end
  $display("PASS panel text equivalence: %0d characters including numeric fields, validity, modes and pipeline",checks);$finish;
 end
 initial begin #1000000;$fatal(1,"text comparison timeout");end
endmodule
