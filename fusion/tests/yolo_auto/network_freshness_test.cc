#include "multimodal_alignment.h"
extern "C" {
unsigned freshness_out[8];
void freshness_test(){
 multimodal_alignment::History h;multimodal_alignment::Result r;
 int16_t t[768];for(unsigned i=0;i<768;++i)t[i]=2500+i;
 h.push_ir(1000,1,0,true,t);h.push_ir(1250,2,1,true,t);h.push_env(1450,1,2932,5431);
 h.match(1500,1,r);freshness_out[0]=r.infrared_valid;
 h.match(1500,1,r,1000);freshness_out[1]=r.infrared_valid;freshness_out[2]=r.minimum;freshness_out[3]=r.maximum;freshness_out[4]=r.center;
 h.match(2251,2,r,1000);freshness_out[5]=r.infrared_valid;
 h.match(1300,3,r);freshness_out[6]=r.infrared_valid;
 h.invalidate_ir();h.match(1500,4,r,1000);freshness_out[7]=r.infrared_valid;
}
}