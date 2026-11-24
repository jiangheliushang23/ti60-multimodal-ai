#pragma once
#include <stdint.h>
namespace thermal_presence {
// Scene-level corroboration only: RGB and infrared optics are not registered.
// MLX90640 surface temperatures are not clinical core body temperatures.
inline uint32_t summarize(const int16_t* t,bool valid){
 if(!valid)return 0;
 unsigned hist[191]={0};
 for(unsigned i=0;i<768;++i){int b=t[i]/100+40;if(b<0)b=0;if(b>190)b=190;++hist[b];}
 unsigned total=0,quartile=0;for(;quartile<190;++quartile){total+=hist[quartile];if(total>=192)break;}
 const int background=(int(quartile)-40)*100;
 uint8_t mask[768];uint16_t queue[768];unsigned pixels=0,largest=0;
 for(unsigned i=0;i<768;++i){mask[i]=t[i]>=3000&&t[i]<=3750&&t[i]>=background+150;if(mask[i])++pixels;}
 for(unsigned i=0;i<768;++i)if(mask[i]){
  unsigned head=0,tail=1;queue[0]=i;mask[i]=0;
  while(head<tail){unsigned p=queue[head++],x=p%32,y=p/32;
   const unsigned n[4]={x?p-1:768,x<31?p+1:768,y?p-32:768,y<23?p+32:768};
   for(unsigned j=0;j<4;++j)if(n[j]<768&&mask[n[j]]){mask[n[j]]=0;queue[tail++]=n[j];}
  }if(tail>largest)largest=tail;
 }
 return 0xa1000000u|(largest<<10)|pixels;
}
}
