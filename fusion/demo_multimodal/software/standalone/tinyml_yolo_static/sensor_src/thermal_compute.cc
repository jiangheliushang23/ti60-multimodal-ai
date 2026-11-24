// Adapted compensation equations from Melexis MLX90640_API.cpp (Apache-2.0).
// The original reference implementation remains in the project for regression.
#include <cmath>
#include <cstdint>
#include "thermal_compute.h"

namespace {
const uint32_t root_q24[4][513]={
#include "thermal_root_lut.inc"
};
float power4(float x){const float y=x*x;return y*y;}
}

float ThermalCompute::fourth_root(float x){
 union {float f;uint32_t u;} bits={x};
 if(!(bits.u&0x7fffffffu))return x;
 const unsigned exponent=(bits.u>>23)&255u;
 if(exponent==255u&&((bits.u&0x7fffffu)||!(bits.u>>31)))return x;
 if(bits.u>>31)return NAN;
 unsigned mantissa=bits.u&0x7fffffu;
 int e=int(exponent)-127;
 if(!exponent){
  e=-126;while(!(mantissa&0x800000u)){mantissa<<=1;--e;}mantissa&=0x7fffffu;
 }
 int q=e/4,r=e%4;if(r<0){r+=4;--q;}
 const unsigned index=mantissa>>14,fraction=mantissa&16383u;
 const uint32_t* table=root_q24[r];
 const uint32_t q24=table[index]+((table[index+1]-table[index])*fraction+8192u)/16384u;
 // The four tables include the exponent remainder. Assemble a rounded IEEE
 // mantissa directly: no software floating multiply/conversion for each root.
 bits.u=uint32_t(q+127)*8388608u+((q24+1u)>>1)-8388608u;
 return bits.f;
}

void ThermalCompute::calibrate(const paramsMLX90640& p){
 const float scale=std::ldexp(0.000001f,p.alphaScale);
 for(unsigned i=0;i<768;++i)alpha_base[i]=p.alpha[i]?scale/p.alpha[i]:0.0f;
}

bool ThermalCompute::prepare(uint16_t* f,const paramsMLX90640& p,float emissivity,float reflected_offset){
 if(!int16_t(f[778])||!(emissivity>0.0f&&emissivity<=1.0f))return false;
 supply=MLX90640_GetVdd(f,&p);ambient=MLX90640_GetTa(f,&p);
 if(!std::isfinite(supply)||supply<2.5f||supply>4.0f||!std::isfinite(ambient)||ambient< -40.0f||ambient>125.0f)return false;
 inv_emissivity=1.0f/emissivity;
 const float tr4=power4(ambient+reflected_offset+273.15f),ta4=power4(ambient+273.15f);
 ta_tr=tr4-(tr4-ta4)*inv_emissivity;
 gain=float(p.gainEE)/int16_t(f[778]);page=f[833]&1u;mode=(f[832]&0x1000u)>>5;
 const float dt=ambient-25.0f,dv=supply-3.3f;
 kta_ta=std::ldexp(dt,-int(p.ktaScale));kv_vdd=std::ldexp(dv,-int(p.kvScale));
 alpha_ta=1.0f+p.KsTa*dt;
 const float cp_offset=float(p.cpOffset[page])+((page&&mode!=p.calibrationModeEE)?p.ilChessC[0]:0.0f);
 cp=p.tgc*(int16_t(f[page?808:776])*gain-cp_offset*(1.0f+p.cpKta*dt)*(1.0f+p.cpKv*dv));
 alpha_range[0]=1.0f/(1.0f+p.ksTo[0]*40.0f);alpha_range[1]=1.0f;
 alpha_range[2]=1.0f+p.ksTo[1]*p.ct[2];alpha_range[3]=alpha_range[2]*(1.0f+p.ksTo[2]*(p.ct[3]-p.ct[2]));
 return std::isfinite(ta_tr)&&std::isfinite(gain)&&std::isfinite(cp);
}

void ThermalCompute::calculate(const uint16_t* f,const paramsMLX90640& p,float* out,unsigned first,unsigned count)const{
 const unsigned last=first+count<768?first+count:768;
 for(unsigned i=first;i<last;++i){
  const int row=(i/32)&1;const unsigned pattern=mode?(row^(i&1)):row;
  if(pattern!=page)continue;
  float ir=int16_t(f[i])*gain-p.offset[i]*(1.0f+p.kta[i]*kta_ta)*(1.0f+p.kv[i]*kv_vdd);
  if(mode!=p.calibrationModeEE){
   const int conversion=(int((i+2)/4)-int((i+3)/4)+int((i+1)/4)-int(i/4))*(1-2*row);
   ir+=p.ilChessC[2]*(2*row-1)-p.ilChessC[1]*conversion;
  }
  ir=(ir-cp)*inv_emissivity;
  const float alpha=alpha_base[i]*alpha_ta;
  const float sx=fourth_root(alpha*alpha*alpha*(ir+alpha*ta_tr))*p.ksTo[1];
  float to=fourth_root(ir/(alpha*(1.0f-p.ksTo[1]*273.15f)+sx)+ta_tr)-273.15f;
  const unsigned r=to<p.ct[1]?0:to<p.ct[2]?1:to<p.ct[3]?2:3;
  to=fourth_root(ir/(alpha*alpha_range[r]*(1.0f+p.ksTo[r]*(to-p.ct[r])))+ta_tr)-273.15f;
  out[i]=to;
 }
}
