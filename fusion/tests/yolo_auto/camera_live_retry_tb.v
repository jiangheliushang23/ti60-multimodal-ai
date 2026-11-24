`timescale 1ns/1ps
module camera_live_retry_tb;
 reg clk=0,reset=1;always #5 clk=~clk;
 reg [31:0] status=0;wire frontend_reset;wire [3:0] retries;
 camera_setup_retry #(.WAIT_CYCLES(9),.RESET_CYCLES(3),.MAX_RETRIES(2)) dut(
  .clk(clk),.reset(reset),.setup_status(status),.frontend_reset(frontend_reset),.retries(retries));
 task tick;begin @(negedge clk);end endtask
 initial begin
  repeat(3)tick();reset=0;
  repeat(30)tick();if(frontend_reset||retries)$fatal(1,"reset without setup failure");
  status=32'h50;
  repeat(8)tick();if(frontend_reset)$fatal(1,"retry before settling delay");
  tick();if(!frontend_reset||retries!=1)$fatal(1,"first retry missing");
  repeat(2)tick();if(!frontend_reset)$fatal(1,"reset pulse too short");
  tick();if(frontend_reset)$fatal(1,"reset pulse too long");
  status=32'hbe1f;repeat(40)tick();if(retries!=1||frontend_reset)$fatal(1,"retried successful setup");
  status=32'h50;repeat(9)tick();if(!frontend_reset||retries!=2)$fatal(1,"second retry missing");
  repeat(100)tick();if(frontend_reset||retries!=2)$fatal(1,"retry limit ignored");
  reset=1;tick();reset=0;status=0;tick();if(retries)$fatal(1,"POR did not clear retry count");
  $display("PASS CAMERA retry: bounded retries, settling delay, reset width and successful setup");$finish;
 end
 initial begin #10000;$fatal(1,"timeout");end
endmodule
