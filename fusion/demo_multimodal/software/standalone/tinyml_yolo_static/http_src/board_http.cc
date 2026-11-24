// NO_SYS lwIP raw TCP server on the RISC-V. No socket, PC proxy, or ISR owner.
#include "board_http.h"
#include "port.h"
#include "../sensor_src/network_packet.h"
#include <cstdio>
#include <cstring>
#include <cstdarg>
#include <cstdlib>
extern "C" {
#include "lwip/init.h"
#include "lwip/tcp.h"
#include "lwip/timeouts.h"
#include "netif/ethernet.h"
#include "web_netif.h"
}
namespace {
#ifdef BOARD_HTTP_TEST
uint32_t test_io[1024];
volatile uint32_t* const io=test_io;
int test_send(const uint8_t*,unsigned);
int test_receive(uint8_t*,unsigned,unsigned*);
#else
volatile uint32_t* const io=reinterpret_cast<volatile uint32_t*>(0xf810a000u);
#endif
constexpr unsigned W=128,H=72,BmpBytes=54+W*H*3,Connections=4,Capacity=32768;
struct Connection {
 tcp_pcb* pcb=nullptr;unsigned received=0,length=0,queued=0,last=0;bool prepared=false;
 char request[1024];uint8_t response[Capacity];
} connections[Connections];
struct Event {unsigned serial,ms,id,score,fall;int x1,y1,x2,y2;} events[24];
struct Seen {unsigned id=0,count=0;bool alarm=false;} seen[8];
unsigned event_count=0,event_next=0,seen_next=0,requests=0,power=0;
unsigned snapshot_seq=0,snapshot_ms=0,last_snapshot=0;
bool enabled=false,linked=false,inside=false,want_snapshot=true,have_snapshot=false;
alignas(4) uint8_t rawtx[1536],bmon[128],bmp[BmpBytes];
netif iface;wm_netif driver;
uint32_t random_state=0xc0645321u;
unsigned be16(const uint8_t* b){return (unsigned(b[0])<<8)|b[1];}
unsigned be32(const uint8_t* b){return (unsigned(b[0])<<24)|(unsigned(b[1])<<16)|(unsigned(b[2])<<8)|b[3];}
void le16(uint8_t* p,unsigned v){p[0]=v;p[1]=v>>8;}
void le32(uint8_t* p,unsigned v){for(unsigned i=0;i<4;++i)p[i]=v>>(i*8);}
void fence(){
#ifndef BOARD_HTTP_TEST
 asm volatile("fence iorw,iorw":::"memory");
#endif
}
int receive_copy(void*,uint8_t* dst,unsigned capacity,unsigned* length){
#ifdef BOARD_HTTP_TEST
 return test_receive(dst,capacity,length);
#else
 if(!(io[5]&1u))return 0;
 unsigned n=io[6];
 if(n<14||n>capacity){io[7]=1;fence();return -1;}
 for(unsigned i=0;i<(n+3)/4;++i){unsigned v=io[128+i];
  for(unsigned j=0;j<4&&i*4+j<n;++j)dst[i*4+j]=v>>(8*j);}
 fence();io[7]=1;fence();*length=n;return 1;
#endif
}
int send_copy(void*,const uint8_t* src,unsigned n){
#ifdef BOARD_HTTP_TEST
 return test_send(src,n);
#else
 if(!linked||n<14||n>1514)return -1;
 // At 1 Gb/s a complete frame takes <13 us. Bounded wait prevents TCP's
 // temporary packet-RAM backpressure from waiting for a 250 ms retransmit.
 const unsigned start=milliseconds();unsigned spins=0;
 while(io[1]&1u)if(++spins==10000||milliseconds()-start>=1)return 0;
 memcpy(rawtx,src,n);if(n<60){memset(rawtx+n,0,60-n);n=60;}
 const uint32_t crc=network_packet::crc32(rawtx,n);le32(rawtx+n,crc);n+=4;
 for(unsigned i=0;i<(n+3)/4;++i){const uint8_t* p=rawtx+i*4;
  io[512+i]=unsigned(p[0])|(unsigned(p[1])<<8)|(unsigned(p[2])<<16)|(unsigned(p[3])<<24);}
 fence();io[2]=n;return 1;
#endif
}
int link_up(void*){return linked;}
const wm_mac_ops ops={receive_copy,send_copy,link_up};
struct Writer {
 char* data;unsigned used,capacity;bool good;
 void add(const char* fmt,...){
  if(!good)return;va_list args;va_start(args,fmt);
  int n=vsnprintf(data+used,capacity-used,fmt,args);va_end(args);
  if(n<0||unsigned(n)>=capacity-used){good=false;return;}used+=unsigned(n);
 }
};
void headers(Connection& c,unsigned code,const char* type,unsigned length){
 int n=snprintf(reinterpret_cast<char*>(c.response),256,
  "HTTP/1.1 %u %s\r\nServer: Ti60-RISC-V/lwIP\r\nContent-Type: %s\r\nContent-Length: %u\r\nCache-Control: no-store\r\nConnection: close\r\nX-Content-Type-Options: nosniff\r\n\r\n",
  code,code==200?"OK":code==404?"Not Found":code==503?"Service Unavailable":code==405?"Method Not Allowed":"Bad Request",type,length);
 c.length=unsigned(n);c.prepared=true;++requests;
}
const char page[]=R"HTML(<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ti60 板端监控</title>
<style>body{background:#101b2b;color:#edf4ff;font:16px system-ui;margin:0}main{max-width:1100px;margin:auto;padding:24px}h1{font-size:25px}.card{background:#1b2c43;border:1px solid #34506c;border-radius:16px;padding:20px;margin:18px 0}.video{position:relative;max-width:768px;margin:16px auto;aspect-ratio:16/9;background:#07111d}img,canvas{position:absolute;width:100%;height:100%;inset:0}p{line-height:1.7}a{color:#87cfff}table{width:100%;text-align:left;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #34506c}.muted{color:#a4bbd6}button,input{font:inherit;padding:9px;border-radius:8px}#summary{white-space:pre-wrap}</style>
<main><h1>Ti60 · RISC-V 板端 HTTP 监控</h1><p class="muted">此页面、状态、图像和事件由 FPGA 内 RISC-V 的 lwIP TCP/HTTP 服务直接提供。无需启动电脑网页服务。</p>
<div class="card"><div id="health">正在连接开发板…</div><div class="video"><img id="camera" alt="正在等待摄像头快照"><canvas id="boxes" width="1280" height="720"></canvas></div><p class="muted">板端轻量彩色快照：128×72，最多约 1 次/秒。原有 640×360 高帧率网页、手机 App 和录像保持原入口。</p><div id="summary"></div></div>
<div class="card"><h2>本次上电事件</h2><p class="muted">最近 24 条跌倒 / 重新站起记录；时间为开发板上电毫秒。原有 PC 历史记录和录像继续保存。</p><table><thead><tr><th>时间(ms)</th><th>类型</th><th>ID</th><th>检测分数</th><th>位置</th></tr></thead><tbody id="events"></tbody></table></div>
<div class="card"><h2>原有完整监控</h2><p>电脑完整监控与安卓 App 继续使用电脑的 8002 端口。请填写运行监控服务的电脑地址。</p><input id="host" value="192.168.0.3" aria-label="电脑IP"><button id="open">打开完整监控</button></div>
<script>
let busy=false;const $=s=>document.getElementById(s);const ctx=$('boxes').getContext('2d');
function draw(s){ctx.clearRect(0,0,1280,720);for(const p of s.people){if(!p.visible)continue;ctx.strokeStyle=p.fall?'#ff334c':'#23e985';ctx.lineWidth=6;ctx.strokeRect(p.x1,p.y1,p.x2-p.x1,p.y2-p.y1);ctx.fillStyle=ctx.strokeStyle;ctx.font='30px sans-serif';ctx.fillText('ID '+p.id,p.x1,Math.max(32,p.y1-10));}}
async function update(){if(busy)return;busy=true;try{const s=await fetch('/api/status',{cache:'no-store'}).then(r=>r.json());$('health').textContent='开发板在线 · '+s.power+' · 上电 '+(s.uptime_ms/1000).toFixed(1)+' 秒';$('summary').textContent='环境温度：'+(s.environment_valid?(s.temperature_centi/100).toFixed(2)+' °C':'无有效数据')+'　湿度：'+(s.environment_valid?(s.humidity_centi/100).toFixed(2)+' %':'无有效数据')+'\n红外最高温度：'+(s.infrared_valid?(s.ir_max_centi/100).toFixed(2)+' °C':'无有效数据')+'　推理耗时：'+s.inference_ms+' ms';draw(s);const e=await fetch('/api/events').then(r=>r.json());$('events').replaceChildren(...e.events.slice().reverse().map(v=>{const tr=document.createElement('tr');for(const text of [v.uptime_ms,v.type==='fall'?'跌倒':'重新站起',v.id,(100*v.score_q15/32768).toFixed(1)+'%',`(${v.x1},${v.y1})–(${v.x2},${v.y2})`]){const td=document.createElement('td');td.textContent=text;tr.append(td);}return tr;}));}catch(e){$('health').textContent='开发板暂未响应，正在重试';}finally{busy=false;setTimeout(update,1000);}}
function image(){const im=$('camera');im.onload=im.onerror=()=>setTimeout(image,1000);im.src='/snapshot.bmp?t='+Date.now();}
$('open').onclick=()=>{const h=$('host').value.trim();if(/^[a-z0-9.-]+$/i.test(h))location.href='http://'+h+':8002/monitor.html';};update();image();</script></main></html>)HTML";
void status_body(Writer& w){
 const unsigned valid=be32(bmon+28),now=milliseconds();
 w.add("{\"host\":\"FPGA_RISCV\",\"build\":\"yolo_auto_v23_board_http\",\"uptime_ms\":%u,\"power\":\"%s\",\"environment_valid\":%s,\"infrared_valid\":%s,\"temperature_centi\":%d,\"humidity_centi\":%d,\"ir_min_centi\":%d,\"ir_max_centi\":%d,\"inference_ms\":%u,\"result_capture_ms\":%u,\"snapshot_sequence\":%u,\"snapshot_ms\":%u,\"http_requests\":%u,\"rx_frames\":%u,\"tx_frames\":%u,\"people\":[",
 now,power==2?"LOW":power==4?"VERIFY":power==3?"RECOVERING":power==1?"ENTERING":"NORMAL",valid&1?"true":"false",valid&2?"true":"false",int(be32(bmon+32)),int(be32(bmon+36)),int(be32(bmon+40)),int(be32(bmon+44)),be32(bmon+56),be32(bmon+20),snapshot_seq,snapshot_ms,requests,driver.rx_frames,driver.tx_frames);
 for(unsigned i=0;i<2;++i){const uint8_t* p=bmon+64+24*i;unsigned flags=be32(p+4);
  const bool fresh=now-be32(bmon+20)<=1000&&power!=2;
  w.add("%s{\"id\":%u,\"visible\":%s,\"fall\":%s,\"pixels\":%s,\"score_q15\":%u,\"fall_count\":%u,\"x1\":%u,\"y1\":%u,\"x2\":%u,\"y2\":%u}",i?",":"",be32(p),(fresh&&(flags&1))?"true":"false",flags&2?"true":"false",flags&8?"true":"false",be32(p+8),be32(p+20),be16(p+12),be16(p+14),be16(p+16),be16(p+18));}
 w.add("]}");
}
void events_body(Writer& w){
 w.add("{\"host\":\"FPGA_RISCV\",\"retention\":\"volatile_latest_24\",\"events\":[");
 unsigned n=event_count<24?event_count:24;
 for(unsigned i=0;i<n;++i){const Event& e=events[(event_next+24-n+i)%24];
  w.add("%s{\"serial\":%u,\"uptime_ms\":%u,\"type\":\"%s\",\"id\":%u,\"score_q15\":%u,\"x1\":%d,\"y1\":%d,\"x2\":%d,\"y2\":%d}",i?",":"",e.serial,e.ms,e.fall?"fall":"standing_recovery",e.id,e.score,e.x1,e.y1,e.x2,e.y2);}
 w.add("]}");
}
void simple(Connection& c,unsigned code,const char* text){headers(c,code,"text/plain; charset=utf-8",strlen(text));memcpy(c.response+c.length,text,strlen(text));c.length+=strlen(text);}
void prepare(Connection& c){
 c.request[c.received]=0;char method[12],path[128],version[16];
 if(sscanf(c.request,"%11s %127s %15s",method,path,version)!=3||strncmp(version,"HTTP/1.",7)){simple(c,400,"Bad request\n");return;}
 if(strcmp(method,"GET")){simple(c,405,"GET only\n");return;}
 if(char* query=strchr(path,'?'))*query=0;
 if(!strcmp(path,"/")||!strcmp(path,"/index.html")){
  headers(c,200,"text/html; charset=utf-8",sizeof(page)-1);memcpy(c.response+c.length,page,sizeof(page)-1);c.length+=sizeof(page)-1;return;}
 if(!strcmp(path,"/snapshot.bmp")){
  want_snapshot=true;if(!have_snapshot){simple(c,503,"Waiting for camera\n");return;}
  headers(c,200,"image/bmp",BmpBytes);memcpy(c.response+c.length,bmp,BmpBytes);c.length+=BmpBytes;return;}
 // Body is built above reserved header space, then moved after exact headers.
 Writer w={reinterpret_cast<char*>(c.response+256),0,Capacity-256,true};
 if(!strcmp(path,"/api/health"))w.add("{\"host\":\"FPGA_RISCV\",\"stack\":\"lwIP raw TCP\",\"port\":80,\"uptime_ms\":%u,\"pc_service_required\":false}",milliseconds());
 else if(!strcmp(path,"/api/status"))status_body(w);
 else if(!strcmp(path,"/api/events"))events_body(w);
 else{simple(c,404,"Not found\n");return;}
 if(!w.good){simple(c,503,"Response capacity\n");return;}
 headers(c,200,"application/json; charset=utf-8",w.used);memmove(c.response+c.length,c.response+256,w.used);c.length+=w.used;
}
void detach(Connection& c){tcp_arg(c.pcb,nullptr);tcp_recv(c.pcb,nullptr);tcp_sent(c.pcb,nullptr);tcp_err(c.pcb,nullptr);tcp_poll(c.pcb,nullptr,0);}
err_t abort_connection(Connection& c){tcp_pcb* pcb=c.pcb;detach(c);c.pcb=nullptr;tcp_abort(pcb);return ERR_ABRT;}
err_t on_receive(void*,tcp_pcb*,pbuf*,err_t);
err_t on_sent(void*,tcp_pcb*,u16_t);
err_t on_poll(void*,tcp_pcb*);
void on_error(void* arg,err_t){if(arg)static_cast<Connection*>(arg)->pcb=nullptr;}
void attach(Connection& c){tcp_arg(c.pcb,&c);tcp_recv(c.pcb,on_receive);tcp_sent(c.pcb,on_sent);tcp_err(c.pcb,on_error);tcp_poll(c.pcb,on_poll,2);}
err_t pump(Connection& c){
 if(!c.prepared)return ERR_OK;
 unsigned budget=2; // bounded TCP work per operator/main-loop poll
 while(budget--&&c.queued<c.length){unsigned n=tcp_sndbuf(c.pcb),left=c.length-c.queued;
  if(!n||tcp_sndqueuelen(c.pcb)>=TCP_SND_QUEUELEN-2)break;
  if(n>tcp_mss(c.pcb))n=tcp_mss(c.pcb);if(n>left)n=left;
  err_t e=tcp_write(c.pcb,c.response+c.queued,u16_t(n),TCP_WRITE_FLAG_COPY);
  if(e==ERR_MEM)break;if(e!=ERR_OK)return abort_connection(c);c.queued+=n;
 }
 err_t e=tcp_output(c.pcb);if(e!=ERR_OK&&e!=ERR_MEM)return abort_connection(c);
 if(c.queued==c.length&&tcp_sndbuf(c.pcb)==TCP_SND_BUF){
  tcp_pcb* pcb=c.pcb;detach(c);e=tcp_close(pcb);
  if(e==ERR_OK){c.pcb=nullptr;return ERR_OK;}
  attach(c);if(e!=ERR_MEM)return abort_connection(c);
 }
 return ERR_OK;
}
err_t on_sent(void* arg,tcp_pcb*,u16_t){Connection& c=*static_cast<Connection*>(arg);c.last=milliseconds();return pump(c);}
err_t on_poll(void* arg,tcp_pcb*){Connection& c=*static_cast<Connection*>(arg);if(milliseconds()-c.last>8000)return abort_connection(c);return pump(c);}
err_t on_receive(void* arg,tcp_pcb*,pbuf* p,err_t e){
 Connection& c=*static_cast<Connection*>(arg);
 if(e!=ERR_OK){if(p)pbuf_free(p);return abort_connection(c);}
 if(!p)return c.prepared?pump(c):abort_connection(c);
 tcp_recved(c.pcb,p->tot_len);c.last=milliseconds();
 if(c.prepared){pbuf_free(p);return ERR_OK;}
 if(p->tot_len>=sizeof(c.request)-c.received){pbuf_free(p);simple(c,400,"Request too large\n");return pump(c);}
 unsigned old=c.received;c.received+=pbuf_copy_partial(p,c.request+c.received,p->tot_len,0);pbuf_free(p);
 unsigned i=old>3?old-3:0;
 for(;i+3<c.received;++i)if(!memcmp(c.request+i,"\r\n\r\n",4)){prepare(c);return pump(c);}
 return ERR_OK;
}
err_t accept(void*,tcp_pcb* pcb,err_t e){
 if(e!=ERR_OK||!pcb)return ERR_ARG;
 for(auto& c:connections)if(!c.pcb){c.pcb=pcb;c.received=c.length=c.queued=0;c.prepared=false;c.last=milliseconds();attach(c);return ERR_OK;}
 tcp_abort(pcb);return ERR_ABRT;
}
}
extern "C" u32_t sys_now(){return milliseconds();}
extern "C" uint32_t wm_platform_random(){random_state^=milliseconds();random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
extern "C" void wm_platform_assert(const char* message){
 // A violated allocator invariant cannot safely return into lwIP. Ordinary
 // packet errors/backpressure are handled without assertions.
#ifdef BOARD_HTTP_TEST
 fprintf(stderr,"HTTP_FATAL reason=%s\n",message);fflush(stderr);abort();
#else
 log_line("HTTP_FATAL reason=%s",message);for(;;){}
#endif
}
// Optional private-lwIP trace hook; no packet logging on the real-time path.
extern "C" void wm_http_trace_ack(tcp_pcb*,void*,void*,unsigned,unsigned,u32_t){}
namespace board_http {
void initialize(){
 enabled=io[0]==0x454e3031u&&io[4]==0x48545031u;
 if(!enabled){log_line("HTTP_DISABLED reason=paired_HTP1_bit_required");return;}
 lwip_init();driver.ops=&ops;const uint8_t mac[6]={2,0x54,0x49,0x36,0,2};memcpy(driver.mac,mac,6);
 ip4_addr_t ip,mask,gateway;IP4_ADDR(&ip,192,168,0,2);IP4_ADDR(&mask,255,255,255,0);IP4_ADDR(&gateway,0,0,0,0);
 if(!netif_add(&iface,&ip,&mask,&gateway,&driver,wm_netif_init,ethernet_input)){enabled=false;log_line("HTTP_DISABLED reason=netif_add");return;}
 netif_set_default(&iface);netif_set_up(&iface);
 tcp_pcb* pcb=tcp_new();if(!pcb){enabled=false;log_line("HTTP_DISABLED reason=tcp_pool");return;}
 if(tcp_bind(pcb,IP_ADDR_ANY,80)!=ERR_OK){tcp_abort(pcb);enabled=false;log_line("HTTP_DISABLED reason=bind");return;}
 tcp_pcb* listener=tcp_listen_with_backlog(pcb,4);
 if(!listener){tcp_abort(pcb);enabled=false;log_line("HTTP_DISABLED reason=listen");return;}
 tcp_accept(listener,accept);
 log_line("HTTP_READY host=FPGA_RISCV stack=lwIP_raw_TCP url=http://192.168.0.2/ port=80 pc_service_required=0 snapshot=128x72_RGB events=24 original_udp=unchanged");
}
void service(bool link,unsigned power_mode){
 if(!enabled||inside)return;inside=true;linked=link;power=power_mode;
 wm_netif_poll(&iface,4);sys_check_timeouts();
 for(auto& c:connections)if(c.pcb){if(milliseconds()-c.last>8000)abort_connection(c);else pump(c);}
 inside=false;
}
void publish_status(const uint8_t* input,unsigned bytes){
 if(bytes!=sizeof(bmon)||memcmp(input,"BMON0001",8))return;memcpy(bmon,input,bytes);
 for(unsigned i=0;i<2;++i){const uint8_t* p=bmon+64+i*24;unsigned id=be32(p),flags=be32(p+4),count=be32(p+20);
  if(!id||!(flags&1))continue;Seen* s=nullptr;
  for(auto& x:seen)if(x.id==id)s=&x;
  if(!s){s=&seen[seen_next++%8];*s=Seen{};s->id=id;}
  bool alarm=flags&2,new_fall=alarm&&count>s->count,recovery=s->alarm&&!alarm;
  if(new_fall||recovery){Event& e=events[event_next++%24];
   e={++event_count,be32(bmon+20),id,be32(p+8),unsigned(new_fall),int(be16(p+12)),int(be16(p+14)),int(be16(p+16)),int(be16(p+18))};}
  s->alarm=alarm;if(count>s->count)s->count=count;
 }
}
bool snapshot_requested(){return enabled&&want_snapshot&&(!have_snapshot||milliseconds()-last_snapshot>=1000);}
void publish_rgb565(const uint16_t* pixels,unsigned sequence,unsigned capture_ms){
 if(!snapshot_requested())return;
 memset(bmp,0,54);bmp[0]='B';bmp[1]='M';le32(bmp+2,BmpBytes);le32(bmp+10,54);le32(bmp+14,40);le32(bmp+18,W);le32(bmp+22,H);le16(bmp+26,1);le16(bmp+28,24);le32(bmp+34,W*H*3);
 for(unsigned y=0;y<H;++y)for(unsigned x=0;x<W;++x){unsigned p=pixels[y*W+x];uint8_t* q=bmp+54+((H-1-y)*W+x)*3;
  q[0]=(p&31)*255/31;q[1]=((p>>5)&63)*255/63;q[2]=(p>>11)*255/31;}
 snapshot_seq=sequence;snapshot_ms=capture_ms;last_snapshot=milliseconds();have_snapshot=true;want_snapshot=false;
}
}
