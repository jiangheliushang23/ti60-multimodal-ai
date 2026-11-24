#include <cmath>
#include "thermal_compute.h"
#include "thermal_range.h"
#include "thermal_rate.h"
extern "C" {
uint16_t ee[832],frame[834];paramsMLX90640 params;
float reference_out[768],fast_out[768],root_in[4096],root_out[4096],emissivity=.95f,reflected_offset=-8.0f;
unsigned root_count=0,scenario=0,math_status=0;
ThermalCompute compute;
void test_extract(){math_status=MLX90640_ExtractParameters(ee,&params);}
void test_scenario(){
 // Nonzero EEPROM coefficients exercise all corrections, both electrical modes,
 // CP/chess mode mismatch and all four object-temperature ranges.
 params.KsTa=(int(scenario%5)-2)*0.0003f;params.tgc=.1f;
 params.cpKta=.001f;params.cpKv=.04f;params.cpOffset[0]=12;params.cpOffset[1]=-9;
 params.ilChessC[0]=2.5f;params.ilChessC[1]=.4f;params.ilChessC[2]=.7f;
 params.ksTo[0]=-.0002f;params.ksTo[1]=-.0001f;params.ksTo[2]=-.00012f;params.ksTo[3]=-.00015f;
 params.ct[0]=-40;params.ct[1]=0;params.ct[2]=80;params.ct[3]=120;
 params.calibrationModeEE=(scenario&2)?128:0;
 params.ktaScale=12;params.kvScale=8;
 for(unsigned i=0;i<768;++i){params.kta[i]=int(i%15)-7;params.kv[i]=int(i%7)-3;}
 frame[832]=(frame[832]&~0x1000u)|((scenario&1)?0x1000u:0);
 frame[833]=(scenario>>2)&1;
 const float vdd_target=3.0f+.2f*(scenario%4);
 const float resolution=std::ldexp(1.0f,int(params.resolutionEE)-int((frame[832]>>10)&3));
 frame[810]=int16_t(std::round((params.vdd25+(vdd_target-3.3f)*params.kVdd)/resolution));
 params.KvPTAT=.02f;
 const float target_ta=(scenario/32)==0?-15.0f:(scenario/32)==1?25.0f:70.0f;
 const float art=(params.vPTAT25+(target_ta-25.0f)*params.KtPTAT)*(1.0f+params.KvPTAT*(MLX90640_GetVdd(frame,&params)-3.3f));
 const float ptat=int16_t(frame[800]);
 frame[768]=int16_t(std::round(ptat*262144.0f/art-ptat*params.alphaPTAT));
 emissivity=(scenario&8)?.85f:.95f;reflected_offset=(scenario&16)?-15.0f:-8.0f;
}
void test_calibrate(){compute.calibrate(params);}
void test_reference(){
 const float ta=MLX90640_GetTa(frame,&params);
 for(unsigned i=0;i<768;i+=32)MLX90640_CalculateToRange(frame,&params,emissivity,ta+reflected_offset,reference_out,i,32);
}
void test_fast(){
 math_status=compute.prepare(frame,params,emissivity,reflected_offset)?0:1;
 if(math_status)return;
 for(unsigned i=0;i<768;i+=192)compute.calculate(frame,params,fast_out,i,192);
}
void test_roots(){for(unsigned i=0;i<root_count;++i)root_out[i]=ThermalCompute::fourth_root(root_in[i]);}
void test_rate(){
 ThermalRate rate;
 for(unsigned i=0;i<=32;++i)rate.acknowledge(0xfffffff0u+i*125u,i&1);
 math_status=(rate.updates_tenths==80&&rate.pairs_tenths==40)?0:1;
 rate.reset();for(unsigned i=0;i<=16;++i)rate.acknowledge(i*125u,0);
 if(rate.updates_tenths!=80||rate.pairs_tenths!=0)math_status|=2;
}
}
