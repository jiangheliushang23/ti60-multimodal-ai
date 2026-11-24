#define YOLO_DRIVER_IMPLEMENTATION
#include "compat_runtime.h"
#include "port.h"
#include "platform/tinyml/ops/mul.h"
#include "tensorflow/lite/kernels/internal/common.h"
#include <algorithm>
#include <cstdlib>

namespace {
bool tested[kNodeCount],safe[kNodeCount];
alignas(64) int8_t input1[65536],input2[65536],actual[65536];
}
bool mul_parameters_verified(int32_t offset1,int32_t offset2,int32_t shift,
                             int32_t multiplier,int32_t output_offset,int32_t maximum,int32_t minimum) {
  if(current_node>=kNodeCount) compat_fatal("mul_node_index");
  if(tested[current_node]) return safe[current_node];
  if(phase!=Phase::Qualify) return false;
  tested[current_node]=true;
  // All 256 * 256 possible INT8 input pairs for this node's real quantization.
  for(unsigned i=0;i<65536;++i) {
    input1[i]=int(i>>8)-128;
    input2[i]=int(i&255)-128;
    actual[i]=0x55;
  }
  const bool previous=node_used_hardware;
  OP_STATUS_T status=OP_OK;
  for(unsigned first=0;first<65536;first+=4096) {
    const auto chunk=hardware_call(mul_drv_elementwise,4096,offset1,offset2,shift,multiplier,
                                    output_offset,maximum,minimum,input1+first,input2+first,actual+first);
    if(chunk!=OP_OK) { status=chunk; break; }
  }
  node_used_hardware=previous;
  unsigned different=0,max_abs=0;
  for(unsigned i=0;i<65536;++i) {
    const int32_t product=(int(input1[i])+offset1)*(int(input2[i])+offset2);
    const int32_t scaled=tflite::MultiplyByQuantizedMultiplier(product,multiplier,shift)+output_offset;
    const int32_t expected=std::min(maximum,std::max(minimum,scaled));
    const unsigned delta=std::abs(int(actual[i])-int(expected));
    different+=delta!=0;
    max_abs=std::max(max_abs,delta);
  }
  safe[current_node]=status==OP_OK && different==0;
  log_line("YOLO2_PARAMCHECK node=%u op=MUL pairs=65536 offset1=%d offset2=%d shift=%d multiplier=%d diff=%u max_abs=%u accepted=%u",
           current_node,int(offset1),int(offset2),int(shift),int(multiplier),different,max_abs,safe[current_node]);
  return safe[current_node];
}
