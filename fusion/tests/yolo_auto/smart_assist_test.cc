#include <stdint.h>
#include <stdio.h>
#include "thermal_presence.h"
#include "voice_fall_queue.h"
using namespace voice_uart;
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
extern "C" {unsigned smart_cases=0;}
struct Hardware {
 unsigned count=0,sizes[16]={0};uint8_t frames[16][32]={};
 Result send(const uint8_t* p,unsigned n){if(n>32||count>=16)return Invalid;sizes[count]=n;for(unsigned i=0;i<n;++i)frames[count][i]=p[i];++count;return Ack41;}
 Result query(){return Idle4F;}
};
extern "C" int run_smart_tests(){
 int16_t t[768];for(unsigned i=0;i<768;++i)t[i]=2200;
 CHECK(thermal_presence::summarize(t,false)==0);
 CHECK(thermal_presence::summarize(t,true)==0xa1000000u);++smart_cases;
 for(unsigned y=8;y<12;++y)for(unsigned x=10;x<14;++x)t[y*32+x]=3500;
 uint32_t s=thermal_presence::summarize(t,true);CHECK((s&1023)==16&&((s>>10)&1023)==16);++smart_cases;
 for(unsigned i=0;i<768;++i)t[i]=5000;
 CHECK((thermal_presence::summarize(t,true)&0xfffff)==0);++smart_cases;
 for(unsigned i=0;i<768;++i)t[i]=3400;
 CHECK((thermal_presence::summarize(t,true)&0xfffff)==0);++smart_cases;
 for(unsigned i=0;i<768;++i)t[i]=2200;t[0]=3500;t[31]=3500;t[32]=3500;
 s=thermal_presence::summarize(t,true);CHECK((s&1023)==3&&((s>>10)&1023)==2);++smart_cases;
 {
  FallQueue q;Hardware h;q.initialize(0);CHECK(q.unauthorized(1000));
  syn6658_voice::FallEvent none[2]={{0,0,false,false,false,false},{0,0,false,false,false,false}};
  q.observe(1000,none);q.service(1000,h);CHECK(q.controller.kind==Unauthorized&&q.controller.phase==Gap);
  q.service(1265,h);CHECK(q.controller.phase==Playing&&h.count==2&&h.sizes[1]==sizeof(kUnauthorizedIntro)+5);
  q.service(1765,h);CHECK(q.controller.uart_completed==0);
  q.service(2000,h);q.service(2265,h);q.service(2765,h);CHECK(q.controller.uart_completed==1);
  CHECK(h.count==4&&h.sizes[3]==sizeof(kUnauthorizedEnd)+5);++smart_cases;
 }
 {
  FallQueue q;Hardware h;q.initialize(0);CHECK(q.unauthorized(1000));q.service(1000,h);q.service(1265,h);
  syn6658_voice::FallEvent fall[2]={{7,1,true,true,false,true},{0,0,false,false,false,false}};
  q.observe(1400,fall);q.service(1600,h);CHECK(q.controller.kind==Fall&&q.controller.phase==Gap);
  q.service(1865,h);CHECK(q.controller.phase==Playing&&h.sizes[h.count-1]==sizeof(kFall)+5);++smart_cases;
 }
 {
  FallQueue q;Hardware h;q.initialize(0);q.unauthorized(1000);q.clear(1000);q.service(1200,h);CHECK(h.count==0);++smart_cases;
 }
 {
  // A latched red box does not indefinitely silence another person's access alert.
  FallQueue q;Hardware h;q.initialize(0);
  syn6658_voice::FallEvent old[2]={{7,1,true,false,false,true},{0,0,false,false,false,false}};
  CHECK(q.unauthorized(1000));q.observe(1000,old);q.service(1000,h);
  CHECK(q.controller.kind==Unauthorized&&q.controller.phase==Gap);++smart_cases;
 }
 return 0;
}
#ifdef HOST_TEST
int main(){int code=run_smart_tests();printf("SMART_TEST cases=%u failed_line=%d\n",smart_cases,code);return code?1:0;}
#endif
