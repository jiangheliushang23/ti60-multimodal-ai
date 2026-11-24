#include "syn6658_voice.h"
#include "voice_fall_queue.h"
#include "rv32_gpio_bus.h"
#include "port.h"

namespace syn6658_voice {
namespace {
bool enabled=false;
voice_uart::FallQueue queue;
voice_uart::Controller& controller=queue.controller;
voice_gpio::Rv32Bus bus;
voice_uart::Transport<voice_gpio::Rv32Bus> hardware(bus);
const char* kind_name(){return controller.kind==voice_uart::Fall?"REAL_FALL_RULE":controller.kind==voice_uart::Recovery?"RECOVERED_STANDING":controller.kind==voice_uart::Test?"TEST":controller.kind==voice_uart::Unauthorized?"UNAUTHORIZED":"NONE";}
}
void initialize(){
  enabled=voice_gpio::Rv32Bus::gpio()[0]==0x56475031u;
  if(enabled){hardware.initialize();queue.initialize(milliseconds());}
  log_line("VOICE_READY enabled=%u interface=UART9600 peripheral=VGP1 baud=9600 rdy_used=0 max_people=2 blocking_budget_us=65000 completion=UART_QUERY recovery=standing_green_once recovery_parts=2 acoustic_verified=0",enabled);
}
void service(){
  if(!enabled)return;
  unsigned previous=controller.reports;
  bus.at_safe_point=true;queue.service(milliseconds(),hardware);bus.at_safe_point=false;
  if(controller.reports!=previous)
    log_line("VOICE_STATE source=%s interface=UART9600 phase=%u error=%u event_id=%u person_id=%u person_event=%u waiting=%u requested=%u accepted=%u uart_completed=%u failed=%u dropped=%u gpio_commands=%u last_result=%u last_rx=%02x last_block_ticks=%llu block_timer_valid=%u rx_framing=%u max_rx_poll_gap_ticks=%u busy_seen=%u rdy_used=0 acoustic_verified=0",
      kind_name(),controller.phase,controller.error,controller.event_id,controller.kind==voice_uart::Test?0:queue.person_id,
      controller.kind==voice_uart::Test?0:queue.person_event,queue.waiting(),controller.requested,controller.accepted,
      controller.uart_completed,controller.failed,controller.dropped,hardware.commands(),controller.last_result,
      hardware.last_rx(),static_cast<unsigned long long>(hardware.last_duration_ticks()),hardware.duration_valid(),
      hardware.framing_errors(),hardware.max_poll_gap_ticks(),controller.busy_seen);
}
void observe(bool alarm,bool event,unsigned id){
  if(!enabled)return;
  if(!alarm){queue.clear(milliseconds());return;}
  const FallEvent events[2]={{1,id,alarm,event},{0,0,false,false}};
  observe_pair(events);
}
void observe_pair(const FallEvent (&events)[2]){
  if(!enabled)return;
  const unsigned added=queue.observe(milliseconds(),events);
  for(unsigned lane=0;lane<2;++lane){
    const auto& e=events[lane];
    if(added&(1u<<lane))log_line("VOICE_QUEUED source=REAL_FALL_RULE person_id=%u event_id=%u test=0 interface=UART9600 waiting=%u",e.track_id,e.event_id,queue.waiting());
    if(added&(1u<<(lane+2)))log_line("VOICE_QUEUED source=RECOVERED_STANDING person_id=%u event_id=%u displayed_green=1 test=0 interface=UART9600 waiting=%u",e.track_id,e.event_id,queue.waiting());
  }
}
void request_unauthorized(){
  bool queued=enabled&&queue.unauthorized(milliseconds());
  log_line("ASSIST_VOICE queued=%u phrase=UNAUTHORIZED priority=below_fall acoustic_verified=0",queued);
}
void request_test(){
  bool queued=enabled&&queue.test(milliseconds());
  log_line("VOICE_TEST requested=1 queued=%u source=TEST changes_fall_state=0 phrase=GBK_TEST interface=UART9600",queued);
}
}
