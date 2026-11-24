#pragma once
#include <cstdint>
#include <cstring>

// All timestamps use the FPGA/APB video millisecond clock. Signed differences
// are valid across wrap for the short retention/tolerance windows used here.
namespace multimodal_alignment {
inline int delta(unsigned a,unsigned b){return int32_t(a-b);}
inline unsigned distance(unsigned a,unsigned b){int d=delta(a,b);return d<0?unsigned(-int64_t(d)):unsigned(d);}
struct Environment {unsigned time_ms=0,sequence=0;int temperature=0,humidity=0;bool valid=false;};
struct Infrared {unsigned time_ms=0,sequence=0,page=0;int16_t temperature[384];bool valid=false;};
struct Result {
 unsigned video_ms=0,video_sequence=0;bool infrared_valid=false,environment_valid=false;
 unsigned ir_ms[2]={0,0},ir_sequence[2]={0,0};int ir_delta_ms[2]={0,0};
 unsigned env_ms=0,env_sequence=0;int env_delta_ms=0,env_temperature=0,env_humidity=0;
 int minimum=0,maximum=0,center=0;int16_t temperature[768];
};
struct History {
 static const unsigned kIrToleranceMs=350,kEnvToleranceMs=1500;
 Infrared ir[32];Environment env[8];unsigned ir_next=0,env_next=0;
 bool chess=true;
 void reset(){for(auto& s:ir)s.valid=false;for(auto& s:env)s.valid=false;ir_next=env_next=0;}
 void invalidate_ir(){for(auto& s:ir)s.valid=false;}
 void invalidate_env(){for(auto& s:env)s.valid=false;}
 void push_ir(unsigned time,unsigned seq,unsigned page,bool chess_mode,const int16_t* values){
  if(chess!=chess_mode){invalidate_ir();chess=chess_mode;}
  auto& s=ir[ir_next++%32];s.time_ms=time;s.sequence=seq;s.page=page;s.valid=true;
  unsigned n=0;for(unsigned i=0;i<768;++i)if((((i/32)&1)^(chess?(i&1):0))==page)s.temperature[n++]=values[i];
 }
 void push_env(unsigned time,unsigned seq,int t,int h){auto& s=env[env_next++%8];s.time_ms=time;s.sequence=seq;s.temperature=t;s.humidity=h;s.valid=true;}
 void match(unsigned video,unsigned sequence,Result& out,unsigned ir_tolerance_ms=kIrToleranceMs)const{
  out=Result{};out.video_ms=video;out.video_sequence=sequence;
  const Infrared* nearest[2]={nullptr,nullptr};unsigned best[2]={~0u,~0u};
  for(const auto& s:ir)if(s.valid){const unsigned d=distance(s.time_ms,video);
   if(d<best[s.page]){best[s.page]=d;nearest[s.page]=&s;}}
  if(nearest[0]&&nearest[1]&&best[0]<=ir_tolerance_ms&&best[1]<=ir_tolerance_ms){
   out.infrared_valid=true;unsigned n[2]={0,0};out.minimum=30000;out.maximum=-4000;
   for(unsigned page=0;page<2;++page){out.ir_ms[page]=nearest[page]->time_ms;out.ir_sequence[page]=nearest[page]->sequence;out.ir_delta_ms[page]=delta(out.ir_ms[page],video);}
   for(unsigned i=0;i<768;++i){unsigned page=((i/32)&1)^(chess?(i&1):0);
    const int t=nearest[page]->temperature[n[page]++];out.temperature[i]=t;
    if(t<out.minimum)out.minimum=t;if(t>out.maximum)out.maximum=t;
   }out.center=out.temperature[12*32+16];
  }
  const Environment* e=nullptr;unsigned best_env=~0u;
  for(const auto& s:env)if(s.valid){const unsigned d=distance(s.time_ms,video);if(d<best_env){best_env=d;e=&s;}}
  if(e&&best_env<=kEnvToleranceMs){out.environment_valid=true;out.env_ms=e->time_ms;out.env_sequence=e->sequence;
   out.env_delta_ms=delta(e->time_ms,video);out.env_temperature=e->temperature;out.env_humidity=e->humidity;}
 }
};
}
