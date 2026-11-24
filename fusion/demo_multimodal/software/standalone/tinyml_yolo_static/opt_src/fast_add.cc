#define YOLO_DRIVER_IMPLEMENTATION
#include "fast_add.h"
#include "port.h"
#include "tensorflow/lite/kernels/internal/reference/integer_ops/add.h"

namespace {
// Exact truth table of the original quantized ADD for each residual node.
// It contains all 65536 possible input pairs; no arithmetic is approximated.
alignas(64) int8_t tables[8][65536];
alignas(64) int32_t unary[8][2][256];
bool use_unary[8];
unsigned slots[kNodeCount],used;
uint64_t ticks() {
  auto* timer=reinterpret_cast<volatile uint32_t*>(0xf8b0bff8u);
  uint32_t hi,lo,again;
  do {hi=timer[1];lo=timer[0];again=timer[1];}while(hi!=again);
  asm volatile("":::"memory");return (uint64_t(hi)<<32)|lo;
}
int8_t finish(int32_t sum,int32_t multiplier,int32_t shift,int32_t offset,int32_t amin,int32_t amax) {
  const int32_t value=tflite::MultiplyByQuantizedMultiplierSmallerThanOneExp(sum,multiplier,shift)+offset;
  return int8_t(std::min(amax,std::max(amin,value)));
}
__attribute__((noinline)) void pairs(int size,const int8_t* x,const int8_t* y,int8_t* out,const int8_t* lut) {
  for(int i=0;i<size;++i)out[i]=lut[(unsigned(uint8_t(x[i]))<<8)|uint8_t(y[i])];
}
__attribute__((noinline)) void separated(int size,const int8_t* x,const int8_t* y,int8_t* out,
    const int32_t* a,const int32_t* b,int32_t m,int32_t s,int32_t o,int32_t amin,int32_t amax) {
  for(int i=0;i<size;++i)out[i]=finish(a[uint8_t(x[i])]+b[uint8_t(y[i])],m,s,o,amin,amax);
}
}
OP_STATUS_T exact_lut_add(int size,const int8_t* x,const int8_t* y,int8_t* out,
    int32_t xo,int32_t yo,int32_t zo,int32_t zm,int32_t zs,int32_t ls,
    int32_t xm,int32_t xs,int32_t ym,int32_t ys,int32_t amin,int32_t amax) {
  if(!driver_enabled)return OP_ERR;
  unsigned slot=slots[current_node];
  if(!slot) {
    if(used==8)return OP_ERR;
    slots[current_node]=slot=++used;
    tflite::ArithmeticParams p;
    p.input1_offset=xo;p.input2_offset=yo;p.output_offset=zo;
    p.output_multiplier=zm;p.output_shift=zs;p.left_shift=ls;
    p.input1_multiplier=xm;p.input1_shift=xs;p.input2_multiplier=ym;p.input2_shift=ys;
    p.quantized_activation_min=amin;p.quantized_activation_max=amax;
    for(unsigned a=0;a<256;++a) {
      unary[slot-1][0][a]=tflite::MultiplyByQuantizedMultiplierSmallerThanOneExp((int8_t(a)+xo)*(1<<ls),xm,xs);
      unary[slot-1][1][a]=tflite::MultiplyByQuantizedMultiplierSmallerThanOneExp((int8_t(a)+yo)*(1<<ls),ym,ys);
    }
    for(unsigned a=0;a<256;++a)for(unsigned b=0;b<256;++b)
      tables[slot-1][(a<<8)|b]=tflite::reference_integer_ops::AddFunc(int8_t(a),int8_t(b),p);
    for(unsigned a=0;a<256;++a)for(unsigned b=0;b<256;++b)
      if(finish(unary[slot-1][0][a]+unary[slot-1][1][b],zm,zs,zo,amin,amax)!=tables[slot-1][(a<<8)|b])
        compat_fatal("add_separated_reference");
    uint64_t pair_ticks=~uint64_t(0),unary_ticks=pair_ticks;
    for(unsigned trial=0;trial<2;++trial) {
      uint64_t t=ticks();pairs(size,x,y,out,tables[slot-1]);pair_ticks=std::min(pair_ticks,ticks()-t);
      t=ticks();separated(size,x,y,out,unary[slot-1][0],unary[slot-1][1],zm,zs,zo,amin,amax);
      unary_ticks=std::min(unary_ticks,ticks()-t);
    }
    use_unary[slot-1]=unary_ticks<pair_ticks;
    log_line("YRAW_ADD_TUNE node=%u method=%s pair_ticks=%u separated_ticks=%u exhaustive_pairs=65536",
        current_node,use_unary[slot-1]?"SEPARATED":"PAIR_LUT",unsigned(pair_ticks),unsigned(unary_ticks));
  }
  if(use_unary[slot-1])separated(size,x,y,out,unary[slot-1][0],unary[slot-1][1],zm,zs,zo,amin,amax);
  else pairs(size,x,y,out,tables[slot-1]);
  node_used_software_fast=true;return OP_OK;
}
