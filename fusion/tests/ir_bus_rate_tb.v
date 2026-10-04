`timescale 1ns/1ps
module ir_bus_rate_tb;
 reg clk=0,reset=1,start=0,slave_sda=0,slave_scl=0;
 always #5 clk=~clk; // 100 MHz fusion APB domain.
 wire scl_low,sda_low,busy,done,word_valid;wire [2:0] result;
 wire [15:0] read_data;wire [9:0] word_index;
 wire scl,sda;
 // Open-drain rising edges take 150 ns; falling edges are immediate.
 assign #(150,0) scl=!(scl_low||slave_scl);
 assign #(150,0) sda=!(sda_low||slave_sda);
 mlx90640_bus #(.TICK_CYCLES(100),.TIMEOUT_TICKS(10000)) dut(
  .clk(clk),.reset(reset),.scl_in(scl),.sda_in(sda),.start(start),.read_op(1'b1),
  .reg_addr(16'h0400),.write_data(16'd0),.read_words(10'd832),
  .scl_low(scl_low),.sda_low(sda_low),.busy(busy),.done(done),.result(result),
  .read_data(read_data),.word_valid(word_valid),.word_index(word_index));
 `include "i2c_slave_tasks.vh"
 integer n,received=0;reg [15:0] value;
 realtime last_rise=0,last_fall=0,started;
 always @(posedge scl)begin
  if(last_fall>0&&($realtime-last_fall)<1300)$fatal(1,"Fast-mode SCL low too short");
  last_rise=$realtime;
 end
 always @(negedge scl)begin
  if(last_rise>0&&($realtime-last_rise)<600)$fatal(1,"Fast-mode SCL high too short");
  last_fall=$realtime;
 end
 always @(negedge clk)if(word_valid)begin
  if(word_index!=received||read_data!==(16'h5a5a^word_index))$fatal(1,"Burst data/index mismatch");
  received=received+1;
 end
 initial begin
  repeat(10)@(negedge clk);reset=0;start=1;started=$realtime;
  @(negedge clk);start=0;wait(done);#1;
  if(result!=1||received!=832)$fatal(1,"Burst failed");
  if($realtime-started>65000000)$fatal(1,"Burst slower than 65ms");
  $display("PASS 832-word I2C burst, 150ns rise, clock stretching, fast-mode high/low timing; elapsed=%0.3f ms",($realtime-started)/1000000.0);
  $finish;
 end
 initial begin
  wait_start;receive(8'h66,0);receive(8'h04,0);receive(8'h00,0);
  wait_start;receive(8'h67,0);
  for(n=0;n<832;n=n+1)begin
   value=16'h5a5a^n;transmit(value[15:8],0);transmit(value[7:0],n==831);
  end
  wait_stop;
 end
 initial begin
  wait(received==100);@(negedge scl);slave_scl=1;#2500;slave_scl=0;
 end
 initial begin #70000000;$fatal(1,"I2C rate test timeout");end
endmodule
