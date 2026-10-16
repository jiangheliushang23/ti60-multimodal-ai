#pragma once
#include <stdint.h>

// Integer port of the board-verified sc_auto_control. Statistics precede WB/Gamma.
struct CameraStats {
 uint16_t sequence;
 uint32_t ae_sum,ae_count,clipped,samples,r_sum,r_count,g_sum,g_count,b_sum,b_count;
};
struct CameraDecision {
 uint16_t exposure,gain_r,gain_b;
 uint8_t gain_index,mean,r_mean,g_mean,b_mean;
 bool sensor_update;
};
inline uint16_t camera_gain_code(unsigned index){
 if(index<18)return 0x0020+index;
 if(index<50)return 0x8020+(index-18);
 if(index<82)return 0x8120+(index-50);
 return 0x8320;
}
inline uint16_t camera_smooth(uint16_t current,uint16_t target){
 unsigned delta=current>target?current-target:target-current;
 unsigned step=delta>>3;if(step==0&&delta>4)step=1;
 return delta<=4?current:(current>target?current-step:current+step);
}
inline uint16_t camera_ratio(unsigned green,unsigned chroma){
 unsigned value=chroma?(green<<8)/chroma:0;
 return value<128?128:(value>512?512:value);
}
inline CameraDecision camera_decide(const CameraStats &s,uint16_t exposure,uint8_t gain_index,uint16_t r,uint16_t b){
 CameraDecision d={exposure,r,b,gain_index,0,0,0,0,false};
 d.mean=s.ae_count?s.ae_sum/s.ae_count:0;
 d.r_mean=s.r_count?s.r_sum/s.r_count:0;
 d.g_mean=s.g_count?s.g_sum/s.g_count:0;
 d.b_mean=s.b_count?s.b_sum/s.b_count:0;
 bool bright=d.mean>64||s.clipped*64>s.samples;
 bool dark=d.mean<48&&s.clipped*128<=s.samples;
 unsigned step=exposure>>2;if(step==0)step=1;
 if(bright&&(gain_index!=0||exposure>4)){
  if(gain_index)d.gain_index=gain_index>8?gain_index-8:0;
  else d.exposure=exposure>4+step?exposure-step:4;
  d.sensor_update=true;
 }else if(!bright&&dark&&(exposure<2989||gain_index<82)){
  if(exposure<2989)d.exposure=exposure+step<2989?exposure+step:2989;
  else d.gain_index=gain_index<78?gain_index+4:82;
  d.sensor_update=true;
 }else if(d.mean>=24&&!bright&&(!dark||(exposure==2989&&gain_index==82))&&
   d.r_mean>=4&&d.g_mean>=4&&d.b_mean>=4&&s.r_count>=64&&s.g_count>=64&&s.b_count>=64){
  d.gain_r=camera_smooth(r,camera_ratio(d.g_mean,d.r_mean));
  d.gain_b=camera_smooth(b,camera_ratio(d.g_mean,d.b_mean));
 }
 return d;
}
inline uint16_t camera_register(unsigned i){
 const uint16_t addresses[]={0x3e00,0x3e01,0x3e02,0x3e08,0x3e09};return addresses[i];
}
inline uint8_t camera_expected(unsigned i,uint16_t exposure,unsigned gain_index){
 switch(i){
 case 0:return exposure>>12;
 case 1:return exposure>>4;
 case 2:return exposure<<4;
 case 3:return camera_gain_code(gain_index)>>8;
 default:return camera_gain_code(gain_index);
 }
}
