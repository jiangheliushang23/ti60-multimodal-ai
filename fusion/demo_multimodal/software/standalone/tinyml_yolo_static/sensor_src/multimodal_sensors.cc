#include <cmath>
#include <cstring>
#include "port.h"
#include "multimodal_sensors.h"
#include "thermal_range.h"
#include "thermal_display.h"
#include "thermal_compute.h"
#include "thermal_rate.h"
#include "thermal_wake.h"

namespace multimodal_sensors {
namespace {
volatile uint32_t* const io=reinterpret_cast<volatile uint32_t*>(0xf8103000u);
volatile uint32_t* const buffer=reinterpret_cast<volatile uint32_t*>(0xf8104000u);
volatile uint32_t* const image=reinterpret_cast<volatile uint32_t*>(0xf8106000u);
volatile uint32_t* const record=reinterpret_cast<volatile uint32_t*>(0xf8101020u);
volatile uint32_t* const hdmi=reinterpret_cast<volatile uint32_t*>(0xf8101000u);
volatile uint32_t* const sht=reinterpret_cast<volatile uint32_t*>(0xf8102000u);
uint16_t ee[832],frame[834],next_frame[834],control;
paramsMLX90640 params;
float temperatures[768],ta;
int16_t centi[768];uint8_t bad[768];ThermalDisplay display;ThermalCompute compute;ThermalRate rate;
multimodal_alignment::History history;multimodal_alignment::Result aligned;
unsigned sample_ms=0,thermal_activity_seq=0,thermal_last_valid=0;bool thermal_activity=false;
ThermalWake thermal_detector;
bool enabled=false,inside=false,active=false,retry_wait=false;
unsigned command_address,command_words,command_data,command_read,attempt,started,retry_at;
unsigned wake=0,last_poll=0,last_fresh=0,last_sht=0,last_sht_log=0,frames=0,pages=0;
unsigned page_time[2]={0,0},pixel=0,read_ms=0,calc_start=0,last_publish=0,published=0;
unsigned pending_error=8;
unsigned refresh_code=5,overruns=0,overrun_streak=0,last_ir_log=0;
unsigned captured_page=0,error_streak=0,last_display=0,recoveries=0;
unsigned command_started=0,next_sample_ms=0,next_page=0,next_read_ms=0,next_read_start=0,next_error=0;
bool next_ready=false,next_rate_drop=false;
bool calibrated=false,restart_calibration=true,have_display=false;
const unsigned kDisplayStaleMs=3000;
enum State {Boot,EeFirst,EeSecond,Extract,ControlRead,ControlWrite,ControlCheck,
 Poll,Status,Clear,ReadFrame,CheckFrame,Calculate,Publish,Acknowledge,NextFrame,Backoff};
State state=Boot;
enum Acquisition {AcqIdle,AcqPoll,AcqStatus,AcqClear,AcqRead,AcqCheck};
Acquisition acquisition=AcqIdle;
bool elapsed(unsigned now,unsigned before,unsigned delay){return unsigned(now-before)>=delay;}
bool due(unsigned now,unsigned deadline){return int32_t(now-deadline)>=0;}
void fence(){asm volatile("fence iorw,iorw":::"memory");}
unsigned bcd_unsigned(unsigned n){unsigned q=0;for(unsigned i=0;i<5;++i){q|=(n%10)<<(i*4);n/=10;}return q;}
unsigned bcd_temperature(int n){return (n<0?0x80000000u:0)|bcd_unsigned(n<0?-n:n);}
int from_bcd(unsigned n){int q=0;for(int i=4;i>=0;--i)q=q*10+((n>>(4*i))&15);return n&0x80000000u?-q:q;}
bool finite_range(float x,float lo,float hi){return std::isfinite(x)&&x>=lo&&x<=hi;}
bool display_idle(){return (hdmi[1]&5u)==4u;}
void submit(){fence();hdmi[6]=1;fence();}
void issue(){io[1]=command_address;io[2]=command_data;io[3]=command_words;fence();io[0]=1|(command_read?2:0);fence();command_started=milliseconds();}
void begin(unsigned address,bool read,unsigned data,unsigned words){
 command_address=address;command_read=read;command_data=data;command_words=words;
 attempt=0;active=true;retry_wait=false;issue();
}
// Never spin on hardware: inference and HDMI continue while a transaction runs.
int finish(){
 const unsigned now=milliseconds();
 if(!active)return -1;
 if(retry_wait){if(!due(now,retry_at))return -1;retry_wait=false;issue();return -1;}
 if(io[0]&1u)return elapsed(now,command_started,1000)?4:-1;
 const unsigned result=io[4];
 if(result==2&&attempt<2){
  ++attempt;retry_wait=true;retry_at=now+2;
  log_line("MM_IR_RETRY reg=%04x attempt=%u status=%u",command_address,attempt,result);return -1;
 }
 active=false;return result==1?1:result?int(result):4;
}
void copy_words(uint16_t* target,unsigned n){for(unsigned i=0;i<n;++i)target[i]=uint16_t(buffer[i]);}
void fail(unsigned code,const char* reason="transport",int detail=0){
 const unsigned now=milliseconds();++error_streak;++recoveries;
 active=false;retry_wait=false;pages=0;rate.reset();history.invalidate_ir();thermal_detector.reset();thermal_activity=false;
 acquisition=AcqIdle;next_ready=false;next_error=0;next_rate_drop=false;
 // A corrupt sample/late ACK does not invalidate the checked EEPROM. Keep the
 // last displayed map until its real freshness deadline; never re-commit old
 // pixels as a new measurement or repeatedly reset the adaptive refresh rate.
 restart_calibration=!calibrated||code==6;
 if(!have_display||elapsed(now,last_display,kDisplayStaleMs))pending_error=code;
 if(!restart_calibration&&error_streak>=2&&refresh_code>3){
  --refresh_code;error_streak=0;
  log_line("MM_IR_RATE_FALLBACK subpage_hz=%u reason=invalid_samples camera_continues=1",1u<<(refresh_code-1));
 }
 const unsigned delay=restart_calibration?2000:50;
 state=Backoff;wake=now+delay;
 log_line("MM_IR_ERROR code=%u reason=%s detail=%d frames=%u recoveries=%u retry_after_ms=%u cached_calibration=%u display_held=%u stale_after_ms=%u camera_continues=1",
  code,reason,detail,frames,recoveries,delay,!restart_calibration,
  have_display&&!elapsed(now,last_display,kDisplayStaleMs),kDisplayStaleMs);
}
void status_if_idle(){
 if(display_idle()){
  record[0]=pending_error;record[5]=frames;record[6]=pages;submit();pending_error=0;
 }
}
void report_sht(){
 const unsigned now=milliseconds();if(!elapsed(now,last_sht_log,500))return;last_sht_log=now;
 unsigned seq,status,t,h,stamp,again;
 // Bounded snapshot retry: a missing peripheral must never freeze camera inference.
 for(unsigned i=0;i<3;++i){
  seq=sht[5];status=sht[0];t=sht[2];h=sht[4];stamp=sht[3];again=sht[5];
  if(seq==again){
   if(seq!=last_sht||!seq){
    last_sht=seq;
    if(seq&&status==1)history.push_env(stamp,seq,from_bcd(t),from_bcd(h));
    else history.invalidate_env();
    log_line("MM_SHT seq=%u status=%u temp_centi=%d rh_centi=%d age_ms=%u",
     seq,status,from_bcd(t),from_bcd(h),io[5]-stamp);
   }return;
  }
 }
 log_line("MM_SHT snapshot_unstable=1");
}
// Hardware reads the next RAM snapshot while the CPU compensates and publishes
// the current one. No command may overwrite next_frame until it is consumed.
void acquire_next(){
 const unsigned now=milliseconds();
 switch(acquisition){
 case AcqIdle:return;
 case AcqPoll:
  if(next_ready||next_error||next_rate_drop)return;
  if(elapsed(now,last_fresh,3000)){next_error=5;acquisition=AcqIdle;return;}
  if(!elapsed(now,last_poll,2))return;
  last_poll=now;begin(0x8000,true,0,1);acquisition=AcqStatus;return;
 case AcqStatus:{
  const int rc=finish();if(rc<0)return;if(rc!=1){next_error=rc;acquisition=AcqIdle;return;}
  if(!(buffer[0]&8)){acquisition=AcqPoll;return;}
  next_sample_ms=io[7];next_page=buffer[0]&1u;
  begin(0x8000,false,0x0030,1);acquisition=AcqClear;return;
 }
 case AcqClear:{
  const int rc=finish();if(rc<0)return;if(rc!=1){next_error=rc;acquisition=AcqIdle;return;}
  begin(0x0400,true,0,832);next_read_start=now;acquisition=AcqRead;return;
 }
 case AcqRead:{
  const int rc=finish();if(rc<0)return;if(rc!=1){next_error=rc;acquisition=AcqIdle;return;}
  copy_words(next_frame,832);next_read_ms=now-next_read_start;
  begin(0x8000,true,0,1);acquisition=AcqCheck;return;
 }
 case AcqCheck:{
  const int rc=finish();if(rc<0)return;if(rc!=1){next_error=rc;acquisition=AcqIdle;return;}
  if(buffer[0]&8){
   ++overruns;++overrun_streak;acquisition=AcqPoll;
   if(overrun_streak>=3&&refresh_code>3){next_rate_drop=true;acquisition=AcqIdle;}
   return;
  }
  next_frame[832]=control;next_frame[833]=next_page;next_ready=true;acquisition=AcqIdle;return;
 }
 }
}
bool prepare_current(unsigned now){
 if(int16_t(frame[778])==0||frame[778]==0x7fff){fail(7,"gain_raw",int16_t(frame[778]));return false;}
 if(!compute.prepare(frame,params,0.95f,-8.0f)){
  log_line("MM_IR_SAMPLE supply_mv=%d ambient_centi=%d gain_raw=%d page=%u control=%04x",
   std::isfinite(compute.supply)?int(compute.supply*1000):0,
   std::isfinite(compute.ambient)?int(compute.ambient*100):0,int16_t(frame[778]),frame[833],control);
  fail(7,"compensation_input");return false;
 }
 ta=compute.ambient;overrun_streak=0;pixel=0;calc_start=now;last_fresh=now;
 state=Calculate;acquisition=AcqPoll;next_ready=false;return true;
}
void step(){
 const unsigned now=milliseconds();report_sht();
 if(have_display&&elapsed(now,last_display,kDisplayStaleMs)){
  have_display=false;pending_error=5;
  log_line("MM_IR_STALE age_ms=%u display_invalid=1",now-last_display);
 }
 // Never send an error-status swap while waiting for a real image ACK: that
 // second swap would look like the image ACK and incorrectly renew freshness.
 if(pending_error&&state!=Acknowledge)status_if_idle();
 if(state==Calculate||state==Publish||state==Acknowledge||state==NextFrame)acquire_next();
 switch(state){
 case Boot:
  if(!due(now,wake)||(io[0]&1))return;
  display.reset();rate.reset();history.invalidate_ir();thermal_detector.reset();pages=0;overrun_streak=0;calibrated=false;
  begin(0x2400,true,0,832);state=EeFirst;return;
 case EeFirst:{
  const int rc=finish();if(rc<0)return;if(rc!=1){fail(rc);return;}
  copy_words(ee,832);begin(0x2400,true,0,832);state=EeSecond;return;
 }
 case EeSecond:{
  const int rc=finish();if(rc<0)return;if(rc!=1){fail(rc);return;}
  copy_words(frame,832);for(unsigned i=0;i<832;++i)if(frame[i]!=ee[i]){fail(6);return;}
  state=Extract;return;
 }
 case Extract:
  if(!(ee[51]&0xff00)||!(ee[50]&0x03ff)||!ee[48]||MLX90640_ExtractParameters(ee,&params)!=0||
     !params.kVdd||!params.KtPTAT||!params.gainEE){fail(6);return;}
  memset(bad,0,sizeof(bad));
  for(unsigned j=0;j<5;++j){if(params.brokenPixels[j]<768)bad[params.brokenPixels[j]]=1;if(params.outlierPixels[j]<768)bad[params.outlierPixels[j]]=1;}
  for(unsigned i=0;i<768;++i)if(!bad[i]&&(!std::isfinite(params.alpha[i])||params.alpha[i]<=0)){fail(6);return;}
  compute.calibrate(params);calibrated=true;memset(temperatures,0,sizeof(temperatures));
  begin(0x800d,true,0,1);state=ControlRead;return;
 case ControlRead:{
  const int rc=finish();if(rc<0)return;if(rc!=1){fail(rc);return;}
  // Preserve resolution/mode; start at 16 subpages/s (8 complete pairs/s).
  control=(uint16_t(buffer[0])&0xfc70)|(refresh_code<<7)|1;
  begin(0x800d,false,control,1);state=ControlWrite;return;
 }
 case ControlWrite:{
  const int rc=finish();if(rc<0)return;if(rc!=1){fail(rc);return;}
  begin(0x800d,true,0,1);state=ControlCheck;return;
 }
 case ControlCheck:{
  const int rc=finish();if(rc<0)return;if(rc!=1){fail(rc);return;}
  if(uint16_t(buffer[0])!=control){fail(6);return;}
  frame[832]=control;state=Poll;last_fresh=now;last_poll=now-10;
  log_line("MM_IR_INIT algorithm=thermal_fast_v1 eeprom_double_read=OK calibration=OK control=%04x subpage_hz=%u complete_pair_hz_max=%u i2c_hz=396825 emissivity_milli=950 interpolation=bilinear",
   control,1u<<(refresh_code-1),1u<<(refresh_code-2));return;
 }
 case Poll:
  if(elapsed(now,last_fresh,3000)){fail(5);return;}
  if(!elapsed(now,last_poll,2))return;last_poll=now;begin(0x8000,true,0,1);state=Status;return;
 case Status:{
  const int rc=finish();if(rc<0)return;if(rc!=1){fail(rc);return;}
  if(!(buffer[0]&8)){state=Poll;return;}
  // Sensor data-ready observed by the same APB clock as the video SOF stamp.
  // Polling/transport latency remains a measurement uncertainty, not zero skew.
  sample_ms=io[7];
  captured_page=buffer[0]&1u; // Vendor contract: page from the ready status BEFORE clearing it.
  begin(0x8000,false,0x0030,1);state=Clear;return;
 }
 case Clear:{
  const int rc=finish();if(rc<0)return;if(rc!=1){fail(rc);return;}
  begin(0x0400,true,0,832);read_ms=now;state=ReadFrame;return;
 }
 case ReadFrame:{
  const int rc=finish();if(rc<0)return;if(rc!=1){fail(rc);return;}
  copy_words(frame,832);read_ms=now-read_ms;begin(0x8000,true,0,1);state=CheckFrame;return;
 }
 case CheckFrame:{
  const int rc=finish();if(rc<0)return;if(rc!=1){fail(rc);return;}
  const unsigned s=buffer[0];if(s&8){
   ++overruns;++overrun_streak;state=Poll;
   if(overrun_streak>=3&&refresh_code>3){
    --refresh_code;overrun_streak=0;pages=0;rate.reset();history.invalidate_ir();
    control=(control&0xfc7f)|(refresh_code<<7);begin(0x800d,false,control,1);state=ControlWrite;
    log_line("MM_IR_RATE_FALLBACK subpage_hz=%u discarded=%u camera_continues=1",1u<<(refresh_code-1),overruns);
   }return;
  }
  // Only bit 3 is the RAM-overrun check. Do not reject unrelated status bits,
  // or label RAM using a later status sample after the next conversion starts.
  frame[833]=captured_page;prepare_current(now);return;
 }
 case Calculate:{
  const unsigned page=frame[833];
  // One finite 384-pixel subpage per call. Splitting this across four neural
  // operators added their wall time to every map; no waiting/spinning here.
  compute.calculate(frame,params,temperatures,0,768);
  for(unsigned i=0;i<768;++i){
   unsigned pattern=(i/32)&1;if(control&0x1000)pattern^=i&1;
   if(pattern==page&&!bad[i]&&!finite_range(temperatures[i],-40,300)){
    log_line("MM_IR_PIXEL index=%u raw=%d temp_centi=%d page=%u",i,int16_t(frame[i]),
     std::isfinite(temperatures[i])?int(temperatures[i]*100):0,page);
    fail(7,"pixel_range",i);return;
   }
  }
  pixel=768;
  if(elapsed(now,page_time[1-page],2000))pages&=1u<<page;
  pages|=1u<<page;page_time[page]=now;++frames;
  if(pages!=3){state=NextFrame;return;}
  for(unsigned i=0;i<768;++i)if(bad[i]){
   const int neighbours[4]={i%32?int(i)-1:-1,i%32<31?int(i)+1:-1,i>=32?int(i)-32:-1,i<736?int(i)+32:-1};
   float sum=0;unsigned n=0;for(int j:neighbours)if(j>=0&&!bad[j]){sum+=temperatures[j];++n;}
   if(!n){fail(7,"bad_pixel_neighbours",i);return;}temperatures[i]=sum/n;
  }
  for(unsigned i=0;i<768;++i){
   const float t=temperatures[i];if(!finite_range(t,-40,300)){fail(7,"complete_map_range",i);return;}
   centi[i]=int16_t(t*100.0f+(t<0?-0.5f:0.5f));
  }
  const bool previous_activity=thermal_activity;
  thermal_last_valid=milliseconds();
  thermal_activity=thermal_detector.update(sample_ms,frames,page,control&0x1000,centi,bad);
  ++thermal_activity_seq;
  if(thermal_activity&&!previous_activity)
   log_line("MM_IR_WAKE possible_person=1 area=%u background_centi=%d contrast_centi=%d duration_ms=%u samples=%u empty_reference=%u new_heat_centi=%d palette_independent=1 confirm_with_yolo=1",
    thermal_detector.area,thermal_detector.background_centi,thermal_detector.contrast_centi,thermal_detector.duration_ms,thermal_detector.samples,
    thermal_detector.use_background,ThermalWake::kNewHeatCenti);
  history.push_ir(sample_ms,frames,page,control&0x1000,centi);
  display.update(centi,page,control&0x1000,bad);state=Publish;started=now;return;
 }
 case Publish:
  if(!display_idle()){if(elapsed(now,started,100))fail(9);return;}
  for(unsigned i=0;i<768;++i)image[i]=display.color(i);
  record[0]=1|(bcd_unsigned(rate.updates_tenths>999?999:rate.updates_tenths)<<8);
  record[1]=bcd_temperature(display.minimum);record[2]=bcd_temperature(display.maximum);
  record[3]=bcd_temperature(display.filtered[12*32+16]);record[4]=bcd_temperature(int(ta*100));
  record[5]=frames;record[6]=pages;record[7]=bcd_temperature(display.low);record[8]=bcd_temperature(display.high);
  record[9]=display.hotspot;record[10]=1;record[11]=bcd_unsigned(read_ms);
  record[12]=bcd_unsigned(now-calc_start);record[13]=bcd_unsigned(published?now-last_publish:0);
  last_publish=now;++published;submit();started=now;state=Acknowledge;return;
 case Acknowledge:
  if(!display_idle()){if(elapsed(now,started,100))fail(9);return;}
  last_display=now;have_display=true;pending_error=0;error_streak=0;
  rate.acknowledge(now,frame[833]);
  if(elapsed(now,last_ir_log,500)){
   last_ir_log=now;
   log_line("MM_IR seq=%u page=%u min_centi=%d max_centi=%d center_centi=%d read_ms=%u calc_wall_ms=%u update_hz_x10=%u pair_hz_x10=%u overruns=%u page0_age_ms=%u page1_age_ms=%u display_seq=%u ack=%x",
    frames,frame[833],display.minimum,display.maximum,display.filtered[12*32+16],read_ms,last_publish-calc_start,
    rate.updates_tenths,rate.pairs_tenths,overruns,now-page_time[0],now-page_time[1],hdmi[4],hdmi[1]);
  }
  state=NextFrame;return;
 case NextFrame:
  if(next_error){const unsigned rc=next_error;fail(rc,"prefetch_transport");return;}
  if(next_rate_drop){
   --refresh_code;overrun_streak=0;next_rate_drop=false;pages=0;rate.reset();history.invalidate_ir();
   control=(control&0xfc7f)|(refresh_code<<7);begin(0x800d,false,control,1);state=ControlWrite;
   log_line("MM_IR_RATE_FALLBACK subpage_hz=%u discarded=%u pipeline=1 camera_continues=1",1u<<(refresh_code-1),overruns);return;
  }
  if(!next_ready)return;
  memcpy(frame,next_frame,sizeof(frame));sample_ms=next_sample_ms;read_ms=next_read_ms;
  prepare_current(now);return;
 case Backoff:
  if(due(now,wake)&&!(io[0]&1u)){
   if(restart_calibration){state=Boot;wake=now;}
   else {begin(0x800d,true,0,1);state=ControlRead;}
  }return;
 }
}
}
void initialize(){
 enabled=hdmi[0]==0x46555331u&&hdmi[0x58/4]==0x59415539u;
 state=Boot;wake=milliseconds()+100;pending_error=8;history.reset();
 calibrated=false;restart_calibration=true;have_display=false;refresh_code=5;error_streak=0;recoveries=0;
 acquisition=AcqIdle;next_ready=false;next_error=0;next_rate_drop=false;
 log_line("MM_START build=yolo_auto_v17_dual_voice_uart sensors=SHT30,MLX90640 thermal=thermal_fast_v1 recovery=ir_stable_v2 pipeline=1 pins=unchanged enabled=%u",enabled);
}
void service(){
 if(!enabled||inside)return;inside=true;
 // Drain cheap state transitions, but at most one temperature batch per call.
 for(unsigned i=0;i<6;++i){const State before=state;step();if(state==before||before==Calculate)break;}
 inside=false;
}
void write_metrics(unsigned fps_tenths,unsigned inference_ms,unsigned score_q15){
 if(!enabled||((hdmi[0x70/4]&5u)!=4u))return;
 hdmi[0x80/4]=bcd_unsigned(fps_tenths>9999?9999:fps_tenths);
 hdmi[0x84/4]=bcd_unsigned(inference_ms>9999?9999:inference_ms);
 const unsigned percent=(score_q15*100u+16384u)/32768u;
 hdmi[0x88/4]=bcd_unsigned(percent>100?100:percent);fence();
}
const multimodal_alignment::Result& align_video(unsigned capture_ms,unsigned video_sequence){
 history.match(capture_ms,video_sequence,aligned);
 log_line("MM_ALIGN video_seq=%u video_ms=%u ir_valid=%u ir0_seq=%u ir0_ms=%u ir0_dt_ms=%d ir1_seq=%u ir1_ms=%u ir1_dt_ms=%d env_valid=%u env_seq=%u env_ms=%u env_dt_ms=%d temp_centi=%d rh_centi=%d ir_min_centi=%d ir_max_centi=%d ir_center_centi=%d policy=nearest ir_limit_ms=350 env_limit_ms=1500",
  video_sequence,capture_ms,aligned.infrared_valid,aligned.ir_sequence[0],aligned.ir_ms[0],aligned.ir_delta_ms[0],
  aligned.ir_sequence[1],aligned.ir_ms[1],aligned.ir_delta_ms[1],aligned.environment_valid,aligned.env_sequence,
  aligned.env_ms,aligned.env_delta_ms,aligned.env_temperature,aligned.env_humidity,aligned.minimum,aligned.maximum,aligned.center);
 return aligned;
}
// Web telemetry shows the latest measured temperature, independently of the
// stricter 350 ms video-fusion alignment. Both subpages must be <=1 s old.
void network_sample(unsigned now,multimodal_alignment::Result& out){history.match(now,0,out,1000);}
bool thermal_wake(unsigned& last_sequence){
 if(last_sequence==thermal_activity_seq)return false;last_sequence=thermal_activity_seq;
 return thermal_activity&&pages==3&&state!=Backoff;
}
void set_low_power_monitor(bool value){
 if(thermal_detector.enabled!=value){thermal_detector.set_enabled(value);thermal_activity=false;++thermal_activity_seq;}
}
void observe_visual_presence(unsigned capture_ms,bool present){thermal_detector.observe_visual(capture_ms,present);}
void reject_thermal_candidate(unsigned now){
 if(thermal_monitor_healthy(now)){
  thermal_detector.reject_candidate(sample_ms,frames,control&0x1000,centi,bad);
  thermal_activity=false;++thermal_activity_seq;
  log_line("MM_IR_REJECT visual_window_ms=5000 empty_reference_updated=1 stationary_retrigger=blocked");
 }
}
bool thermal_monitor_healthy(unsigned now){return enabled&&pages==3&&unsigned(now-thermal_last_valid)<3000;}
}
