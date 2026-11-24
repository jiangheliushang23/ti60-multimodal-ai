// Exercise real RV32 packing/tiling/scatter; replace only the protected DSP
// entry with an independent scalar accumulator. No FPGA timing is simulated.
#include "tiled_conv.cc"
Phase phase=Phase::Hybrid;
unsigned current_node=0,node_ms[kNodeCount],hash_failures=0,qualify_failures=0;
bool driver_enabled=true,node_used_hardware=false,node_used_software_fast=false;
bool qualified[kNodeCount],software_qualified[kNodeCount];
const char* fallback_reason=nullptr;
void cache_sync(){}
void log_line(const char*,...){}
extern "C" {
alignas(64) int8_t conv_input[32768],conv_filter[65536],conv_output[8192];
int32_t conv_bias[128],conv_multiplier[128],conv_shift[128];
int32_t conv_args[12];
unsigned conv_result,conv_calls;
}
OP_STATUS_T conv_drv(int sw,int sh,int dw,int dh,int pw,int ph,int32_t io,int32_t oo,
 int batches,int ci,int co,int iw,int ih,int kw,int kh,int ow,int oh,int32_t amin,int32_t amax,
 const int32_t*,const int32_t*,const int8_t* input,const int8_t* filter,const int32_t* bias,
 const int32_t*,const int32_t*,const int32_t*,int8_t* output){
 ++conv_calls;
 for(int y=0;y<oh;++y)for(int x=0;x<ow;++x)for(int o=0;o<co;++o){
  int32_t sum=bias?bias[o]:0;
  for(int ky=0;ky<kh;++ky)for(int kx=0;kx<kw;++kx){
   int sx=x*sw-pw+kx*dw,sy=y*sh-ph+ky*dh;
   if(sx<0||sy<0||sx>=iw||sy>=ih)continue;
   for(int c=0;c<ci;++c)sum+=(int(input[(sy*iw+sx)*ci+c])+io)*int(filter[((o*kh+ky)*kw+kx)*ci+c]);
  }
  output[(y*ow+x)*co+o]=static_cast<int8_t>((sum+oo)&255);
 }
 return OP_OK;
}
extern "C" void run_conv(){
 const int iw=conv_args[0],ih=conv_args[1],ci=conv_args[2],co=conv_args[3],k=conv_args[4],s=conv_args[5],p=conv_args[6];
 const int ow=(iw+2*p-k)/s+1,oh=(ih+2*p-k)/s+1;
 int32_t xs[4]={1,ih,iw,ci},ys[4]={1,oh,ow,co},ws[4]={co,k,k,ci};
 conv_tile_weight_bytes=conv_args[9];conv_calls=0;
 conv_result=tiled_conv_drv(s,s,1,1,p,p,conv_args[7],conv_args[8],1,ci,co,iw,ih,k,k,ow,oh,-128,127,
  conv_multiplier,conv_shift,conv_input,conv_filter+conv_args[11],conv_args[10]?nullptr:conv_bias,xs,ys,ws,conv_output);
}
