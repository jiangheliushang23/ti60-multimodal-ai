// In-memory Ethernet transport only. Server callbacks and lwIP are production code.
#include "../../demo_multimodal/software/standalone/tinyml_yolo_static/http_src/board_http.cc"
#include <cstdlib>
extern "C" {
#include "lwip/priv/tcp_priv.h"
}
unsigned fake_now=1000;
uint32_t milliseconds(){return fake_now;}
void log_line(const char*,...){}
namespace {
unsigned head=0,tail=0,incoming_length=0,send_budget=~0u,lengths[256];
uint8_t frames[256][1600],incoming[1600];
int test_send(const uint8_t* p,unsigned n){
 if(!send_budget||head-tail==256)return 0;if(send_budget!=~0u)--send_budget;
 memcpy(frames[head%256],p,n);lengths[head++%256]=n;return 1;
}
int test_receive(uint8_t* p,unsigned capacity,unsigned* n){
 if(!incoming_length)return 0;*n=incoming_length;incoming_length=0;
 if(*n>capacity)return -1;memcpy(p,incoming,*n);return 1;
}
}
#define API extern "C" __declspec(dllexport)
API int stack_init(){test_io[0]=0x454e3031u;test_io[4]=0x48545031u;board_http::initialize();board_http::service(true,0);return enabled;}
API int stack_input(const uint8_t* p,unsigned n){if(n>1600)return 0;memcpy(incoming,p,n);incoming_length=n;board_http::service(true,0);return 1;}
API unsigned stack_pop(uint8_t* p){if(tail==head)return 0;unsigned n=lengths[tail%256];memcpy(p,frames[tail++%256],n);return n;}
API void stack_tick(unsigned n){fake_now+=n;board_http::service(true,0);}
API void stack_send_budget(unsigned n){send_budget=n;}
API void stack_mode(unsigned n){board_http::service(true,n);}
API void stack_status(const uint8_t* data){board_http::publish_status(data,128);}
API void stack_frame(){uint16_t pixels[128*72];for(unsigned i=0;i<128*72;++i)pixels[i]=uint16_t(i);want_snapshot=true;last_snapshot=0;board_http::publish_rgb565(pixels,7,fake_now);}
API int stack_queue_valid(){
 for(tcp_pcb* pcb=tcp_active_pcbs;pcb;pcb=pcb->next){unsigned n=0,guard=0;
  for(tcp_seg* s=pcb->unsent;s;s=s->next){if(++guard>64)return 0;n+=pbuf_clen(s->p);}
  for(tcp_seg* s=pcb->unacked;s;s=s->next){if(++guard>64)return 0;n+=pbuf_clen(s->p);}
  if(n!=pcb->snd_queuelen)return 0;
 }return 1;
}
