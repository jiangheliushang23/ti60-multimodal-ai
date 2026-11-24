#include <stdint.h>
#include <stdio.h>
#include "two_person_analysis.h"
#include "voice_fall_queue.h"
using namespace voice_uart;
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
extern "C" {unsigned recovery_cases=0,recovery_failed_line=0;}
namespace {
const fall_detection::Detection stand={210,150,370,650,25000,true},lie={120,450,520,650,25000,true};
const fall_detection::Detection absent={0,0,0,0,0,false};
const person_roi::Detection a={{210,150,370,650},25000,true},al={{120,450,520,650},25000,true};
const person_roi::Detection b={{900,150,1060,650},25000,true},bl={{810,450,1210,650},25000,true};
const person_roi::Detection none={{0,0,0,0},0,false};
void fall(fall_detection::Detector& d){
  for(unsigned t=0;t<=800;t+=200)d.update(t,stand);
  d.update(1000,lie);d.update(1200,lie);
}
struct Hardware {
  uint8_t frames[32][32]={};unsigned sizes[32]={},count=0;Result query_result=Idle4F;
  Result send(const uint8_t* bytes,unsigned size){
    if(size>32||count>=32)return Invalid;
    sizes[count]=size;for(unsigned i=0;i<size;++i)frames[count][i]=bytes[i];++count;return Ack41;
  }
  Result query(){return query_result;}
};
void complete_fall(FallQueue& q,Hardware& h){q.service(1000,h);q.service(1265,h);q.service(1765,h);}
bool phrase(const Hardware& h,unsigned at,const uint8_t* text,unsigned n){
  if(h.sizes[at]!=n+5||h.frames[at][0]!=0xfd||h.frames[at][2]!=n+2)return false;
  for(unsigned i=0;i<n;++i)if(h.frames[at][i+5]!=text[i])return false;
  return true;
}
}
extern "C" unsigned run_standing_recovery_tests(){
  recovery_cases=0;
  {
    fall_detection::Detector d;fall(d);CHECK(d.alarmed());
    for(unsigned t=1400;t<65000;t+=200){auto r=d.update(t,lie);CHECK(r.alarm&&!r.recovered&&!r.event);}
    for(unsigned t=65000;t<70000;t+=200){auto r=d.update(t,{210,330,370,650,25000,true});CHECK(r.alarm&&!r.recovered);}
    CHECK(d.update(75000,absent).alarm);CHECK(d.update(80000,lie).alarm);++recovery_cases;
  }
  {
    fall_detection::Detector d;fall(d);
    for(unsigned t=1400;t<8000;t+=200){auto s=stand;s.score=0;CHECK(d.update(t,s,true).alarm);}
    CHECK(d.update(8000,stand).alarm);CHECK(d.update(8400,stand).alarm);
    CHECK(d.update(8600,absent).alarm); // an interruption restarts standing confirmation
    for(unsigned t=8800;t<10000;t+=200)CHECK(d.update(t,stand).alarm);
    auto r=d.update(10000,stand);CHECK(!r.alarm&&r.recovered&&r.events==1);
    for(unsigned t=10200;t<14000;t+=200){r=d.update(t,stand);CHECK(!r.alarm&&!r.recovered);}
    ++recovery_cases;
  }
  {
    two_person_analysis::Manager m;two_person_analysis::Result r={};
    for(unsigned t=0;t<=800;t+=200)r=m.update(t,t,a,none,false,true);
    const unsigned id=r.ids[0];m.update(1000,1000,al,none,false,true);r=m.update(1200,1200,al,none,false,true);
    CHECK(r.alarm[0]);
    r=m.update(5000,5000,none,none,false,true);CHECK(r.any_alarm&&r.visible==0&&r.active==1);
    r=m.update(5200,5200,al,none,false,true);CHECK(r.ids[0]==id&&r.alarm[0]);
    CHECK((two_person_analysis::flags(r.detections[0],id,r.alarm[0])&15)==7);
    for(unsigned t=5400;t<6600;t+=200){r=m.update(t,t,a,none,false,true);CHECK(r.alarm[0]);}
    r=m.update(6600,6600,a,none,false,true);CHECK(r.ids[0]==id&&!r.alarm[0]&&r.falls[0].recovered);
    CHECK((two_person_analysis::flags(r.detections[0],id,r.alarm[0])&15)==3);++recovery_cases;
  }
  {
    two_person_analysis::Manager m;two_person_analysis::Result r={};
    for(unsigned t=0;t<=800;t+=200)r=m.update(t,t,a,b,false,true);
    unsigned left=r.ids[0],right=r.ids[1];m.update(1000,1000,al,bl,false,true);
    r=m.update(1200,1200,bl,al,false,true);CHECK(r.ids[0]==right&&r.ids[1]==left&&r.alarm[0]&&r.alarm[1]);
    for(unsigned t=1400;t<5000;t+=200)r=m.update(t,t,bl,al,false,true);
    for(unsigned t=5000;t<6200;t+=200){r=m.update(t,t,bl,a,false,true);CHECK(r.alarm[0]&&r.alarm[1]);}
    r=m.update(6200,6200,bl,a,false,true);CHECK(r.ids[0]==right&&r.ids[1]==left&&r.alarm[0]&&!r.alarm[1]&&r.falls[1].recovered);
    for(unsigned t=6400;t<7600;t+=200){r=m.update(t,t,a,b,false,true);CHECK(!r.alarm[0]&&r.alarm[1]);}
    r=m.update(7600,7600,a,b,false,true);CHECK(!r.any_alarm&&r.falls[1].recovered&&!r.falls[0].recovered);++recovery_cases;
  }
  {
    two_person_analysis::Manager m;two_person_analysis::Result r={};
    for(unsigned t=0;t<=800;t+=200)r=m.update(t,t,a,b,false,true);
    auto old=r.ids[0];m.update(1000,1000,al,b,false,true);r=m.update(1200,1200,al,b,false,true);CHECK(r.alarm[0]);
    const person_roi::Detection new_person={{580,50,650,400},25000,true};
    r=m.update(1400,1400,new_person,b,false,true);
    CHECK(r.ids[0]!=old&&!r.alarm[0]&&!r.falls[0].recovered);++recovery_cases;
  }
  {
    FallQueue q;Hardware h;q.initialize(0);syn6658_voice::FallEvent e[2]={{11,1,true,true,false,true},{0,0,false,false,false,false}};
    q.observe(1000,e);complete_fall(q,h);CHECK(q.controller.uart_completed==1);
    e[0]={11,1,false,false,true,false};CHECK(q.observe(2000,e)==0&&q.waiting()==0);
    e[0].recovered=false;e[0].displayed=true;CHECK(q.observe(2100,e)==4&&q.waiting()==1);
    for(unsigned t=2200;t<2500;t+=100)q.observe(t,e);
    CHECK(q.queued==2&&q.waiting()==1);q.service(2500,h);q.service(2765,h);CHECK(q.controller.kind==Recovery);
    CHECK(phrase(h,3,kRecoveryIntro,sizeof(kRecoveryIntro)));
    q.service(3265,h);CHECK(q.running()&&q.controller.uart_completed==1);
    q.service(3500,h);q.service(3765,h);CHECK(phrase(h,5,kRecoverySafety,sizeof(kRecoverySafety)));
    q.service(4265,h);CHECK(q.controller.uart_completed==2&&!q.running());
    for(unsigned t=4400;t<8000;t+=200){e[0].recovered=true;q.observe(t,e);q.service(t,h);}
    CHECK(q.queued==2&&h.count==6);++recovery_cases;
  }
  {
    FallQueue q;Hardware h;q.initialize(0);syn6658_voice::FallEvent e[2]={{1,0,false,false,false,true},{2,0,false,false,false,true}};
    for(unsigned t=1000;t<5000;t+=200){q.observe(t,e);q.service(t,h);}CHECK(h.count==0);
    e[0]={1,1,true,true,false,true};q.observe(5100,e);q.service(5100,h);q.service(5365,h);q.service(5865,h);
    e[0]={1,1,false,false,true,false};q.observe(6000,e);e[0]={3,0,false,false,false,true};q.observe(6200,e);q.service(6200,h);
    CHECK(q.queued==1&&h.count==2);++recovery_cases;
  }
  {
    FallQueue q;Hardware h;q.initialize(0);
    syn6658_voice::FallEvent e[2]={{11,1,false,false,true,true},{22,1,false,false,true,true}};
    CHECK(q.observe(1000,e)==12&&q.waiting()==2);
    q.service(1000,h);q.service(1265,h);q.service(1765,h);q.service(2000,h);q.service(2265,h);q.service(2765,h);
    CHECK(q.controller.uart_completed==1&&q.person_id==11);
    q.service(3000,h);q.service(3265,h);q.service(3765,h);q.service(4000,h);q.service(4265,h);q.service(4765,h);
    CHECK(q.controller.uart_completed==2&&q.person_id==22&&h.count==8&&q.waiting()==0);++recovery_cases;
  }
  {
    FallQueue q;Hardware h;q.initialize(0);
    syn6658_voice::FallEvent e[2]={{11,1,false,false,true,true},{22,0,false,false,false,true}};
    q.observe(1000,e);q.service(1000,h);q.service(1265,h);CHECK(q.controller.kind==Recovery);
    e[0].recovered=false;e[1]={22,1,true,true,false,true};CHECK(q.observe(1400,e)==2);
    q.service(1500,h);q.service(1765,h);CHECK(q.controller.kind==Fall&&phrase(h,3,kFall,sizeof(kFall)));
    q.service(2265,h);CHECK(q.controller.uart_completed==1&&h.count==4);++recovery_cases;
  }
  {
    FallQueue q;Hardware h;q.initialize(0);
    syn6658_voice::FallEvent e[2]={{11,1,false,false,true,true},{22,0,false,false,false,true}};
    q.observe(1000,e);e[0].recovered=false;e[1]={22,1,true,true,false,true};q.observe(1100,e);
    CHECK(q.waiting()==2);q.service(1200,h);CHECK(q.person_id==22&&q.waiting()==1);
    q.service(1465,h);q.service(1965,h);q.service(2200,h);q.service(2465,h);
    CHECK(q.person_id==11&&q.controller.kind==Recovery);++recovery_cases;
  }
  {
    FallQueue q;Hardware h;const uint32_t t=0xffffffe8u;q.initialize(t-1000);
    syn6658_voice::FallEvent e[2]={{11,2,false,false,true,true},{0,0,false,false,false,false}};
    q.observe(t,e);q.service(t,h);q.service(t+265,h);q.service(t+765,h);q.service(t+1000,h);q.service(t+1265,h);q.service(t+1765,h);
    CHECK(q.controller.uart_completed==1&&h.count==4);++recovery_cases;
  }
  return 0;
}
#ifdef HOST_TEST
int main(){
  recovery_failed_line=run_standing_recovery_tests();
  printf("STANDING_RECOVERY cases=%u failed_line=%u\n",recovery_cases,recovery_failed_line);
  return recovery_failed_line?1:0;
}
#endif
