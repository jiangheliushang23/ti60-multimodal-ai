#pragma once
#include <algorithm>
#include <cstring>
#include "fixture.h"
#include "port.h"
#include "compat_runtime.h"
#include "person_roi.h"
#include "person_visual_track.h"
#ifdef YOLO_BOARD_HTTP
#include "board_http.h"
#endif

namespace camera_live_source {
#ifdef YOLO_MULTIMODAL
constexpr uint32_t kHdmiIdentity=0x59415539u,kLeaseIdentity=0x59465233u;
#else
constexpr uint32_t kHdmiIdentity=0x59434d32u,kLeaseIdentity=0x59465232u;
#endif
volatile uint32_t* const lease=reinterpret_cast<volatile uint32_t*>(0xf8105100u);
volatile uint32_t* const hdmi=reinterpret_cast<volatile uint32_t*>(0xf8100000u);
volatile uint32_t* const camera=reinterpret_cast<volatile uint32_t*>(0xf8105000u);
constexpr unsigned kWidth=1280,kHeight=720;
constexpr unsigned kFitWidth=(kInputHeight*kWidth+kHeight/2)/kHeight;
constexpr unsigned kFitHeight=(kInputWidth*kHeight+kWidth/2)/kWidth;
constexpr unsigned kNewWidth=kInputWidth<kFitWidth?kInputWidth:kFitWidth;
constexpr unsigned kNewHeight=kInputHeight<kFitHeight?kInputHeight:kFitHeight;
constexpr unsigned kPadX=(kInputWidth-kNewWidth)/2,kPadY=(kInputHeight-kNewHeight)/2;
unsigned sample_x[kNewWidth],sample_row[kNewHeight];
int8_t expand5[32],expand6[64];bool sampling_ready=false,have_last=false;
uint32_t last_count=0;
struct Frame {unsigned sequence,count,started_ms,pre_ms,skipped;uint8_t motion_gray[384];uint16_t support_rgb565[person_visual_track::Pixels];};
struct Rectangle {int x1,y1,x2,y2;bool valid;};
void fence(){asm volatile("fence iorw,iorw":::"memory");}
bool available(){return lease[0]==kLeaseIdentity&&hdmi[0x1058/4]==kHdmiIdentity&&
 lease[5]==kWidth&&lease[6]==kHeight&&lease[7]==0x565&&lease[8]==0x00020000;}
bool acquire(bool value){
 lease[1]=value;fence();const unsigned start=milliseconds();
 while(bool(lease[2]&4u)!=value)if(milliseconds()-start>=20)return false;
 fence();return !value||(lease[2]&3u)==3u;
}
void initialize_sampling(){
 if(!sampling_ready){
  for(unsigned x=0;x<kNewWidth;++x)sample_x[x]=((2*x+1)*kWidth)/(2*kNewWidth);
  for(unsigned y=0;y<kNewHeight;++y)sample_row[y]=((2*y+1)*kHeight)/(2*kNewHeight)*kWidth;
  for(unsigned i=0;i<32;++i)expand5[i]=int(i*255/31)-128;
  for(unsigned i=0;i<64;++i)expand6[i]=int(i*255/63)-128;
  sampling_ready=true;
 }
}
// Only the letterbox needs initialization: every interior RGB byte is replaced.
void prepare_padding(int8_t* input,int nw,int nh,int px,int py){
 const unsigned stride=kInputWidth*3;
 if(py)memset(input,-14,py*stride);
 for(int y=py;y<py+nh;++y){
  if(px)memset(input+y*stride,-14,px*3);
  const int right=kInputWidth-px-nw;
  if(right)memset(input+y*stride+(px+nw)*3,-14,right*3);
 }
 const unsigned end=(py+nh)*stride;
 if(end<kInputBytes)memset(input+end,-14,kInputBytes-end);
}
bool same_view(const person_roi::View& a,const person_roi::View& b){
 return a.roi.x1==b.roi.x1&&a.roi.y1==b.roi.y1&&a.roi.x2==b.roi.x2&&a.roi.y2==b.roi.y2&&
  a.nw==b.nw&&a.nh==b.nh&&a.px==b.px&&a.py==b.py&&a.turns==b.turns&&a.zoom==b.zoom;
}
void prepare_input(const volatile uint16_t* pixels,int8_t* input){
 initialize_sampling();
 // Model input: RGB/255, scale=1/255, zero_point=-128. Padding is RGB 114.
 prepare_padding(input,kNewWidth,kNewHeight,kPadX,kPadY);
 for(unsigned y=0;y<kNewHeight;++y){
  const auto* row=pixels+sample_row[y];
  for(unsigned x=0;x<kNewWidth;++x){
   const unsigned p=row[sample_x[x]];auto* d=input+((y+kPadY)*kInputWidth+x+kPadX)*3;
   d[0]=expand5[p>>11];d[1]=expand6[(p>>5)&63];d[2]=expand5[p&31];
  }
 }
}
void prepare_view(const volatile uint16_t* pixels,int8_t* input,const person_roi::View& v){
 if(!v.zoom&&!v.turns){prepare_input(pixels,input);return;}
 // One immutable leased frame supplies both views; release it before Invoke.
 initialize_sampling();
 int xs[kInputWidth],rows[kInputHeight];
 const int w=v.roi.x2-v.roi.x1,h=v.roi.y2-v.roi.y1;
 // Precompute the separable rotation addresses once per axis, not per pixel.
 for(int x=0;x<v.nw;++x){
  int u=(2*x+1)*((v.turns&1)?h:w)/(2*v.nw);
  xs[x]=v.turns==1?(h-1-u)*int(kWidth):v.turns==2?w-1-u:v.turns==3?u*int(kWidth):u;
 }
 for(int y=0;y<v.nh;++y){
  int t=(2*y+1)*((v.turns&1)?w:h)/(2*v.nh);
  rows[y]=v.turns==1?t:v.turns==2?(h-1-t)*int(kWidth):v.turns==3?w-1-t:t*int(kWidth);
 }
 prepare_padding(input,v.nw,v.nh,v.px,v.py);
 for(int y=0;y<v.nh;++y)for(int x=0;x<v.nw;++x){
   const unsigned p=pixels[v.roi.y1*kWidth+v.roi.x1+rows[y]+xs[x]];auto* d=input+((y+v.py)*kInputWidth+x+v.px)*3;
   d[0]=expand5[p>>11];d[1]=expand6[(p>>5)&63];d[2]=expand5[p&31];
 }
}
bool capture_views(int8_t* input,int8_t* alternate,Frame* frame,const person_roi::View& primary,const person_roi::View& secondary){
 const unsigned start=milliseconds();
 if(!available()||!acquire(true)){acquire(false);return false;}
 const unsigned sequence=lease[4],base=lease[3],count=lease[10];
#ifdef YOLO_MULTIMODAL
 const unsigned captured_ms=lease[11];
#else
 const unsigned captured_ms=start;
#endif
 if((have_last&&count==last_count)||(base!=0x06000000u&&base!=0x06200000u&&base!=0x06400000u)){
  acquire(false);return false;
 }
 cache_sync();const auto* pixels=reinterpret_cast<volatile const uint16_t*>(base);
 prepare_view(pixels,input,primary);
 if(alternate){
  if(same_view(primary,secondary))memcpy(alternate,input,kInputBytes);
  else prepare_view(pixels,alternate,secondary);
 }
 for(unsigned y=0;y<16;++y)for(unsigned x=0;x<24;++x){
   const unsigned p=pixels[((2*y+1)*kHeight/32)*kWidth+(2*x+1)*kWidth/48];
   frame->motion_gray[y*24+x]=(77*(int(expand5[p>>11])+128)+150*(int(expand6[(p>>5)&63])+128)+29*(int(expand5[p&31])+128)+128)>>8;
 }
 for(unsigned y=0;y<person_visual_track::Height;++y)for(unsigned x=0;x<person_visual_track::Width;++x)
   frame->support_rgb565[y*person_visual_track::Width+x]=pixels[(y*10+5)*kWidth+x*10+5];
 fence();
 const bool good=(lease[2]&3u)==3u&&lease[4]==sequence&&lease[10]==count;
 const bool released=acquire(false);
 if(!good||!released)return false;
#ifdef YOLO_BOARD_HTTP
 board_http::publish_rgb565(frame->support_rgb565,sequence,captured_ms);
#endif
 frame->sequence=sequence;frame->count=count;frame->started_ms=captured_ms;
 frame->pre_ms=milliseconds()-start;frame->skipped=have_last?count-last_count-1:0;
 last_count=count;have_last=true;return true;
}
// Low-power wake monitoring samples only 384 grayscale pixels. No neural
// network, tensor preprocessing, rotations or model/DSP calls are executed.
bool capture_monitor(Frame* frame){
 const unsigned start=milliseconds();
 if(!available()||!acquire(true)){acquire(false);return false;}
 const unsigned sequence=lease[4],base=lease[3],count=lease[10];
#ifdef YOLO_MULTIMODAL
 const unsigned captured=lease[11];
#else
 const unsigned captured=start;
#endif
 if((have_last&&count==last_count)||(base!=0x06000000u&&base!=0x06200000u&&base!=0x06400000u)){
  acquire(false);return false;}
 cache_sync();const auto* pixels=reinterpret_cast<const volatile uint16_t*>(base);
#ifdef YOLO_BOARD_HTTP
 // Only a requested HTTP snapshot samples color in LOW. It never runs YOLO
 // and uses the same immutable DDR lease, released before network service.
 const bool http_snapshot=board_http::snapshot_requested();
 if(http_snapshot)for(unsigned y=0;y<72;++y)for(unsigned x=0;x<128;++x)
  frame->support_rgb565[y*128+x]=pixels[(y*10+5)*kWidth+x*10+5];
#endif
 for(unsigned y=0;y<16;++y)for(unsigned x=0;x<24;++x){
  const unsigned p=pixels[((2*y+1)*kHeight/32)*kWidth+(2*x+1)*kWidth/48];
  const unsigned r=(p>>11)*255/31,g=((p>>5)&63)*255/63,b=(p&31)*255/31;
  frame->motion_gray[y*24+x]=(77*r+150*g+29*b+128)>>8;
 }
 fence();const bool good=(lease[2]&3u)==3u&&lease[10]==count&&lease[4]==sequence;
 const bool released=acquire(false);if(!good||!released)return false;
#ifdef YOLO_BOARD_HTTP
 if(http_snapshot)board_http::publish_rgb565(frame->support_rgb565,sequence,captured);
#endif
 frame->sequence=sequence;frame->count=count;frame->started_ms=captured;frame->pre_ms=milliseconds()-start;
 frame->skipped=have_last?count-last_count-1:0;last_count=count;have_last=true;return true;
}
bool capture(int8_t* input,Frame* frame){
 return capture_views(input,nullptr,frame,person_roi::full(),person_roi::full());
}
Rectangle rectangle(bool valid,int x1q,int y1q,int x2q,int y2q){
 Rectangle r={0,0,0,0,false};if(!valid)return r;
 r.x1=(x1q-int(kPadX*256))*int(kWidth)/int(kNewWidth)/256;
 r.x2=(x2q-int(kPadX*256))*int(kWidth)/int(kNewWidth)/256;
 r.y1=(y1q-int(kPadY*256))*int(kHeight)/int(kNewHeight)/256;
 r.y2=(y2q-int(kPadY*256))*int(kHeight)/int(kNewHeight)/256;
 r.x1=std::max(0,std::min(1279,r.x1));r.x2=std::max(0,std::min(1280,r.x2));
 r.y1=std::max(0,std::min(719,r.y1));r.y2=std::max(0,std::min(720,r.y2));
 r.valid=r.x2>r.x1&&r.y2>r.y1;return r;
}
bool wait_idle(){
 const unsigned start=milliseconds();
 while((hdmi[0x1070/4]&5u)!=4u)if(milliseconds()-start>=50)return false;
 return true;
}
bool overlay_metadata(unsigned sequence,const Rectangle& r,const Rectangle& second,unsigned first_flags,unsigned second_flags){
 if(!wait_idle())return false;
 // Both rectangles share one request and vertical-blank acknowledgement.
 hdmi[0x1060/4]=r.valid?first_flags:0u;
 hdmi[0x1064/4]=r.valid?((r.y1+144)<<16)|(r.x1+32):0;
 hdmi[0x1068/4]=r.valid?((r.y2+144)<<16)|(r.x2+32):0;
#ifdef YOLO_MULTIMODAL
 hdmi[0x1098/4]=second.valid?second_flags:0u;
 hdmi[0x109c/4]=second.valid?((second.y1+144)<<16)|(second.x1+32):0;
 hdmi[0x10a0/4]=second.valid?((second.y2+144)<<16)|(second.x2+32):0;
#endif
 hdmi[0x1078/4]=sequence;fence();hdmi[0x106c/4]=1;fence();
 if(!wait_idle())return false;
 return hdmi[0x107c/4]==sequence;
}
bool overlay_pair(unsigned sequence,const Rectangle& r,const Rectangle& second,bool alarm=false){
 return overlay_metadata(sequence,r,second,alarm?7u:3u,1u);
}
bool overlay(unsigned sequence,const Rectangle& r,bool alarm=false){
 return overlay_pair(sequence,r,{0,0,0,0,false},alarm);
}
}
