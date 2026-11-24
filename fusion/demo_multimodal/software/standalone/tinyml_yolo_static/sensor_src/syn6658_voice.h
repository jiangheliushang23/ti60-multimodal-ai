#pragma once
namespace syn6658_voice {
struct FallEvent {unsigned track_id,event_id;bool alarm,event,recovered,displayed;};
void initialize();
void service();
void observe(bool alarm,bool event,unsigned event_id);
void observe_pair(const FallEvent (&events)[2]);
void request_test();
void request_unauthorized();
}
