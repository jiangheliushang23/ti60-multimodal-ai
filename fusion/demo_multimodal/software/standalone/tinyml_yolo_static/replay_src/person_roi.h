#pragma once
#include <stdint.h>

// Adaptive input sampling for the SAME quantized detector. No synthetic boxes,
// held-last-box presence, expected person labels, or video-specific coordinates.
namespace person_roi {
inline int minimum(int a,int b){return a<b?a:b;}
inline int maximum(int a,int b){return a>b?a:b;}
inline int clip(int n,int lo,int hi){return maximum(lo,minimum(hi,n));}
inline int absolute(int n){return n<0?-n:n;}
struct Rect {int x1,y1,x2,y2;};
struct View {Rect roi;int nw,nh,px,py;bool zoom;unsigned turns;};
struct Box {int x1,y1,x2,y2;unsigned score;};
struct Detection {Rect box;unsigned score;bool valid;};
inline View view(Rect r,int input_w=192,int input_h=96,unsigned turns=0){
  const int w=(turns&1)?r.y2-r.y1:r.x2-r.x1,h=(turns&1)?r.x2-r.x1:r.y2-r.y1;
  const int nw=minimum(input_w,(input_h*w+h/2)/h);
  const int nh=minimum(input_h,(input_w*h+w/2)/w);
  return {r,nw,nh,(input_w-nw)/2,(input_h-nh)/2,r.x2-r.x1!=1280||r.y2-r.y1!=720,turns};
}
inline View full(){return view({0,0,1280,720});}
inline Rect map(const View& v,Box b){
  const int w=v.roi.x2-v.roi.x1,h=v.roi.y2-v.roi.y1;
  const int rw=(v.turns&1)?h:w,rh=(v.turns&1)?w:h;
  const int u1=(b.x1-v.px*256)*rw/v.nw/256,u2=(b.x2-v.px*256)*rw/v.nw/256;
  const int t1=(b.y1-v.py*256)*rh/v.nh/256,t2=(b.y2-v.py*256)*rh/v.nh/256;
  Rect r={u1,t1,u2,t2};
  if(v.turns==1)r={t1,h-u2,t2,h-u1};
  if(v.turns==2)r={w-u2,h-t2,w-u1,h-t1};
  if(v.turns==3)r={w-t2,u1,w-t1,u2};
  r={clip(v.roi.x1+r.x1,0,1279),clip(v.roi.y1+r.y1,0,719),
     clip(v.roi.x1+r.x2,0,1280),clip(v.roi.y1+r.y2,0,720)};
  return r;
}
class Planner {
 public:
  Planner(){reset();}
  void reset(){last_={0,0,0,0};seen_=false;turns_=missed_=0;seen_at_=0;iteration_=0;}
  bool tracking(uint32_t now)const{return seen_&&uint32_t(now-seen_at_)<=1200;}
  View local()const{
    const int w=minimum(1280,maximum(640,(last_.x2-last_.x1)*8/5));
    const int h=minimum(720,maximum(360,(last_.y2-last_.y1)*8/5));
    const int x=clip((last_.x1+last_.x2-w)/2,0,1280-w);
    const int y=clip((last_.y1+last_.y2-h)/2,0,720-h);
    return view({x,y,x+w,y+h},192,96,turns_);
  }
  void acquired(){++iteration_;}
  View next(uint32_t now)const{
    const unsigned iteration=iteration_+1;
    if(tracking(now))return iteration%8?local():full();
    // Search the entire view regularly, plus overlapping larger-scale windows.
    // This can acquire a person who was already lying down at startup.
    const unsigned tile=iteration%5;
    if(!tile)return full();
    const int x=(tile==2||tile==4)?320:0,y=tile>=3?180:0;
    return view({x,y,x+960,y+540});
  }
  View alternate(const View& primary,uint32_t now)const{
    // Keep the established 180-degree rescue first. If it failed on the
    // preceding frame, try a quarter turn without repeating that same search.
    const unsigned rescue_turns=missed_%3==0?2:missed_%3==1?1:3;
    if(primary.zoom&&tracking(now)){
      if(primary.turns)return view(primary.roi);
      if(rescue_turns==2)return view(primary.roi,192,96,2);
      // Cover the possible floor extent of the last verified person, instead
      // of clipping a newly horizontal body to a narrow upright crop.
      const int old_h=last_.y2-last_.y1;
      const int w=minimum(1280,maximum(primary.roi.x2-primary.roi.x1,old_h*8/5));
      const int h=minimum(720,maximum(360,old_h*4/5));
      const int x=clip((last_.x1+last_.x2-w)/2,0,1280-w);
      const int y=clip(last_.y2+old_h/5-h,0,720-h);
      return view({x,y,x+w,y+h},192,96,rescue_turns);
    }
    if(!primary.zoom&&tracking(now))return local();
    // When starting with a person already on the floor, alternate ordinary
    // full-scene acquisition with rotated search windows as well.
    return missed_%6>=3?view(primary.roi,192,96,rescue_turns):full();
  }
  Detection select(const View& v,const Box* boxes,unsigned count,uint32_t now)const{
    Detection out={{0,0,0,0},0,false};int64_t best=-1;
    for(unsigned i=0;i<count;++i){
      const auto& b=boxes[i];if(b.score<8192)continue;
      const Rect r=map(v,b);const int w=r.x2-r.x1,h=r.y2-r.y1;
      if(w<24||h<36)continue;
      int64_t rank=b.score;
      if(tracking(now)){
        const int iw=maximum(0,minimum(r.x2,last_.x2)-maximum(r.x1,last_.x1));
        const int ih=maximum(0,minimum(r.y2,last_.y2)-maximum(r.y1,last_.y1));
        const int64_t inter=int64_t(iw)*ih;
        const int64_t total=int64_t(w)*h+int64_t(last_.x2-last_.x1)*(last_.y2-last_.y1)-inter;
        if(total>0)rank+=inter*16384/total;
      }
      if(rank>best){best=rank;out={r,b.score,true};}
    }
    return out;
  }
  void commit(uint32_t now,const Detection& d,unsigned turns=0){
    if(d.valid){last_=d.box;seen_=true;seen_at_=now;turns_=turns;missed_=0;}
    else ++missed_;
  }
 private:
  Rect last_;bool seen_;uint32_t seen_at_;unsigned iteration_,turns_,missed_;
};
}
