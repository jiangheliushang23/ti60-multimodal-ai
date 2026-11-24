#include "multimodal_alignment.h"
#include "scene_power.h"
#include "thermal_wake.h"
#include "person_pair.h"
void compat_fatal(const char*);
#include "camera_auto_service.h"
extern "C" unsigned checks=0;
#define CHECK(x) do{++checks;if(!(x))return __LINE__;}while(0)
unsigned test_ms=0;
uint32_t milliseconds(){return test_ms;}
void log_line(const char*,...){}
void compat_fatal(const char*){for(;;){}}

extern "C" int test_pair(){
 using namespace person_roi;
 const auto fullview=full();
 auto box=[&](Rect r,unsigned score)->Box{
  return {fullview.px*256+r.x1*fullview.nw*256/1280,fullview.py*256+r.y1*fullview.nh*256/720,
          fullview.px*256+r.x2*fullview.nw*256/1280,fullview.py*256+r.y2*fullview.nh*256/720,score};
 };
 Box b[4]={box({100,100,400,650},24000),box({800,120,1100,660},22000),
           box({110,110,390,640},12000),box({500,300,510,310},25000)};
 person_pair::Detections candidates;candidates.add(fullview,b,4);CHECK(candidates.count==2);
 const auto first=candidates.items[0],second=candidates.second(first,true);
 CHECK(first.valid&&second.valid&&second.score==22000);
 CHECK(first.box.x1>=98&&first.box.x1<=100&&second.box.x1>=798);
 CHECK(!person_pair::duplicate(first.box,second.box));CHECK(!candidates.second(first,false).valid);
 CHECK(candidates.second(second,true).score==24000);
 Detection none={{0,0,0,0},0,false};CHECK(candidates.second(none,true).score==24000);
 person_pair::Detections one;one.add(fullview,b,1);CHECK(!one.second(first,true).valid);
 person_pair::Detections empty;CHECK(!empty.second(none,true).valid);
 Box weak=box({700,100,1000,650},8191);empty.add(fullview,&weak,1);CHECK(!empty.count);
 // A duplicate from the same-frame crop must not become a second person.
 auto crop=view({640,0,1280,720});Rect r=second.box;
 Box local={(r.x1-640)*crop.nw*256/640+crop.px*256,r.y1*crop.nh*256/720+crop.py*256,
            (r.x2-640)*crop.nw*256/640+crop.px*256,r.y2*crop.nh*256/720+crop.py*256,23000};
 candidates.add(crop,&local,1);CHECK(candidates.count==2);CHECK(candidates.second(first,true).score==23000);
 // Any person keeps NORMAL and can satisfy a wake window, regardless of slot.
 scene_power::Manager power;power.mode=scene_power::Recovering;power.camera_state(1000,false,true,false);
 power.observe(1200,false||second.valid,false);CHECK(power.mode==scene_power::Normal);
 for(unsigned t=2000;t<=40000;t+=1000)power.observe(t,second.valid,false);
 CHECK(power.mode==scene_power::Normal&&!power.empty);
 CHECK(!person_pair::usable({{-1,0,200,400},20000,true}));
 CHECK(!person_pair::usable({{0,0,1281,400},20000,true}));
 CHECK(!person_pair::usable({{0,0,200,721},20000,true}));
 return 0;
}

extern "C" int test_alignment(){
 static multimodal_alignment::History h;h.reset();
 static multimodal_alignment::Result r;
 int16_t a[768],b[768];for(unsigned i=0;i<768;++i){a[i]=1000+i;b[i]=2000+i;}
 h.match(1000,12,r);CHECK(!r.infrared_valid&&!r.environment_valid&&r.video_sequence==12);
 h.push_ir(900,1,0,true,a);h.push_ir(1020,2,1,true,b);
 h.push_ir(600,3,0,true,b);h.push_env(950,5,2501,5020);h.push_env(1200,6,2602,6020);
 h.match(1000,13,r);CHECK(r.infrared_valid&&r.environment_valid);
 CHECK(r.ir_sequence[0]==1&&r.ir_sequence[1]==2&&r.ir_delta_ms[0]==-100&&r.ir_delta_ms[1]==20);
 CHECK(r.env_sequence==5&&r.env_temperature==2501&&r.env_humidity==5020&&r.env_delta_ms==-50);
 for(unsigned i=0;i<768;++i)CHECK(r.temperature[i]==((((i/32)&1)^(i&1))?b[i]:a[i]));
 CHECK(r.minimum==1000&&r.maximum==2766&&r.center==a[400]);
 // Samples arriving after a frame can still be nearest when inference finishes.
 h.push_ir(990,4,0,true,b);h.match(1000,14,r);CHECK(r.ir_sequence[0]==4);
 h.match(5000,15,r);CHECK(!r.infrared_valid&&!r.environment_valid&&r.ir_sequence[0]==0&&r.env_ms==0&&r.maximum==0);
 h.reset();h.push_ir(0xfffffff0,10,0,false,a);h.push_ir(10,11,1,false,b);h.push_env(0xfffffff0,12,1,2);
 h.match(4,99,r);CHECK(r.infrared_valid&&r.environment_valid&&r.ir_delta_ms[0]==-20&&r.ir_delta_ms[1]==6);
 for(unsigned i=0;i<768;++i)CHECK(r.temperature[i]==((i/32)&1?b[i]:a[i]));
 h.push_ir(20,13,0,true,a);h.match(20,100,r);CHECK(!r.infrared_valid); // mode switch invalidates incompatible pages
 h.push_ir(21,14,1,true,b);h.invalidate_env();h.match(20,101,r);CHECK(r.infrared_valid&&!r.environment_valid);
 h.invalidate_ir();h.match(20,102,r);CHECK(!r.infrared_valid);
 for(unsigned i=0;i<100;++i){h.push_ir(1000+i*10,i,i&1,true,a);h.push_env(1000+i*10,i,1,2);}
 h.match(1990,103,r);CHECK(r.infrared_valid&&r.ir_sequence[0]==98&&r.ir_sequence[1]==99&&r.env_sequence==99);
 h.reset();h.push_ir(650,1,0,true,a);h.push_ir(1350,2,1,true,b);h.push_env(2500,1,1,2);
 h.match(1000,1,r);CHECK(r.infrared_valid&&r.environment_valid); // inclusive tolerance boundary
 h.match(999,2,r);CHECK(!r.infrared_valid&&!r.environment_valid);
 return 0;
}
extern "C" int test_power(){
 scene_power::Manager p;CHECK(p.inference_allowed()&&!p.led()&&!p.want_low());
 p.observe(10000,false,false);
 CHECK(scene_power::Manager::kEmptyMs==30000);
 for(unsigned t=11000;t<40000;t+=1000)p.observe(t,false,false);
 p.observe(39999,false,false);
 CHECK(p.mode==scene_power::Normal&&p.empty_ms(39999)==29999);
 p.observe(40000,false,false);CHECK(p.mode==scene_power::Entering&&p.want_low()&&p.inference_allowed()&&!p.led());
 p.camera_state(190001,true,false,false);CHECK(p.mode==scene_power::Entering);
 p.camera_state(190200,true,true,false);CHECK(p.mode==scene_power::Sleep&&!p.inference_allowed()&&p.led());
 p.wake(191000);CHECK(p.mode==scene_power::Recovering&&!p.want_low()&&p.led()&&!p.inference_allowed());
 p.camera_state(191001,true,true,false);CHECK(p.mode==scene_power::Recovering);
 p.camera_state(191500,false,true,false);CHECK(p.mode==scene_power::Verifying&&p.inference_allowed()&&p.led()&&!p.empty);
 p.observe(191600,true,false);CHECK(p.mode==scene_power::Normal&&!p.led()&&!p.empty);
 p.observe(192000,false,false);p.observe(192100,true,false);CHECK(!p.empty);
 p.observe(193000,false,false);p.observe(193100,false,true);CHECK(!p.empty);
 p.observe(194000,false,false);p.no_frame(198000);CHECK(!p.empty&&p.mode==scene_power::Normal);
 p.observe(200000,false,false);p.observe(204000,false,false);CHECK(p.empty_ms(204000)==0); // capture gap is not evidence
 p.mode=scene_power::Entering;p.observe(205000,true,false);CHECK(p.mode==scene_power::Recovering);
 p.mode=scene_power::Entering;p.no_frame(209000);CHECK(p.mode==scene_power::Recovering);
 p.mode=scene_power::Sleep;p.camera_state(210000,true,false,true);CHECK(p.mode==scene_power::Normal&&!p.led()&&!p.empty);
 // Thirty seconds must also work when the millisecond counter wraps.
 scene_power::Manager w;unsigned start=0xfffff000;
 w.observe(start,false,false);for(unsigned t=1000;t<=30000;t+=1000)w.observe(start+t,false,false);
 CHECK(w.mode==scene_power::Entering);
 w.camera_state(start+30100,true,true,false);CHECK(w.led());w.wake(start+31000);CHECK(w.led());
 w.camera_state(start+31100,false,true,false);CHECK(w.mode==scene_power::Verifying&&w.led());
 w.observe(start+31200,false,false);CHECK(w.mode==scene_power::Verifying&&w.led());
 for(unsigned t=32200;t<36100;t+=500){w.observe(start+t,false,false);w.tick(start+t);CHECK(w.mode==scene_power::Verifying);}
 w.tick(start+36099);CHECK(w.mode==scene_power::Verifying&&w.inference_allowed());
 w.tick(start+36100);CHECK(w.mode==scene_power::Entering&&w.verification_rejected&&!w.inference_allowed()&&w.led());
 w.camera_state(start+36500,true,true,false);CHECK(w.mode==scene_power::Sleep&&!w.inference_allowed());
 w.wake(start+37000);w.camera_state(start+37200,false,true,false);w.observe(start+37300,true,false);
 CHECK(w.mode==scene_power::Normal&&!w.led()&&!w.verification_rejected);
 // A person arriving just before the deadline starts a fresh empty interval.
 scene_power::Manager q;
 for(unsigned t=10000;t<=39000;t+=1000)q.observe(t,false,false);
 q.observe(39999,true,false);CHECK(!q.empty&&q.mode==scene_power::Normal);
 for(unsigned t=40000;t<=69000;t+=1000)q.observe(t,false,false);
 q.observe(69999,false,false);CHECK(q.mode==scene_power::Normal&&q.empty_ms(69999)==29999);
 q.observe(70000,false,false);CHECK(q.mode==scene_power::Entering);
 // Five seconds is measured from restored normal-rate camera operation.
 scene_power::Manager v;v.mode=scene_power::Sleep;v.wake(100);
 v.tick(10000);CHECK(v.mode==scene_power::Recovering); // restoration is not inference time
 v.camera_state(11000,false,true,false);v.observe(10999,true,false);CHECK(v.mode==scene_power::Verifying);
 v.observe(12000,false,false);v.tick(15999);CHECK(v.mode==scene_power::Verifying);
 v.observe(15999,true,false);CHECK(v.mode==scene_power::Normal&&!v.led());
 v.tick(16000);CHECK(v.mode==scene_power::Normal); // no stale deadline after positive
 scene_power::Manager n;n.mode=scene_power::Recovering;n.camera_state(1000,false,true,false);
 n.no_frame(5000);n.tick(5999);CHECK(n.mode==scene_power::Verifying);
 n.tick(6000);CHECK(n.mode==scene_power::Entering&&!n.inference_allowed()); // no endless VERIFY if inference stalls
 CHECK(scene_power::display_status(scene_power::Sleep,50,true)==0x050a);
 CHECK(scene_power::display_status(scene_power::Sleep,49,true)==0x049a);
 CHECK(scene_power::display_status(scene_power::Sleep,0,false)==2);
 CHECK(scene_power::display_status(scene_power::Normal,1000,true)==0x9998);
 return 0;
}
extern "C" int test_thermal_wake(){
 ThermalWake w;int16_t p[768];uint8_t bad[768]={};unsigned seq=0;
 auto plain=[&](int temp){for(auto& x:p)x=temp;};
 auto patch=[&](int temp){for(unsigned y=8;y<12;++y)for(unsigned x=12;x<16;++x)p[y*32+x]=temp;};
 auto update=[&](unsigned now,unsigned page){return w.update(now,++seq,page,true,p,bad);};
 plain(2500);patch(3300);CHECK(!update(0,0)); // disabled in normal mode
 w.set_enabled(true);plain(2500);CHECK(!update(100,0));CHECK(!update(200,1));
 // Small warm object and one-pixel noise cannot wake the CPU.
 p[300]=3600;CHECK(!update(300,0));CHECK(!update(500,1));CHECK(w.area<6);
 // A stationary body-like thermal region can wake: no motion is required.
 plain(2500);patch(3300);CHECK(!update(600,0));CHECK(w.area==16&&w.background_centi==2500);
 CHECK(!update(800,1));CHECK(update(1000,0));CHECK(w.duration_ms==400&&w.samples==3);
 CHECK(w.update(3000,seq,0,true,p,bad));CHECK(w.samples==3); // duplicate cannot advance duration
 plain(2500);CHECK(!update(1100,1));CHECK(!w.confirmed);
 // Below 36 C must still be detected, and no fixed palette indices are used.
 patch(2800);CHECK(!update(1200,0));CHECK(!update(1400,1));CHECK(update(1600,0));
 // Uniform ambient changes and insufficient contrast cannot create a hot blob.
 plain(3400);CHECK(!update(1800,1));CHECK(!update(2000,0));
 plain(3200);patch(3300);CHECK(!update(2200,1));CHECK(!update(2400,0));
 // Invalid pixels and very hot appliances do not satisfy this body-temperature gate.
 plain(2500);patch(6000);CHECK(!update(2600,1));CHECK(!update(2800,0));
 patch(3300);for(unsigned y=8;y<12;++y)for(unsigned x=12;x<16;++x)bad[y*32+x]=1;
 CHECK(!update(3000,1));CHECK(!update(3200,0));for(auto& x:bad)x=0;
 // Require both fresh subpages after re-arming, even if a complete old map exists.
 w.set_enabled(false);w.set_enabled(true);CHECK(!update(4000,0));CHECK(!update(4500,0));
 CHECK(!update(4600,1));CHECK(!update(4800,0));CHECK(update(5000,1));
 // A missing page or long sampling gap invalidates persistence.
 CHECK(!update(7000,0));CHECK(!update(7100,1));CHECK(!update(7200,0));CHECK(update(7500,1));
 w.reset();unsigned start=0xffffff00;CHECK(!update(start,0));CHECK(!update(start+100,1));
 CHECK(!update(start+300,0));CHECK(update(start+500,1));
 // Disconnected hot pixels have no single connected region of the minimum area.
 w.reset();plain(2500);for(unsigned i=0;i<8;++i)p[40+i*66]=3300;
 CHECK(!update(0,0));CHECK(!update(200,1));CHECK(!update(700,0));
 // Static warm furnishings in a visually empty scene must not immediately
 // wake LOW. A new stationary warm body remains detectable against it.
 ThermalWake f;plain(2500);patch(3300);
 f.observe_visual(100,false);CHECK(!f.update(100,1,0,true,p,bad));
 f.observe_visual(200,false);CHECK(!f.update(200,2,1,true,p,bad));CHECK(f.background_pages==3);
 f.set_enabled(true);CHECK(!f.update(300,3,0,true,p,bad));CHECK(f.use_background);
 CHECK(!f.update(500,4,1,true,p,bad));CHECK(!f.update(900,5,0,true,p,bad));CHECK(f.area==0);
 for(unsigned y=15;y<19;++y)for(unsigned x=20;x<24;++x)p[y*32+x]=3100;
 CHECK(!f.update(1000,6,1,true,p,bad));CHECK(!f.update(1200,7,0,true,p,bad));CHECK(f.update(1500,8,1,true,p,bad));
 CHECK(f.area==16&&f.use_background); // old 16-pixel warm object excluded
 for(unsigned i=0;i<9;++i)CHECK(f.update(1800+i*250,9+i,i&1,true,p,bad)); // reference is frozen during sleep
 f.set_enabled(false);f.observe_visual(4100,true);CHECK(f.background_pages==0);
 f.set_enabled(true);CHECK(!f.use_background); // never learn a YOLO-confirmed body
 // Expired empty evidence cannot suppress the first thermal candidate.
 ThermalWake old;old.observe_visual(0,false);plain(2500);patch(3300);
 old.update(0,1,0,true,p,bad);old.update(100,2,1,true,p,bad);old.set_enabled(true);
 CHECK(!old.update(4000,3,0,true,p,bad)&&!old.use_background);
 // A five-second visual rejection adopts a new stationary warm object.
 ThermalWake rejected;plain(2500);rejected.observe_visual(0,false);
 rejected.update(0,1,0,true,p,bad);rejected.update(100,2,1,true,p,bad);rejected.set_enabled(true);patch(3300);
 CHECK(!rejected.update(200,3,0,true,p,bad));CHECK(!rejected.update(400,4,1,true,p,bad));CHECK(!rejected.update(700,5,0,true,p,bad));CHECK(rejected.update(900,6,1,true,p,bad));
 rejected.set_enabled(false);rejected.reject_candidate(6000,20,true,p,bad);rejected.set_enabled(true);
 CHECK(!rejected.update(6100,21,1,true,p,bad));CHECK(!rejected.update(6300,22,0,true,p,bad));CHECK(!rejected.update(6600,23,1,true,p,bad));
 CHECK(rejected.area==0&&rejected.use_background);
 for(unsigned y=15;y<19;++y)for(unsigned x=20;x<24;++x)p[y*32+x]=3200;
 CHECK(!rejected.update(6800,24,0,true,p,bad));CHECK(!rejected.update(7000,25,1,true,p,bad));CHECK(rejected.update(7200,26,0,true,p,bad));
 return 0;
}
extern "C" int test_motion(){
 scene_power::MotionWake m;uint8_t p[384];for(auto& x:p)x=60;
 CHECK(!m.update(p));for(unsigned i=0;i<20;++i)CHECK(!m.update(p));
 for(auto& x:p)x=100;CHECK(!m.update(p));CHECK(!m.update(p)); // uniform exposure jump
 for(auto& x:p)x=60;m.reset(p);
 for(unsigned y=4;y<12;++y)for(unsigned x=9;x<14;++x)p[y*24+x]=160;
 CHECK(!m.update(p));CHECK(m.update(p));
 for(auto& x:p)x=60;CHECK(!m.update(p)); // confirmation resets on quiet frame
 return 0;
}
extern "C" int test_scene(){
 scene_power::Manager power;ThermalWake thermal;int16_t p[768];uint8_t bad[768]={};
 for(auto& x:p)x=2500;
 for(unsigned t=1000;t<=31000;t+=1000)power.observe(t,false,false);
 CHECK(power.mode==scene_power::Entering&&!power.led());
 power.camera_state(31200,true,true,false);thermal.set_enabled(power.mode==scene_power::Sleep);
 CHECK(!power.inference_allowed()&&power.led());
 CHECK(!thermal.update(31300,1,0,true,p,bad));CHECK(!thermal.update(31400,2,1,true,p,bad));
 for(unsigned y=8;y<14;++y)for(unsigned x=11;x<16;++x)p[y*32+x]=3100;
 CHECK(!thermal.update(31500,3,0,true,p,bad));CHECK(!thermal.update(31700,4,1,true,p,bad));
 CHECK(thermal.update(31900,5,0,true,p,bad));power.wake(31900);
 CHECK(power.mode==scene_power::Recovering&&power.led()&&!power.inference_allowed());
 power.camera_state(32000,false,false,false);CHECK(!power.inference_allowed());
 power.camera_state(32200,false,true,false);CHECK(power.mode==scene_power::Verifying&&power.inference_allowed()&&power.led());
 power.observe(32300,true,false);CHECK(power.mode==scene_power::Normal&&!power.led()&&!power.empty);
 // A warm object receives a full five-second window, then returns to LOW.
 for(unsigned t=33000;t<=63000;t+=1000)power.observe(t,false,false);
 power.camera_state(63200,true,true,false);CHECK(power.mode==scene_power::Sleep);
 power.wake(64000);power.camera_state(64200,false,true,false);power.observe(64300,false,false);
 CHECK(power.mode==scene_power::Verifying&&power.led());
 for(unsigned t=65000;t<69200;t+=500){power.observe(t,false,false);power.tick(t);CHECK(power.mode==scene_power::Verifying);}
 power.tick(69199);CHECK(power.inference_allowed());power.tick(69200);
 CHECK(power.mode==scene_power::Entering&&power.want_low()&&!power.inference_allowed()&&power.led());
 thermal.set_enabled(false);thermal.reject_candidate(69200,6,true,p,bad);
 power.camera_state(69700,true,true,false);CHECK(power.mode==scene_power::Sleep);
 thermal.set_enabled(true);CHECK(!thermal.update(69800,7,1,true,p,bad));CHECK(!thermal.update(70000,8,0,true,p,bad));
 CHECK(!thermal.update(70400,9,1,true,p,bad)&&!power.inference_allowed());
 return 0;
}
extern "C" int test_rate(){
 CameraRate r;volatile uint32_t a[19]={};
 auto drive=[&](unsigned now)->int{
  const bool slow=r.target;
  for(unsigned n=0;n<6;++n){
   if(r.state==CameraRate::Apply){a[13]+=2;r.step(++now,a);}
   if(r.state==CameraRate::Gap)r.step(++now,a);
   if(r.state!=CameraRate::Start)return 1;
   r.step(now,a);
   const uint32_t expected=(n>=4?1u<<24:0)|(unsigned(CameraRate::value(n,slow))<<16)|CameraRate::address(n);
   if(a[14]!=expected||a[15]!=1||r.state!=CameraRate::Wait)return 2;
   a[16]=0x100|CameraRate::value(n,slow);now+=CameraRate::kCommandGuardMs;r.step(now,a);
  }
  if(r.state!=CameraRate::Settle)return 3;
  a[13]++;r.step(++now,a);if(r.state!=CameraRate::Settle)return 4;
  a[13]++;r.step(++now,a);return r.settled()?0:5;
 };
 r.request(true,10,0);CHECK(!r.settled());CHECK(drive(11)==0&&r.low&&!r.fault);
 r.request(false,100,2);CHECK(drive(101)==0&&!r.low);
 r.request(true,200,4);r.step(200,a);a[16]=0x200;r.step(203,a);
 CHECK(r.fault==3&&r.retries==1&&!r.target&&r.state==CameraRate::Gap);
 CHECK(drive(204)==0&&!r.low&&!r.fault); // failed partial hold restored at normal VTS
 r.request(true,300,6);r.step(300,a);a[1]=2;r.step(801,a);
 CHECK(r.fault==2&&r.retries==1);a[1]=0;CHECK(drive(802)==0&&!r.low);
 r.request(true,900,8);a[1]=10;r.step(1401,a);CHECK(r.fault==1);
 r.step(1402,a);r.step(1903,a);r.step(1904,a);r.step(2405,a);CHECK(r.state==CameraRate::Failed&&r.retries==2);
 // Tight callbacks must ignore stale success/read data before the CDC/bus
 // can complete. Even an ACK with physical-bus busy must not advance.
 CameraRate c;a[1]=0;c.request(true,0,0);c.step(0,a);a[16]=0x123;
 c.step(0,a);c.step(1,a);c.step(2,a);CHECK(c.command==0&&c.state==CameraRate::Wait&&!c.fault);
 a[1]=8;c.step(3,a);CHECK(c.state==CameraRate::Wait);a[1]=0;a[16]=0x100;c.step(4,a);CHECK(c.command==1);
 // Group release must wait for two genuinely new sensor SOFs before readback.
 CameraRate s;s.request(true,0,0);a[1]=0;
 for(unsigned n=0;n<4;++n){if(n)s.step(n*10,a);s.step(n*10+1,a);a[16]=0x100;s.step(n*10+4,a);}
 CHECK(s.state==CameraRate::Apply);s.step(40,a);CHECK(s.state==CameraRate::Apply);
 a[13]++;s.step(41,a);CHECK(s.state==CameraRate::Apply);a[13]++;s.step(42,a);CHECK(s.command==4&&s.state==CameraRate::Start);
 for(unsigned n=4;n<6;++n){if(n==5)s.step(n*10,a);s.step(n*10+1,a);a[16]=0x100|CameraRate::value(n,true);s.step(n*10+4,a);}
 CHECK(s.state==CameraRate::Settle);s.step(3000,a);CHECK(s.fault==5&&!s.target);
 // A terminal fault is retried after a bounded cooldown, never latched forever.
 r.retry_recovery(7404,a[13]);CHECK(r.state==CameraRate::Failed);
 r.retry_recovery(7405,a[13]);CHECK(r.state==CameraRate::Start&&!r.target&&r.retries==0);
 CHECK(drive(7406)==0&&!r.fault&&!r.low);
 // Readback mismatch must be diagnosed, not silently treated as low power.
 CameraRate d;d.request(true,0,0);d.command=4;d.step(0,a);a[16]=0x105;d.step(3,a);
 CHECK(d.fault==4&&d.failed_command==4&&d.failed_response==0x105&&!d.low);
 return 0;
}
extern "C" int test_service(){
 using namespace camera_auto_service;
 automatic=CameraAuto(registers,camera);rate=CameraRate{};enabled=true;desired_low=true;logged_rate_retry=0;
 volatile uint32_t* a=registers;for(unsigned i=0;i<19;++i)a[i]=0;
 automatic.ready=true;automatic.state=CameraAuto::BusWait;automatic.entered=0;
 a[1]=2;test_ms=1;service();CHECK(rate.settled()&&automatic.state==CameraAuto::BusWait);
 // Only a quiescent AE state may transfer I2C ownership to the VTS sequencer.
 automatic.state=CameraAuto::WaitFrames;test_ms=2;service();CHECK(rate.state==CameraRate::Start);
 const auto ae_state=automatic.state;a[1]=0;
 for(unsigned n=0;n<6;++n){
  if(rate.state==CameraRate::Apply){a[13]+=2;++test_ms;service();}
  if(rate.state==CameraRate::Gap){++test_ms;service();}
  ++test_ms;service();CHECK(a[14]==((n>=4?1u<<24:0)|(unsigned(CameraRate::value(n,true))<<16)|CameraRate::address(n)));
  CHECK(automatic.state==ae_state);a[16]=0x100|CameraRate::value(n,true);test_ms+=CameraRate::kCommandGuardMs;service();
 }
 CHECK(rate.state==CameraRate::Settle);a[13]+=2;++test_ms;service();CHECK(low_power()&&rate_settled());
 a[14]=0xdeadbeef;for(unsigned i=0;i<100;++i){++test_ms;service();}
 CHECK(a[14]==0xdeadbeef&&low_power()); // no AE I2C while sleeping
 request_low_power(false);++test_ms;service();CHECK(rate.state==CameraRate::Start);
 return 0;
}
