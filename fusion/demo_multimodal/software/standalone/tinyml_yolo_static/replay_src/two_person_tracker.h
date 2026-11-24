#pragma once
#include "person_pair.h"

// Geometry association only. Predictions never create detections. A separate
// per-ID analysis layer owns fall states and current-pixel continuation.
namespace two_person_tracker {
using person_roi::Detection;
using person_roi::Rect;
struct Point {uint32_t ms;int x,y;};
struct Track {
  uint32_t id,last_ms,previous_ms;Rect box;
  int vx,vy;unsigned hits,misses,history_count,history_head;
  bool active,observed;
  Point history[32];
};
struct Result {uint32_t ids[2];unsigned active,visible;};
class Tracker {
 public:
  static constexpr unsigned kLostMs=1200,kPredictMs=600,kPointMs=150;
  Tracker():next_id_(1){reset();}
  // Preserve the session ID counter across camera/LOW/manual resets.
  void reset(){
    if(!next_id_)next_id_=1;
    tracks_[0]=Track{};tracks_[1]=Track{};retain_[0]=retain_[1]=false;have_time_=false;now_=0;
  }
  const Track& track(unsigned slot)const{return tracks_[slot];}
  void retain_alarm(unsigned slot,bool alarm){if(slot<2)retain_[slot]=alarm;}
  // Only the current-pixel verifier may use this for a missed, established ID.
  bool observe_pixels(unsigned slot,uint32_t ms,const Detection& d){
    if(slot>=2||!person_pair::usable(d)||ms!=now_)return false;
    auto& t=tracks_[slot];
    if(!t.active||t.observed||(!retain_[slot]&&uint32_t(ms-t.last_ms)>kLostMs))return false;
    for(unsigned i=0;i<2;++i)if(i!=slot&&tracks_[i].observed&&person_pair::duplicate(tracks_[i].box,d.box))return false;
    observe(t,d,ms);return true;
  }
  Result update(uint32_t ms,const Detection& first,const Detection& second,bool fresh=true){
    Result result={{0,0},0,0};
    if(have_time_&&int32_t(ms-now_)<=0)return result;
    now_=ms;have_time_=true;
    Detection d[2]={first,second};
    for(unsigned j=0;j<2;++j)d[j].valid=fresh&&person_pair::usable(d[j]);
    if(d[0].valid&&d[1].valid&&person_pair::duplicate(d[0].box,d[1].box))d[1].valid=false;
    for(unsigned i=0;i<2;++i){auto& t=tracks_[i];
      t.observed=false;
      if(t.active&&!retain_[i]&&uint32_t(ms-t.last_ms)>kLostMs)t=Track{};
    }
    int cost[2][2];
    for(unsigned i=0;i<2;++i)for(unsigned j=0;j<2;++j)
      cost[i][j]=tracks_[i].active&&d[j].valid?association(tracks_[i],d[j].box,ms):-1;
    // Exhaustively choose the best of the nine two-track assignments. Maximize
    // matched identities first, then minimize total cost; never match twice.
    int best_a=-1,best_b=-1,best_count=-1,best_cost=0x7fffffff;
    for(int a=-1;a<2;++a)for(int b=-1;b<2;++b){
      if(a>=0&&b==a)continue;
      if((a>=0&&cost[0][a]<0)||(b>=0&&cost[1][b]<0))continue;
      const int n=int(a>=0)+int(b>=0),c=(a>=0?cost[0][a]:0)+(b>=0?cost[1][b]:0);
      if(n>best_count||(n==best_count&&c<best_cost)){
        best_count=n;best_cost=c;best_a=a;best_b=b;
      }
    }
    const int matches[2]={best_a,best_b};bool used[2]={false,false};
    for(unsigned i=0;i<2;++i){
      if(matches[i]>=0){
        const unsigned j=unsigned(matches[i]);observe(tracks_[i],d[j],ms);
        result.ids[j]=tracks_[i].id;used[j]=true;
      }else if(tracks_[i].active)++tracks_[i].misses;
    }
    for(unsigned j=0;j<2;++j)if(d[j].valid&&!used[j]){
      int slot=-1;
      for(unsigned i=0;i<2;++i)if(!tracks_[i].active){slot=int(i);break;}
      // A distinct current detection replaces an unmatched old identity when
      // both slots are reserved. Do not relabel it as the departed person.
      if(slot<0)for(unsigned i=0;i<2;++i)if(!tracks_[i].observed&&
        (slot<0||uint32_t(ms-tracks_[i].last_ms)>uint32_t(ms-tracks_[slot].last_ms)))slot=int(i);
      if(slot>=0){
        auto& t=tracks_[slot];t=Track{};retain_[slot]=false;
        // Four decimal HDMI digits. Skip IDs still owned by either slot.
        for(;;){
          t.id=next_id_++;if(next_id_>9999)next_id_=1;
          bool collision=false;
          for(unsigned i=0;i<2;++i)if(int(i)!=slot&&tracks_[i].active&&tracks_[i].id==t.id)collision=true;
          if(!collision)break;
        }
        t.active=true;observe(t,d[j],ms);result.ids[j]=t.id;
      }
    }
    for(const auto& t:tracks_){result.active+=t.active;result.visible+=t.active&&t.observed;}
    return result;
  }
 private:
  Track tracks_[2];bool retain_[2];uint32_t next_id_,now_;bool have_time_;
  static int center_x(Rect b){return (b.x1+b.x2)/2;}
  static int center_y(Rect b){return (b.y1+b.y2)/2;}
  static int area(Rect b){return (b.x2-b.x1)*(b.y2-b.y1);}
  static int iou(Rect a,Rect b){
    const int w=person_roi::maximum(0,person_roi::minimum(a.x2,b.x2)-person_roi::maximum(a.x1,b.x1));
    const int h=person_roi::maximum(0,person_roi::minimum(a.y2,b.y2)-person_roi::maximum(a.y1,b.y1));
    const int intersection=w*h,total=area(a)+area(b)-intersection;
    return total>0?int(int64_t(intersection)*1000/total):0;
  }
  static int association(const Track& t,Rect b,uint32_t ms){
    const unsigned dt=person_roi::minimum(int(ms-t.last_ms),int(kPredictMs));
    const int dx=t.vx*int(dt)/1000,dy=t.vy*int(dt)/1000;
    const Rect predicted={t.box.x1+dx,t.box.y1+dy,t.box.x2+dx,t.box.y2+dy};
    const int a=area(t.box),n=area(b);
    if(int64_t(a)>int64_t(n)*6||int64_t(n)>int64_t(a)*6)return -1;
    const int distance=person_roi::absolute(center_x(b)-center_x(predicted))+
                       person_roi::absolute(center_y(b)-center_y(predicted));
    const int size=person_roi::maximum(t.box.x2-t.box.x1,t.box.y2-t.box.y1);
    const int gate=person_roi::clip(size/2+int(dt)/8,80,280);
    const int overlap=iou(predicted,b),old_overlap=iou(t.box,b);
    if(overlap<100&&old_overlap<100&&distance>gate)return -1;
    // Distance also resolves overlapping crossing boxes with similar IOU.
    return 1000-overlap+distance*3;
  }
  static void observe(Track& t,const Detection& d,uint32_t ms){
    const int x=center_x(d.box),y=center_y(d.box);
    if(t.hits){
      const unsigned dt=ms-t.last_ms;
      if(dt){
        const int vx=person_roi::clip((x-center_x(t.box))*1000/int(dt),-1600,1600);
        const int vy=person_roi::clip((y-center_y(t.box))*1000/int(dt),-1000,1000);
        t.vx=t.hits==1?vx:(t.vx+vx*3)/4;t.vy=t.hits==1?vy:(t.vy+vy*3)/4;
      }
    }
    t.previous_ms=t.last_ms;t.last_ms=ms;t.box=d.box;++t.hits;t.misses=0;t.observed=true;
    if(!t.history_count||uint32_t(ms-t.history[(t.history_head+31)%32].ms)>=kPointMs){
      t.history[t.history_head]={ms,x,y};t.history_head=(t.history_head+1)%32;
      if(t.history_count<32)++t.history_count;
    }
  }
};
}
