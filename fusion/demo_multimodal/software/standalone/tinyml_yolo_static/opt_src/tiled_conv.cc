#define YOLO_DRIVER_IMPLEMENTATION
#include "tiled_conv.h"
#include "platform/tinyml/ops/conv.h"
#include "compat_runtime.h"
#include "port.h"
#include <algorithm>
#include <cstring>

// Bound the protected filter working set to avoid thrashing the 16 KiB
// accelerator cache (32 KiB in the live build). Each tile is an exact, independent set of output channels;
// there is no change to weights, bias, quantization, or accumulator ordering.
unsigned conv_tile_weight_bytes=8192;
namespace {
alignas(64) int8_t tile_output[96*96*32];
alignas(64) int8_t first_columns[96*96*108];
alignas(64) int8_t first_filter[32*3*3*16];
unsigned selected_budget[kNodeCount];
bool tuned[kNodeCount];
const int8_t* packed_filter=nullptr;
int packed_channels=0;
uint64_t timer_ticks() {
  auto* t=reinterpret_cast<volatile uint32_t*>(0xf8b0bff8u);unsigned hi,lo,again;
  do {hi=t[1];lo=t[0];again=t[1];}while(hi!=again);
  return (uint64_t(hi)<<32)|lo;
}
}

static OP_STATUS_T tiled_conv_impl(int sw,int sh,int dw,int dh,int pw,int ph,
    int32_t input_offset,int32_t output_offset,int batches,int ci,int co,
    int iw,int ih,int kw,int kh,int ow,int oh,int32_t amin,int32_t amax,
    const int32_t* multiplier,const int32_t* shift,const int8_t* input,
    const int8_t* filter,const int32_t* bias,const int32_t* input_shape,
    const int32_t* output_shape,const int32_t* filter_shape,int8_t* output) {
  // Exact space-to-depth: a stride-2 6x6 RGB convolution becomes a stride-1
  // 3x3 convolution with 12 useful channels (padded to 16 DSP lanes). Each
  // source pixel is packed only once instead of being copied into 36 windows.
  if(batches==1&&ci==3&&co<=32&&kw==6&&kh==6&&sw==2&&sh==2&&dw==1&&dh==1&&
      iw%2==0&&ih%2==0&&pw%2==0&&ph%2==0&&unsigned(iw/2*ih/2*16)<=sizeof(first_columns)) {
    const int w=iw/2,h=ih/2;
    const uint32_t pad=uint8_t(-input_offset)*0x01010101u;
    for(int y=0;y<h;++y)for(int x=0;x<w;++x) {
      auto* d=first_columns+(y*w+x)*16;
      __builtin_memcpy(d,input+((y*2)*iw+x*2)*3,6);
      __builtin_memcpy(d+6,input+((y*2+1)*iw+x*2)*3,6);
      __builtin_memcpy(d+12,&pad,4);
    }
    // TFLM model weights are immutable for the life of this interpreter.
    // Keep the exact transformed filter resident across both rescue passes.
    if(packed_filter!=filter||packed_channels!=co){
      memset(first_filter,0,co*3*3*16);
      for(int o=0;o<co;++o)for(int ky=0;ky<3;++ky)for(int kx=0;kx<3;++kx)
        for(int dy=0;dy<2;++dy)
          __builtin_memcpy(first_filter+((o*3+ky)*3+kx)*16+dy*6,
                 filter+((o*6+ky*2+dy)*6+kx*2)*3,6);
      packed_filter=filter;packed_channels=co;
    }
    const int32_t xs[4]={1,h,w,16},ws[4]={co,3,3,16};
    cache_sync();
    const auto status=conv_drv(1,1,1,1,pw/2,ph/2,input_offset,output_offset,1,16,co,
        w,h,3,3,ow,oh,amin,amax,multiplier,shift,first_columns,first_filter,bias,xs,output_shape,ws,output);
    cache_sync();return status;
  }
  // Fold the first 6x6 RGB convolution into 1x1 x 108 channels. This gives
  // the DSP array contiguous input vectors and useful work for every lane.
  // OHWI filter ordering is unchanged, including accumulator ordering.
  if(ci==3&&kw==6&&kh==6&&unsigned(ow*oh*108)<=sizeof(first_columns)) {
    const int depth=108;
    for(int y=0;y<oh;++y)for(int x=0;x<ow;++x) {
      int8_t* dest=first_columns+(y*ow+x)*depth;
      memset(dest,static_cast<int8_t>(-input_offset),depth);
      const int iy=y*sh-ph,ix=x*sw-pw;
      const int first=std::max(0,-ix),last=std::min(kw,iw-ix);
      if(last<=first)continue;
      for(int ky=0;ky<kh;++ky)if(iy+ky>=0&&iy+ky<ih)
        memcpy(dest+(ky*kw+first)*3,input+((iy+ky)*iw+ix+first)*3,(last-first)*3);
    }
    int32_t xs[4]={1,oh,ow,depth},ws[4]={co,1,1,depth};
    cache_sync();
    const auto status=conv_drv(1,1,1,1,0,0,input_offset,output_offset,1,depth,co,
        ow,oh,1,1,ow,oh,amin,amax,multiplier,shift,first_columns,filter,bias,xs,output_shape,ws,output);
    cache_sync();return status;
  }
  const unsigned row=kw*kh*ci;
  if(!conv_tile_weight_bytes || unsigned(co)*row<=conv_tile_weight_bytes)
    return conv_drv(sw,sh,dw,dh,pw,ph,input_offset,output_offset,batches,ci,co,
        iw,ih,kw,kh,ow,oh,amin,amax,multiplier,shift,input,filter,bias,
        input_shape,output_shape,filter_shape,output);
  // Larger channel tiles reuse the same input activation for more outputs.
  // Keep the measured filter working-set budget; only widen when it fits.
  unsigned channels=std::min(64u,std::max(4u,(conv_tile_weight_bytes/row)&~3u));
  if(unsigned(ow*oh)*channels>sizeof(tile_output))channels=std::min(channels,32u);
  if(unsigned(ow*oh)*channels>sizeof(tile_output) || batches!=1) return OP_ERR;
  int32_t ys[4]={1,oh,ow,0}, ws[4]={0,kh,kw,ci};
  for(unsigned first=0;first<unsigned(co);first+=channels) {
    const unsigned count=std::min(channels,unsigned(co)-first);
    ys[3]=ws[0]=count;
    cache_sync();
    const auto status=conv_drv(sw,sh,dw,dh,pw,ph,input_offset,output_offset,
        1,ci,count,iw,ih,kw,kh,ow,oh,amin,amax,multiplier+first,shift+first,
        input,filter+first*row,bias?bias+first:nullptr,input_shape,ys,ws,tile_output);
    cache_sync();
    if(status!=OP_OK) return status;
    if(((reinterpret_cast<uintptr_t>(output)|unsigned(co)|first|count)&3u)==0){
      // NHWC channel tiles are word aligned. Avoid a general memcpy call for
      // each output pixel, including the common four-channel tile case.
      for(int pixel=0;pixel<ow*oh;++pixel){
        auto* d=reinterpret_cast<uint32_t*>(output+pixel*co+first);
        const auto* s=reinterpret_cast<const uint32_t*>(tile_output+pixel*count);
        for(unsigned word=0;word<count/4;++word)d[word]=s[word];
      }
    }else for(int pixel=0;pixel<ow*oh;++pixel)
      memcpy(output+pixel*co+first,tile_output+pixel*count,count);
  }
  return OP_OK;
}

OP_STATUS_T tiled_conv_drv(int sw,int sh,int dw,int dh,int pw,int ph,
    int32_t input_offset,int32_t output_offset,int batches,int ci,int co,
    int iw,int ih,int kw,int kh,int ow,int oh,int32_t amin,int32_t amax,
    const int32_t* multiplier,const int32_t* shift,const int8_t* input,
    const int8_t* filter,const int32_t* bias,const int32_t* input_shape,
    const int32_t* output_shape,const int32_t* filter_shape,int8_t* output) {
  const unsigned saved=conv_tile_weight_bytes;
  auto run=[&](){return tiled_conv_impl(sw,sh,dw,dh,pw,ph,input_offset,output_offset,
      batches,ci,co,iw,ih,kw,kh,ow,oh,amin,amax,multiplier,shift,input,filter,bias,
      input_shape,output_shape,filter_shape,output);};
  if(phase==Phase::Qualify&&!tuned[current_node]&&unsigned(co*kw*kh*ci)>4096) {
#ifdef YOLO_REALTIME
    const unsigned budgets[]={4096,8192,12288,16384,24576,32768};
#else
    const unsigned budgets[]={4096,8192,12288,16384};
#endif
    uint64_t best=~uint64_t(0);unsigned choice=saved;
    for(auto budget:budgets) {
      conv_tile_weight_bytes=budget;cache_sync();const uint64_t t=timer_ticks();
      const auto status=run();cache_sync();const uint64_t elapsed=timer_ticks()-t;
      if(status==OP_OK&&elapsed<best){best=elapsed;choice=budget;}
    }
    selected_budget[current_node]=choice;tuned[current_node]=true;
    log_line("YRAW_TUNE node=%u filter_bytes=%u ticks=%u",current_node,choice,unsigned(best));
  }
  if(tuned[current_node])conv_tile_weight_bytes=selected_budget[current_node];
  const auto status=run();conv_tile_weight_bytes=saved;return status;
}
