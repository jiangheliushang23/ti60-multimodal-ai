#pragma once
#include <stdint.h>
#include "person_roi.h"

// Fixed-camera, single-person continuity. A detection starts an identity; only
// CURRENT foreground pixels can continue it. A previous rectangle alone never
// produces presence. This is not a newly trained YOLO or a probability score.
namespace person_visual_track {
enum { Width=128,Height=72,Pixels=Width*Height };
using person_roi::Rect;
using person_roi::Detection;
inline int lo(int a,int b){return a<b?a:b;}
inline int hi(int a,int b){return a>b?a:b;}
inline int absval(int x){return x<0?-x:x;}
inline bool inside(Rect r,int x,int y,int margin=0){
  return x>=r.x1-margin&&x<r.x2+margin&&y>=r.y1-margin&&y<r.y2+margin;
}
struct Result {
  Detection detection;
  bool fallback,ready;
  unsigned foreground,support,known,scene_change,appearance;
};
class Tracker {
 public:
  Tracker(){reset();}
  void reset(){
    frames_=0;active_=false;last_seen_=0;area_=0;hist_total_=0;
    last_={0,0,0,0};for(int k=0;k<3;++k)shift_[k]=0;
    for(unsigned i=0;i<Pixels;++i)age_[i]=0;
    for(unsigned i=0;i<64;++i)hist_[i]=0;
  }
  // Keep learned background when an ID changes, but never transfer a person's
  // appearance or a lying-person continuation to the replacement identity.
  void forget_identity(){
    active_=false;last_seen_=area_=hist_total_=0;last_={0,0,0,0};
    for(unsigned i=0;i<64;++i)hist_[i]=0;
  }
  Result update(uint32_t now,const uint16_t* image,const Detection& model){
    Result out={model,false,false,0,0,0,0,0};
    ++frames_;
    // A stale track cannot silently migrate to an unrelated moving object.
    if(active_&&uint32_t(now-last_seen_)>1500)active_=false;
    const Rect protected_box=model.valid?model.box:last_;
    const bool protect=model.valid||active_;
    int shift[3]={0,0,0};unsigned samples=0;
    int histogram[3][129]={};
    for(int y=0;y<Height;y+=2)for(int x=0;x<Width;x+=2){
      const unsigned i=y*Width+x;
      if(age_[i]<4||(protect&&inside(protected_box,x*10+5,y*10+5,30)))continue;
      int c[3];color(image[i],c);++samples;
      for(int k=0;k<3;++k)++histogram[k][hi(0,lo(128,c[k]-int(mean_[i][k]/16)+64))];
    }
    if(samples>=64)for(int k=0;k<3;++k){
      unsigned n=0;for(int b=0;b<129;++b){n+=histogram[k][b];if(n>samples/2){shift[k]=b-64;break;}}
    }
    for(int k=0;k<3;++k)shift_[k]=shift[k];
    unsigned outside=0,changed_outside=0;
    for(int y=0;y<Height;++y)for(int x=0;x<Width;++x){
      const unsigned i=y*Width+x;int c[3];color(image[i],c);
      mask_[i]=0;
      if(age_[i]>=4){
        ++out.known;int sum=0,max_delta=0;
        for(int k=0;k<3;++k){const int d=absval(c[k]-shift[k]-int(mean_[i][k]/16));sum+=d;max_delta=hi(max_delta,d);}
        // Reject sensor noise and small exposure residuals. Three-channel
        // differencing preserves stationary people instead of only motion.
        mask_[i]=sum>=65&&max_delta>=30;
        out.foreground+=mask_[i];
        if(!protect||!inside(protected_box,x*10+5,y*10+5,100)){++outside;changed_outside+=mask_[i];}
      }
    }
    out.ready=frames_>=8&&out.known>=Pixels*3/5;
    out.scene_change=outside?changed_outside*1000/outside:0;
    const bool unstable=out.scene_change>330||out.foreground>Pixels*2/3;
    // A camera move invalidates the background; preserve genuine YOLO output,
    // but explicitly discard foreground identity and relearn the new view.
    if(unstable){
      active_=false;hist_total_=0;
      for(unsigned i=0;i<Pixels;++i)age_[i]=0;
      frames_=0;out.ready=false;
    }
    if(!model.valid&&active_&&out.ready&&!unstable&&area_>=32&&hist_total_>=24){
      // Close one-cell gaps, then label components. Isolated foreground noise
      // cannot grow into a person rectangle by carrying over yesterday's box.
      for(int y=0;y<Height;++y)for(int x=0;x<Width;++x){
        unsigned n=0;
        for(int yy=hi(0,y-1);yy<=lo(Height-1,y+1);++yy)
          for(int xx=hi(0,x-1);xx<=lo(Width-1,x+1);++xx)n+=mask_[yy*Width+xx];
        work_[y*Width+x]=mask_[y*Width+x]||n>=4;
      }
      int64_t best=-1;Rect candidate={0,0,0,0};unsigned best_n=0,best_app=0;
      for(unsigned start=0;start<Pixels;++start){
        if(!work_[start])continue;
        unsigned begin=0,end=1,n=0,matched=0;queue_[0]=start;work_[start]=0;
        unsigned rows[Height]={};
        int x1=Width,y1=Height,x2=0,y2=0;
        while(begin<end){
          const unsigned i=queue_[begin++];const int y=i/Width,x=i%Width;
          x1=lo(x1,x);x2=hi(x2,x+1);y1=lo(y1,y);y2=hi(y2,y+1);
          if(mask_[i]){++n;++rows[y];int c[3];color(image[i],c);matched+=matches(c,shift);}
          for(int yy=hi(0,y-1);yy<=lo(Height-1,y+1);++yy)for(int xx=hi(0,x-1);xx<=lo(Width-1,x+1);++xx){
            const unsigned j=yy*Width+xx;
            if(work_[j]){work_[j]=0;queue_[end++]=j;}
          }
        }
        const int w=x2-x1,h=y2-y1;
        const unsigned appearance=n?matched*1000/n:0;
        if(n<32||w<3||h<4||n*100<unsigned(w*h)*18||n*5<area_||n>hi(400,int(area_*5/2)))continue;
        if(hist_total_>=24&&appearance<450)continue;
        // Thin foreground tails can join a person to a displaced door or
        // bedding. Bound each tail by its observed pixel mass, then retain a
        // one-cell margin. Dense silhouettes are not reduced by a percentile.
        // Preserve horizontal extent, including limbs clipped by the view.
        int left=x1,right=x2,top=y1,bottom=y2;
        trim_sparse_tail(rows,top,bottom,n);
        Rect r={left*10,top*10,right*10,bottom*10};
        const int iw=hi(0,lo(last_.x2,r.x2)-hi(last_.x1,r.x1));
        const int ih=hi(0,lo(last_.y2,r.y2)-hi(last_.y1,r.y1));
        const int span=hi(last_.x2-last_.x1,last_.y2-last_.y1);
        const int dx=absval(r.x1+r.x2-last_.x1-last_.x2)/2;
        const int dy=absval(r.y1+r.y2-last_.y1-last_.y2)/2;
        if(!iw||!ih){if(dx>hi(100,span/2)||dy>hi(140,span*3/4))continue;}
        if(dx>hi(160,span*3/4)||dy>hi(180,span))continue;
        const int64_t rank=int64_t(iw)*ih+int64_t(n)*100+appearance*20-dx*20-dy*10;
        if(rank>best){best=rank;candidate=r;best_n=n;best_app=appearance;}
      }
      if(best>=0){
        out.detection={candidate,0,true};out.fallback=true;
        out.support=best_n;out.appearance=best_app;
        last_=candidate;last_seen_=now;
        // Bound slow area adaptation, so a nearby door cannot inflate a track.
        area_=(area_*15+best_n)/16;
      }
    }
    if(model.valid)confirm(now,image,model);
    // Learn background only outside the currently observed person. Unknown
    // pixels beneath the initial person stay unknown until actually uncovered.
    const Rect p=out.detection.valid?out.detection.box:last_;
    const bool preserve=out.detection.valid||active_;
    for(int y=0;y<Height;++y)for(int x=0;x<Width;++x){
      const unsigned i=y*Width+x;
      if(preserve&&inside(p,x*10+5,y*10+5,20))continue;
      int c[3];color(image[i],c);
      for(int k=0;k<3;++k){
        const int v=hi(0,lo(255,c[k]-shift[k]))*16;
        if(!age_[i])mean_[i][k]=v;
        else if(age_[i]<4||!mask_[i])mean_[i][k]+= (v-int(mean_[i][k]))/(age_[i]<4?2:32);
      }
      if(age_[i]<255)++age_[i];
    }
    return out;
  }
  void confirm(uint32_t now,const uint16_t* image,const Detection& model){
    if(!model.valid)return;
      active_=true;last_=model.box;last_seen_=now;
      unsigned n=0;uint16_t observed[64]={};
      for(int y=0;y<Height;++y)for(int x=0;x<Width;++x){
        unsigned i=y*Width+x;
        const int px=x*10+5,py=y*10+5;
        if(!inside(model.box,px,py))continue;
        const int mx=(model.box.x2-model.box.x1)/5,my=(model.box.y2-model.box.y1)/8;
        const Rect inner={model.box.x1+mx,model.box.y1+my,model.box.x2-mx,model.box.y2-my};
        if(!mask_[i]&&!(age_[i]<4&&inside(inner,px,py)))continue;
        int c[3];color(image[i],c);
        for(int k=0;k<3;++k)c[k]=hi(0,lo(255,c[k]-shift_[k]));
        ++observed[bin(c)];++n;
      }
      if(n>=24){
        area_=area_?(area_*3+n)/4:n;
        // Only genuine model detections teach appearance, never predictions
        // from the tracker itself. Accumulate adjacent quantized color bins.
        for(unsigned i=0;i<64;++i)hist_[i]=(hist_[i]*3+observed[i])/4;
        hist_total_=0;for(unsigned i=0;i<64;++i)hist_total_+=hist_[i];
      }
  }
 private:
  static void trim_sparse_tail(const unsigned* projection,int& first,int& last,unsigned n){
    unsigned peak=0;for(int i=first;i<last;++i)if(projection[i]>peak)peak=projection[i];
    if(!peak)return;
    const int original_first=first,original_last=last;
    const unsigned budget=n*12/100;
    unsigned removed=0;
    while(first+3<last&&projection[first]*2<peak&&removed+projection[first]<=budget){
      removed+=projection[first++];
    }
    removed=0;
    while(last>first+3&&projection[last-1]*2<peak&&removed+projection[last-1]<=budget){
      removed+=projection[--last];
    }
    first=hi(original_first,first-1);last=lo(original_last,last+1);
  }
  static void color(unsigned p,int* c){c[0]=(p>>11)*255/31;c[1]=((p>>5)&63)*255/63;c[2]=(p&31)*255/31;}
  static unsigned bin(const int* c){return (c[0]/64)*16+(c[1]/64)*4+c[2]/64;}
  bool matches(int* c,const int* shift)const{
    if(hist_total_<24)return false;
    for(int k=0;k<3;++k)c[k]=hi(0,lo(255,c[k]-shift[k]));
    const int r=c[0]/64,g=c[1]/64,b=c[2]/64;
    unsigned support=hist_[r*16+g*4+b];
    if(r)support+=hist_[(r-1)*16+g*4+b];if(r<3)support+=hist_[(r+1)*16+g*4+b];
    if(g)support+=hist_[r*16+(g-1)*4+b];if(g<3)support+=hist_[r*16+(g+1)*4+b];
    if(b)support+=hist_[r*16+g*4+b-1];if(b<3)support+=hist_[r*16+g*4+b+1];
    return support>=hi(2,int(hist_total_/100));
  }
  uint16_t mean_[Pixels][3],queue_[Pixels],hist_[64];
  uint8_t age_[Pixels],mask_[Pixels],work_[Pixels];
  int shift_[3];
  Rect last_;uint32_t last_seen_;unsigned frames_,area_,hist_total_;bool active_;
};
}
