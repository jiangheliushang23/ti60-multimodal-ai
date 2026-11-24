#pragma once
#include "person_roi.h"

// Same-frame detections only. No identities, predicted boxes or held results.
namespace person_pair {
using person_roi::Detection;
using person_roi::Rect;
inline bool usable(const Detection& d){
 return d.valid&&d.box.x1>=0&&d.box.y1>=0&&d.box.x2<=1280&&d.box.y2<=720&&
        d.box.x2-d.box.x1>=24&&d.box.y2-d.box.y1>=36;
}
inline bool duplicate(Rect a,Rect b){
 const int w=person_roi::maximum(0,person_roi::minimum(a.x2,b.x2)-person_roi::maximum(a.x1,b.x1));
 const int h=person_roi::maximum(0,person_roi::minimum(a.y2,b.y2)-person_roi::maximum(a.y1,b.y1));
 const int64_t intersection=int64_t(w)*h;
 const int64_t area=int64_t(a.x2-a.x1)*(a.y2-a.y1)+int64_t(b.x2-b.x1)*(b.y2-b.y1)-intersection;
 return area>0&&intersection*100>area*45;
}
struct Detections {
 Detection items[16];unsigned count;
 Detections():count(0){}
 void add(const person_roi::View& view,const person_roi::Box* boxes,unsigned n){
  for(unsigned i=0;i<n&&i<8;++i){
   Detection d={person_roi::map(view,boxes[i]),boxes[i].score,boxes[i].score>=8192};
   if(!usable(d))continue;
   unsigned same=count;
   for(unsigned j=0;j<count;++j)if(duplicate(items[j].box,d.box)){same=j;break;}
   if(same<count){if(d.score>items[same].score)items[same]=d;}
   else if(count<16)items[count++]=d;
  }
 }
 Detection second(const Detection& first,bool fresh)const{
  Detection out={{0,0,0,0},0,false};if(!fresh)return out;
  for(unsigned i=0;i<count;++i){
   const auto& d=items[i];
   if(usable(first)&&duplicate(first.box,d.box))continue;
   if(!out.valid||d.score>out.score)out=d;
  }
  return out;
 }
};
}
