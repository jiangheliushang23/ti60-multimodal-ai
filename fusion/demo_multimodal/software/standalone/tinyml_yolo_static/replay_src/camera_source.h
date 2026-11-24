#pragma once
#include <cstring>
#include "fixture.h"
#include "port.h"
#include "compat_runtime.h"

namespace camera_source {
volatile uint32_t* const lease=reinterpret_cast<volatile uint32_t*>(0xf8105100u);
volatile uint32_t* const fusion=reinterpret_cast<volatile uint32_t*>(0xf8100000u);
unsigned last_seq=~0u;
unsigned sample_x[kInputWidth],sample_row[kInputHeight];
int8_t expand5[32],expand6[64];bool sampling_ready=false;
void fence() {asm volatile("fence iorw,iorw":::"memory");}
bool available() {return lease[0]==0x59465231u&&lease[5]==1280&&lease[6]==720&&lease[7]==0x565;}
bool acquire(bool value) {
  lease[1]=value;fence();const unsigned t=milliseconds();
  while(bool(lease[2]&4u)!=value)if(milliseconds()-t>10)return false;
  fence();return !value||(lease[2]&3u)==3u;
}
bool capture(int8_t* input,unsigned* sequence,unsigned* elapsed) {
  if(!available()||!acquire(true)) {acquire(false);return false;}
  const unsigned t=milliseconds(),seq=lease[4],base=lease[3];
  if(seq==last_seq || (base!=0x06000000u&&base!=0x06200000u&&base!=0x06400000u)) {
    acquire(false);return false;
  }
  cache_sync();
  const auto* pixels=reinterpret_cast<volatile const uint16_t*>(base);
  const unsigned nw=std::min(kInputWidth,(kInputHeight*1280u+360u)/720u);
  const unsigned nh=std::min(kInputHeight,(kInputWidth*720u+640u)/1280u);
  const unsigned px=(kInputWidth-nw)/2,py=(kInputHeight-nh)/2;
  if(!sampling_ready) {
    for(unsigned x=0;x<nw;++x)sample_x[x]=((x*2+1)*1280)/(nw*2);
    for(unsigned y=0;y<nh;++y)sample_row[y]=(((y*2+1)*720)/(nh*2))*1280;
    for(unsigned i=0;i<32;++i)expand5[i]=int(i*255u/31u)-128;
    for(unsigned i=0;i<64;++i)expand6[i]=int(i*255u/63u)-128;
    sampling_ready=true;
  }
  memset(input,-14,kInputBytes);
  for(unsigned y=0;y<nh;++y) {
    const auto* row=pixels+sample_row[y];
    for(unsigned x=0;x<nw;++x) {
      const unsigned p=row[sample_x[x]];auto* d=input+((y+py)*kInputWidth+x+px)*3;
      d[0]=expand5[p>>11];d[1]=expand6[(p>>5)&63u];d[2]=expand5[p&31u];
    }
  }
  fence();const bool good=(lease[2]&3u)==3u&&lease[4]==seq;
  const bool released=acquire(false);
  if(!good||!released)return false;
  last_seq=seq;*sequence=seq;*elapsed=milliseconds()-t;return true;
}
bool overlay(bool valid,int x1q,int y1q,int x2q,int y2q) {
  if((fusion[0x1070/4]&5u)!=4u)return false;
  const int nw=std::min(kInputWidth,(kInputHeight*1280u+360u)/720u);
  const int nh=std::min(kInputHeight,(kInputWidth*720u+640u)/1280u);
  const int px=(kInputWidth-nw)/2,py=(kInputHeight-nh)/2;
  int x1=(x1q-px*256)*1280/nw/256,x2=(x2q-px*256)*1280/nw/256;
  int y1=(y1q-py*256)*720/nh/256,y2=(y2q-py*256)*720/nh/256;
  x1=std::max(0,std::min(1279,x1));x2=std::max(x1,std::min(1280,x2));
  y1=std::max(0,std::min(719,y1));y2=std::max(y1,std::min(720,y2));
  fusion[0x1060/4]=valid?3:0;
  fusion[0x1064/4]=valid?((y1+144)<<16)|(x1+32):0;
  fusion[0x1068/4]=valid?((y2+144)<<16)|(x2+32):0;
  fence();fusion[0x106c/4]=1;fence();return true;
}
}
