#pragma once
#include <stdint.h>

// Display preprocessing in centidegrees. Sensor calibration stays in main.cpp.
// Rebuild with -DTHERMAL_FIXED_SCALE for the original 15..47 C color range.
struct ThermalDisplay {
 int16_t previous[768],filtered[768],candidate[768];
 uint8_t seeded[768],pending[768];
 uint16_t histogram[1361]; // -40..300 C, 0.25 C bins
 int low,high,minimum,maximum,hotspot;
 bool scale_ready;
 static int absdiff(int a,int b){return a>b?a-b:b-a;}
 void reset(){
  for(int i=0;i<768;i++){seeded[i]=0;pending[i]=0;}
  scale_ready=false;
 }
 void update(const int16_t *raw,unsigned page,bool chess,const uint8_t *bad){
  for(int i=0;i<768;i++){
   unsigned pattern=(i/32)&1;if(chess)pattern^=i&1;
   if(!seeded[i]){previous[i]=filtered[i]=raw[i];seeded[i]=1;continue;}
   if(pattern!=page)continue; // Never average an unchanged opposite subpage again.
   int value=raw[i];
   // Hold an isolated >3 C jump for one fresh sample. A persistent small hot
   // object is accepted on confirmation; a broad real temperature step is immediate.
   bool isolated=!bad[i]&&absdiff(value,previous[i])>300;
   int neighbours[4]={i%32?i-1:-1,i%32<31?i+1:-1,i>=32?i-32:-1,i<736?i+32:-1};
   int valid=0;
   for(int j:neighbours)if(j>=0&&!bad[j]){
    valid++;if(absdiff(value,raw[j])<=300)isolated=false;
   }
   isolated=isolated&&valid>=2;
   if(isolated && !(pending[i]&&absdiff(value,candidate[i])<=150)){
    candidate[i]=value;pending[i]=1;continue;
   }
   pending[i]=0;
   // Keep the two-sample mean for small fluctuations; follow >1 C motion promptly.
   filtered[i]=absdiff(value,previous[i])>100?value:(previous[i]+value)/2;
   previous[i]=value;
  }
  minimum=30000;maximum=-4000;hotspot=0;
  for(int b=0;b<1361;b++)histogram[b]=0;
  for(int i=0;i<768;i++){
   int t=filtered[i];
   if(t<minimum)minimum=t;
   if(t>maximum){maximum=t;hotspot=i;}
   histogram[(t+4000)/25]++;
  }
#ifdef THERMAL_FIXED_SCALE
  low=1500;high=4700;
#else
  // Drop only the lowest/highest 15 of 768 pixels from color-range estimation.
  // Actual min/max and hotspot retain all filtered pixels, including clipped ones.
  int count=0,lower=0,upper=1360;
  for(int b=0;b<1361;b++){count+=histogram[b];if(count>15){lower=b;break;}}
  count=0;
  for(int b=1360;b>=0;b--){count+=histogram[b];if(count>15){upper=b;break;}}
  int target_low=lower*25-4000-50,target_high=(upper+1)*25-4000+50;
  if(target_high-target_low<500){int mid=(target_low+target_high)/2;target_low=mid-250;target_high=target_low+500;}
  if(!scale_ready){low=target_low;high=target_high;scale_ready=true;}
  else{
   // Expand promptly to admit a changed scene; contract slowly to reduce flicker.
   low=target_low<low?target_low:low+(target_low-low+3)/4;
   high=target_high>high?target_high:high-(high-target_high+3)/4;
   if(high-low<500)high=low+500;
  }
#endif
 }
 unsigned color(int i)const{
  int n=(int(filtered[i])-low)*255/(high-low);
  return n<0?0:n>255?255:unsigned(n);
 }
};
