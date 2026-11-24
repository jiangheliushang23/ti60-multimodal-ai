#include <assert.h>
#include <stdio.h>
#include <vector>
#include "uart_voice_controller.h"
#include "fall_detection.h"
#include "voice_fall_queue.h"
#include "two_person_analysis.h"
using namespace voice_uart;
struct Bus {
  uint64_t t=0,at=0;unsigned step=100,rx=0x41;bool stopped=false,low=false,bad_stop=false,safe=true;
  uint32_t saved=8,restored=99;unsigned disabled=0;
  std::vector<unsigned> pins;
  uint64_t ticks(){if(!stopped)t+=step;return t;}
  bool timer_valid(){return true;}
  bool safe_point(){return safe;}
  uint32_t disable_irq(){++disabled;return saved;}
  void restore_irq(uint32_t v){restored=v;}
  void outputs(unsigned v){assert(v==4||v==6);pins.push_back(v);}
  unsigned inputs(){
    if(low)return 0;
    if(!at||t<at||t>=at+10*10417)return 1;
    unsigned bit=unsigned((t-at)/10417);
    return bit==0?0:bit==9?!bad_stop:(rx>>(bit-1))&1;
  }
  void response(unsigned n,unsigned value){at=100+n*10*10417+200000;rx=value;}
};
struct Hardware {
  std::vector<std::vector<uint8_t>> frames;Result send_result=Ack41,query_result=Busy4E;unsigned queries=0;
  Result send(const uint8_t* p,unsigned n){frames.push_back(std::vector<uint8_t>(p,p+n));return send_result;}
  Result query(){++queries;return query_result;}
};
int main(){
  unsigned cases=0;const uint8_t stop[]={0xfd,0,1,2};
  for(unsigned saved:{0u,8u}){
    Bus b;b.saved=saved;b.response(4,0x41);Transport<Bus> t(b);
    assert(t.send(stop,4)==Ack41&&b.restored==saved&&t.duration_valid());
    assert(t.last_duration_ticks()<6500000&&t.framing_errors()==0);
    for(unsigned i=0;i<4;++i){assert(b.pins[i*10]==4&&b.pins[i*10+9]==6);
      for(unsigned bit=0;bit<8;++bit)assert(b.pins[i*10+1+bit]==((stop[i]&(1<<bit))?6u:4u));}
    ++cases;
  }
  for(unsigned value:{0x4eu,0x4fu,0x41u,0x45u}){
    Bus b;b.response(4,value);Transport<Bus> t(b);
    Result r=t.query();assert(r==(value==0x4e?Busy4E:value==0x4f?Idle4F:value==0x45?Nak45:NoReply));++cases;
  }
  {Bus b;Transport<Bus> t(b);assert(t.send(stop,4)==NoReply&&b.restored==8&&t.last_duration_ticks()<6500000);++cases;}
  {Bus b;b.response(4,0x45);Transport<Bus> t(b);assert(t.send(stop,4)==Nak45);++cases;}
  {Bus b;b.response(4,0x41);b.bad_stop=true;Transport<Bus> t(b);assert(t.send(stop,4)==Invalid&&t.framing_errors());++cases;}
  {Bus b;b.low=true;Transport<Bus> t(b);assert(t.send(stop,4)==Invalid&&b.restored==8&&b.pins.size()==1);++cases;}
  {Bus b;b.safe=false;Transport<Bus> t(b);assert(t.send(stop,4)==Invalid&&b.disabled==0);++cases;}
  {Bus b;b.stopped=true;Transport<Bus> t(b);assert(t.send(stop,4)==Invalid&&b.restored==8);++cases;}
  {Bus b;Transport<Bus> t(b);uint8_t frame[33]={};assert(t.send(frame,33)==Invalid&&b.disabled==0);++cases;}
  {Bus b;Transport<Bus> t(b);uint8_t frame[32]={};b.response(32,0x41);assert(t.send(frame,32)==Ack41);++cases;}
  {Controller c;Hardware h;c.initialize(0);for(unsigned n=0;n<10000;n+=100)c.service(n,h);assert(h.frames.empty());++cases;}
  {Controller c;Hardware h;c.initialize(0);c.observe(1,true,true,42);c.service(999,h);assert(h.frames.empty());
    c.service(1000,h);assert(c.phase==Gap&&h.frames[0]==std::vector<uint8_t>(stop,stop+4));
    c.service(1264,h);assert(h.frames.size()==1);c.service(1265,h);assert(c.accepted==1&&c.phase==Playing);
    assert(h.frames[1].size()==27&&h.frames[1][2]==24);
    for(unsigned n=0;n<sizeof(kFall);++n)assert(h.frames[1][n+5]==kFall[n]);
    c.service(1765,h);assert(c.busy_seen&&c.uart_completed==0);h.query_result=Idle4F;c.service(2265,h);
    assert(c.uart_completed==1&&c.phase==Idle);
    for(unsigned n=2300;n<8000;n+=100){c.observe(n,true,true,42);c.service(n,h);}assert(h.frames.size()==2&&c.requested==1);
    c.observe(8001,false,false,42);c.observe(8002,true,true,43);c.service(8002,h);assert(c.requested==2&&c.phase==Gap);++cases;}
  {Controller c;Hardware h;c.initialize(0);c.observe(1,true,true,7);c.observe(2,false,false,0);c.service(1000,h);
    assert(h.frames.empty()&&c.dropped==1&&c.error==Cancelled);++cases;}
  {Controller c;Hardware h;c.initialize(0);c.observe(1,true,true,7);c.service(1000,h);c.observe(1100,false,false,0);
    c.service(2000,h);assert(h.frames.size()==1&&c.error==Cancelled);++cases;}
  {Controller c;Hardware h;c.initialize(0);c.observe(1,true,true,7);c.service(3001,h);assert(c.error==Expired&&h.frames.empty());++cases;}
  for(Result value:{NoReply,Nak45,Invalid}){
    Controller c;Hardware h;c.initialize(0);c.observe(1,true,true,7);h.send_result=value;c.service(1000,h);
    for(unsigned n=1100;n<10000;n+=100){c.observe(n,true,true,7);c.service(n,h);}
    assert(c.failed==1&&h.frames.size()==1);++cases;
  }
  {Controller c;Hardware h;c.initialize(0);assert(c.test(1));c.service(1000,h);assert(!c.test(1100));
    c.service(1265,h);assert(c.kind==Test&&h.frames[1].size()==17);h.query_result=NoReply;
    c.service(1765,h);c.service(2265,h);c.service(2765,h);assert(c.error==StatusTimeout&&c.uart_completed==0);++cases;}
  {Controller c;Hardware h;c.initialize(0);assert(c.test(1));c.observe(2,true,true,99);c.service(1000,h);
    assert(c.kind==Fall&&c.event_id==99&&c.dropped==1);++cases;}
  {Controller c;Hardware h;c.initialize(0);c.observe(1,true,true,1);c.service(1000,h);c.service(1265,h);
    c.observe(1300,false,false,1);c.observe(1301,true,true,2);h.query_result=Idle4F;c.service(1765,h);c.service(2000,h);
    assert(c.kind==Fall&&c.event_id==2&&h.frames.size()==3);++cases;}
  {Controller c;Hardware h;c.initialize(0xfffffc00u);c.observe(0xfffffc01u,true,true,1);c.service(0xffffffe8u,h);
    c.service(0xffffffe8u+265,h);h.query_result=Idle4F;c.service(0xffffffe8u+765,h);assert(c.uart_completed==1);++cases;}
  {Controller c;Hardware h;c.initialize(0);fall_detection::Detector d;
    const fall_detection::Detection standing={520,150,680,650,25000,true},lying={430,450,830,650,25000,true};
    for(unsigned n:{0u,280u,560u,840u}){auto r=d.update(n,standing);c.observe(n,r.alarm,r.event,r.events);}
    for(unsigned n:{1120u,1400u,1680u,1960u,2240u}){auto r=d.update(n,lying);c.observe(n,r.alarm,r.event,r.events);}
    assert(c.requested==1);c.service(2240,h);c.service(2505,h);assert(c.accepted==1&&c.kind==Fall);++cases;
  }
  {FallQueue q;Hardware h;q.initialize(0);
    syn6658_voice::FallEvent e[2]={{11,1,true,true},{22,1,true,true}};
    q.observe(1000,e);assert(q.waiting()==2&&q.queued==2);
    q.service(1000,h);q.service(1265,h);assert(q.controller.accepted==1&&q.person_id==11&&q.waiting()==1);
    q.observe(1300,e);assert(q.queued==2); // Repeated event does not repeat audio.
    h.query_result=Idle4F;q.service(1765,h);q.service(2000,h);q.service(2265,h);
    assert(q.controller.accepted==2&&q.person_id==22&&q.waiting()==0);
    q.service(2765,h);assert(q.controller.uart_completed==2&&h.frames.size()==4);++cases;}
  {FallQueue q;Hardware h;q.initialize(0);
    syn6658_voice::FallEvent e[2]={{11,1,true,true},{22,1,true,true}};
    q.observe(1000,e);q.service(1000,h);q.service(1265,h);
    e[1]={22,1,false,false};q.observe(1400,e);assert(q.waiting()==0&&q.cancelled==1);
    h.query_result=Idle4F;q.service(1765,h);q.service(2000,h);assert(h.frames.size()==2);++cases;}
  {FallQueue q;Hardware h;q.initialize(0);
    syn6658_voice::FallEvent e[2]={{11,1,true,true},{0,0,false,false}};
    q.observe(1000,e);q.service(1000,h);
    e[0]={33,0,false,false};q.observe(1100,e);q.service(1265,h);
    assert(q.controller.accepted==0&&h.frames.size()==1&&!q.running());
    e[0]={33,1,true,true};q.observe(2000,e);q.service(2000,h);q.service(2265,h);
    assert(q.person_id==33&&q.controller.accepted==1);++cases;}
  {FallQueue q;Hardware h;q.initialize(0);
    syn6658_voice::FallEvent e[2]={{1,0,false,false},{2,0,false,false}};
    for(unsigned t=1000;t<5000;t+=200){q.observe(t,e);q.service(t,h);}
    assert(h.frames.empty()&&q.queued==0); // Presence/yellow alone never speaks.
    e[0]={1,1,true,true};q.observe(5100,e);q.clear(5200);q.service(5300,h);
    assert(h.frames.empty()&&q.cancelled==1);++cases;}
  {FallQueue q;Hardware h;q.initialize(0);assert(q.test(1000));
    q.service(1000,h);q.service(1265,h);assert(q.controller.kind==Test);
    syn6658_voice::FallEvent e[2]={{71,1,true,true},{0,0,false,false}};
    q.observe(1500,e);h.query_result=Idle4F;q.service(1765,h);q.service(2000,h);q.service(2265,h);
    assert(q.controller.kind==Fall&&q.person_id==71&&q.controller.accepted==2);++cases;}
  {FallQueue q;Hardware h;q.initialize(0);h.send_result=NoReply;
    syn6658_voice::FallEvent e[2]={{1,1,true,true},{2,1,true,true}};
    q.observe(1000,e);q.service(1000,h);q.service(1200,h);
    assert(q.controller.failed==2&&!q.running()&&q.waiting()==0);++cases;}
  {FallQueue q;Hardware h;q.initialize(0xfffffc00u);
    syn6658_voice::FallEvent e[2]={{11,1,true,true},{22,1,true,true}};
    const uint32_t t=0xffffffe8u;q.observe(t,e);q.service(t,h);q.service(t+265,h);
    h.query_result=Idle4F;q.service(t+765,h);q.service(t+1000,h);q.service(t+1265,h);
    assert(q.controller.accepted==2&&q.person_id==22);++cases;}
  {FallQueue q;Hardware h;q.initialize(0);two_person_analysis::Manager m;
    const person_roi::Detection stand={{420,100,580,650},25000,true};
    const person_roi::Detection lie={{350,450,750,650},25000,true};
    const person_roi::Detection other={{900,100,1050,650},25000,true};
    const person_roi::Detection other_lie={{800,450,1200,650},25000,true};
    unsigned first=0,second=0;
    for(unsigned t=0;t<3200;t+=200){
      const auto r=m.update(t,t,t>=1000?lie:stand,t>=1800?other_lie:other,false,true);
      syn6658_voice::FallEvent e[2];
      for(unsigned lane=0;lane<2;++lane){const auto& f=r.lane_falls[lane];
        e[lane]={m.track(lane).id,f.events,f.alarm,f.event};
        if(f.event){if(t<1800)++first;else ++second;}}
      q.observe(t,e);q.service(t,h);
    }
    assert(first==1&&second==1&&q.queued==2&&q.controller.accepted==1);
    h.query_result=Idle4F;q.service(3400,h);q.service(3700,h);q.service(4000,h);
    assert(q.controller.accepted==2);++cases;}
  printf("UART_TEST_PASS cases=%u source=SYNTHETIC_OFFLINE acoustic_verified=0\n",cases);
}
