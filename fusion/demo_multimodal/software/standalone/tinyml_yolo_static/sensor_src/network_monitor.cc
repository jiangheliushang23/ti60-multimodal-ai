#include "network_monitor.h"
#include "thermal_presence.h"
#include "network_packet.h"
#include "port.h"
#include "multimodal_sensors.h"
#include "board_http.h"
namespace network_monitor {
namespace {
volatile uint32_t* const io=reinterpret_cast<volatile uint32_t*>(0xf810a000u);
alignas(16) uint8_t packet[1536],status[128];
bool enabled=false,link=false,inside=false,stream_running=false;
unsigned next_status=0,packet_seq=0,status_seq=0,last_link=0,last_log=0,link_count=0,max_work_ms=0;
unsigned result_count=0,result_ms=0,env_ms=0,valid=0,infer_ms=0,fps=0,mode=0;
multimodal_alignment::Result network_sensors;
int env_temp=0,env_humidity=0,ir_min=0,ir_max=0,ir_center=0,env_delta=0,ir_delta=0;
struct Person {unsigned id=0,flags=0,score=0,events=0;int x1=0,y1=0,x2=0,y2=0;} people[2];
bool due(unsigned n,unsigned deadline){return int32_t(n-deadline)>=0;}
unsigned gray_decode(unsigned g){for(unsigned s=1;s<16;s<<=1)g^=g>>s;return g&65535;}
bool submit(const uint8_t* p,unsigned bytes){
 if(io[1]&1u)return false;
 unsigned n=network_packet::frame(packet,p,bytes,++packet_seq);
 for(unsigned i=0;i<(n+3)/4;++i){const auto* b=packet+i*4;io[512+i]=unsigned(b[0])|(unsigned(b[1])<<8)|(unsigned(b[2])<<16)|(unsigned(b[3])<<24);}
 asm volatile("fence iorw,iorw":::"memory");io[2]=n;
 return true;
}
void encode_status(unsigned now,const multimodal_alignment::Result* aligned=nullptr){
 if(!aligned)multimodal_sensors::network_sample(now,network_sensors);
 const auto& a=aligned?*aligned:network_sensors;
 env_ms=a.env_ms;valid=unsigned(a.environment_valid)|(unsigned(a.infrared_valid)<<1);
 env_temp=a.env_temperature;env_humidity=a.env_humidity;env_delta=a.env_delta_ms;
 ir_min=a.minimum;ir_max=a.maximum;ir_center=a.center;ir_delta=a.ir_delta_ms[0];
 memset(status,0,sizeof(status));memcpy(status,"BMON0001",8);
 using network_packet::be32;using network_packet::be16;
 be32(status+8,++status_seq);be32(status+12,now);be32(status+16,result_count);be32(status+20,result_ms);
 be32(status+24,env_ms);be32(status+28,valid);be32(status+32,env_temp);be32(status+36,env_humidity);
 be32(status+40,ir_min);be32(status+44,ir_max);be32(status+48,ir_center);
 be32(status+52,mode);be32(status+56,infer_ms);be32(status+60,fps);
 for(unsigned i=0;i<2;++i){const auto& a=people[i];auto* b=status+64+24*i;
  be32(b,a.id);be32(b+4,a.flags);be32(b+8,a.score);be16(b+12,a.x1);be16(b+14,a.y1);
  be16(b+16,a.x2);be16(b+18,a.y2);be32(b+20,a.events);}
 be32(status+112,env_delta);be32(status+116,ir_delta);be32(status+120,result_ms);
 be32(status+124,thermal_presence::summarize(a.temperature,a.infrared_valid));
 board_http::publish_status(status,sizeof(status));
}
}
void initialize(){
 enabled=io[0]==0x454e3031u&&io[3]==0x43533634u;
 if(enabled){io[3]=0;asm volatile("fence iorw,iorw":::"memory");}
 last_link=milliseconds();link_count=gray_decode(io[1]>>1);
 log_line("NET_READY enabled=%u protocol=TCAM6401 telemetry=BMON0001 source=192.168.0.2 target=192.168.0.3 udp=8080 preview=640x360 color=RGB565 target_hz=30 independent_camera=1 hardware_stream=1 mac=025449360002 transport=lan_broadcast_mac http=FPGA_RISCV:80,PC:8002 nonblocking=1",enabled);
 board_http::initialize();
}
void service(unsigned power_mode){
 if(!enabled||inside)return;inside=true;const unsigned start=milliseconds();if(power_mode!=~0u)mode=power_mode;
 if(mode==2){for(auto& p:people){p.id=0;p.flags=0;p.score=0;}infer_ms=0;fps=0;}
 if(start-last_link>=200){
  const unsigned count=gray_decode(io[1]>>1),dt=start-last_link;
  const unsigned ticks=(count-link_count)&65535;
  // 125MHz /4096 => 30.5 ticks/ms. No modular-frequency ambiguity: the
  // counter wraps after 2.14 s and the accepted sampling interval is <=1 s.
  link=dt<=1000&&ticks>dt*28u&&ticks<dt*33u;
  last_link=start;link_count=count;
 }
 if(stream_running!=link){io[3]=unsigned(link);asm volatile("fence iorw,iorw":::"memory");stream_running=link;}
 if(link&&!(io[1]&1u)){
  if(due(start,next_status)){encode_status(start);if(submit(status,sizeof(status)))next_status=start+500;}
 }
 if(start-last_log>=10000){
  log_line("NET_STATUS gigabit_clock=%u mode=%u hardware_stream=1 tx_busy=%u service_max_ms=%u color=RGB565 size=640x360 target_hz=30",link,mode,io[1]&1u,max_work_ms);
  last_log=start;max_work_ms=0;
 }
 board_http::service(link,mode);
 unsigned work=milliseconds()-start;if(work>max_work_ms)max_work_ms=work;
 inside=false;
}
// Compatibility hooks intentionally do not sample the model tensor or low-power
// grayscale monitor: all network pictures now come from the post-gamma hardware camera tap.
void preview_tick(){} // Native hardware stream needs no CPU/timer servicing.
unsigned sent_images(){return 0;}
void camera_input(const int8_t*,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned){}
void low_camera(const uint8_t*,unsigned,unsigned,unsigned,unsigned){}
void observe(const two_person_analysis::Result& r,const multimodal_alignment::Result& a,
 unsigned count,unsigned capture,unsigned inference,unsigned fps_tenths){
 result_count=count;result_ms=capture;env_ms=a.env_ms;valid=unsigned(a.environment_valid)|(unsigned(a.infrared_valid)<<1);
 env_temp=a.env_temperature;env_humidity=a.env_humidity;env_delta=a.env_delta_ms;
 ir_min=a.minimum;ir_max=a.maximum;ir_center=a.center;ir_delta=a.ir_delta_ms[0];infer_ms=inference;fps=fps_tenths;
 for(unsigned i=0;i<2;++i){const auto& d=r.detections[i];auto& p=people[i];
  p.id=r.ids[i];p.flags=unsigned(d.valid)|(unsigned(r.alarm[i])<<1)|(unsigned(r.pixels[i])<<3);
  p.score=d.score;p.events=r.falls[i].events;p.x1=d.box.x1;p.y1=d.box.y1;p.x2=d.box.x2;p.y2=d.box.y2;
 }

}
}
