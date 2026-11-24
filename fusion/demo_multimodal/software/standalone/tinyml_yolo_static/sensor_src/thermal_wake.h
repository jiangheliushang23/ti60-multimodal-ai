#pragma once
#include <cstdint>

// Low-cost wake evidence from calibrated temperatures, independent of the palette.
// This finds a possible body heat source; YOLO must confirm whether it is a person.
struct ThermalWake {
 static const unsigned kMinArea=6,kConfirmMs=400,kMaxGapMs=1500,kMinSamples=3;
 static const int kMinCenti=2400,kMaxCenti=4200,kContrastCenti=150;
 bool enabled=false,have_sequence=false,candidate=false,confirmed=false,chess_mode=false;
 unsigned last_sequence=0,page_mask=0,page_ms[2]={0,0},first_ms=0,last_ms=0,samples=0;
 unsigned area=0,duration_ms=0;int background_centi=0,contrast_centi=0;
 unsigned x1=0,y1=0,x2=0,y2=0;
 int16_t empty_background[768]={};
 bool visual_empty=false,background_chess=false,use_background=false,check_background_age=false;
 unsigned visual_ms=0,background_pages=0,background_ms=0,background_sequence=0;
 static const int kNewHeatCenti=100;
 void reject_candidate(unsigned now,unsigned sequence,bool chess,const int16_t* temperature,const uint8_t* bad){
  // After the full visual confirmation window, adopt the current non-person
  // heat source. A stationary rejected object must not retrigger every sleep.
  for(unsigned i=0;i<768;++i)if(!bad[i])empty_background[i]=temperature[i];
  background_pages=3;background_chess=chess;background_ms=now;background_sequence=sequence;
  reset();
 }
 void observe_visual(unsigned now,bool present){
  visual_empty=!present;visual_ms=now;
  if(present)background_pages=0;
 }
 void learn_background(unsigned now,unsigned sequence,unsigned page,bool chess,const int16_t* temperature,const uint8_t* bad){
  const int age=int32_t(now-visual_ms);
  if(!visual_empty||age < -1000||age>3000)return;
  if(background_pages&&(background_chess!=chess||unsigned(now-background_ms)>3000))background_pages=0;
  if(background_pages&&sequence==background_sequence)return;
  page&=1;const bool seeded=background_pages&(1u<<page);
  for(unsigned i=0;i<768;++i){
   unsigned pattern=(i/32)&1;if(chess)pattern^=i&1;
   if(pattern!=page||bad[i])continue;
   empty_background[i]=seeded?(int(empty_background[i])*15+temperature[i])/16:temperature[i];
  }
  background_pages|=1u<<page;background_chess=chess;background_ms=now;background_sequence=sequence;
 }
 void reset(){
  have_sequence=candidate=confirmed=false;page_mask=0;samples=0;area=duration_ms=0;
  background_centi=contrast_centi=0;
 }
 void set_enabled(bool value){if(value!=enabled){enabled=value;reset();use_background=value&&background_pages==3;check_background_age=use_background;}}
 bool update(unsigned now,unsigned sequence,unsigned page,bool chess,const int16_t* temperature,const uint8_t* bad){
  // YOLO-confirmed empty normal frames teach the static warm scene. Freeze
  // that reference in LOW, so a stationary *new* body still wakes the system.
  // Display colors and the compensated temperatures remain unchanged.
  if(!enabled){learn_background(now,sequence,page,chess,temperature,bad);return false;}
  if(check_background_age){use_background=unsigned(now-background_ms)<=3000&&background_chess==chess;check_background_age=false;}
  if(use_background&&background_chess!=chess)use_background=false;
  if(have_sequence&&chess_mode!=chess)reset();chess_mode=chess;
  if(have_sequence&&sequence==last_sequence)return confirmed;
  have_sequence=true;last_sequence=sequence;page&=1;page_mask|=1u<<page;page_ms[page]=now;
  if(page_mask!=3||unsigned(now-page_ms[1-page])>kMaxGapMs){candidate=confirmed=false;samples=0;return false;}
  // Lower 35th percentile is a robust scene-background estimate. A uniform
  // ambient-temperature change alone has no warm foreground contrast.
  uint16_t histogram[128]={};unsigned count=0;
  for(unsigned i=0;i<768;++i)if(!bad[i]){
   int b=(int(temperature[i])+4000)/100;b=b<0?0:b>127?127:b;++histogram[b];++count;
  }
  if(!count){candidate=confirmed=false;return false;}
  unsigned total=0,bin=0;for(;bin<127;++bin){total+=histogram[bin];if(total>count*35/100)break;}
  background_centi=int(bin)*100-4000;
  uint8_t foreground[768]={};uint16_t queue[768];
  for(unsigned i=0;i<768;++i){
   const int t=temperature[i];
   foreground[i]=!bad[i]&&t>=kMinCenti&&t<=kMaxCenti&&t-background_centi>=kContrastCenti&&
     (!use_background||t-int(empty_background[i])>=kNewHeatCenti);
  }
  unsigned best=0,bx1=0,by1=0,bx2=0,by2=0;int best_contrast=0;
  for(unsigned seed=0;seed<768;++seed)if(foreground[seed]){
   unsigned head=0,tail=0,l=31,r=0,t=23,b=0;int contrast=0;
   foreground[seed]=0;queue[tail++]=seed;
   while(head<tail){
    const unsigned i=queue[head++],x=i%32,y=i/32;
    l=x<l?x:l;r=x>r?x:r;t=y<t?y:t;b=y>b?y:b;
    const int delta=int(temperature[i])-background_centi;contrast=delta>contrast?delta:contrast;
    const int neighbours[4]={x?int(i)-1:-1,x<31?int(i)+1:-1,y?int(i)-32:-1,y<23?int(i)+32:-1};
    for(int j:neighbours)if(j>=0&&foreground[j]){foreground[j]=0;queue[tail++]=j;}
   }
   if(tail>best&&r>l&&b>t){best=tail;bx1=l;bx2=r;by1=t;by2=b;best_contrast=contrast;}
  }
  area=best;contrast_centi=best_contrast;
  if(best<kMinArea){candidate=confirmed=false;samples=duration_ms=0;return false;}
  const bool overlap=candidate&&bx1<=x2+1&&x1<=bx2+1&&by1<=y2+1&&y1<=by2+1;
  if(!overlap||unsigned(now-last_ms)>kMaxGapMs){first_ms=now;samples=0;}
  candidate=true;last_ms=now;x1=bx1;x2=bx2;y1=by1;y2=by2;++samples;
  duration_ms=now-first_ms;
  confirmed=samples>=kMinSamples&&duration_ms>=kConfirmMs;
  return confirmed;
 }
};
