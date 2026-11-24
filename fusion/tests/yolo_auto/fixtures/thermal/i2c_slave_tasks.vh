 task wait_start;
 begin : waiting
  forever begin @(negedge sda); if(scl===1'b1) disable waiting; end
 end endtask
 task wait_stop;
 begin : waiting
  forever begin @(posedge sda); if(scl===1'b1) disable waiting; end
 end endtask
 task receive;
 input [7:0] expected; input nack; reg [7:0] value; integer b;
 begin
  for(b=7;b>=0;b=b-1) begin @(posedge scl); #1; value[b]=sda; @(negedge scl); end
  if(value!==expected) $fatal(1,"I2C sent %h expected %h",value,expected);
  #1; slave_sda=!nack;
  @(posedge scl); @(negedge scl); #1; slave_sda=0;
 end endtask
 task transmit;
 input [7:0] value; input expected_nack; integer b;
 begin
  for(b=7;b>=0;b=b-1) begin
   #1; slave_sda=!value[b]; @(posedge scl); @(negedge scl);
  end
  #1; slave_sda=0; @(posedge scl); #1;
  if(sda!==expected_nack) $fatal(1,"Incorrect master ACK/NACK");
  @(negedge scl);
 end endtask
