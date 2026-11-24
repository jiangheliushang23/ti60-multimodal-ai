// Real RV32/DSP inference. The host only transports images and draws board boxes.
#include <algorithm>
#include <cstring>
#include "fixture.h"
#include "port.h"
#include "compat_runtime.h"
#include "tiled_conv.h"
#include "person_roi.h"
#include "person_pair.h"
#include "two_person_analysis.h"
#include "tensorflow/lite/micro/micro_error_reporter.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_profiler.h"
#include "tensorflow/lite/schema/schema_generated.h"
#ifdef YOLO_CAMERA_LIVE
#include "camera_live_source.h"
#include "fall_detection.h"
#else
#include "camera_source.h"
#endif
#include "fast_memory_ops.h"
#ifdef YOLO_MULTIMODAL
#include "multimodal_sensors.h"
#include "camera_auto_service.h"
#include "scene_power.h"
#include "syn6658_voice.h"
#include "network_monitor.h"
#endif

uint32_t fnv(const uint8_t* p,unsigned n) {uint32_t h=2166136261u;while(n--)h=(h^*p++)*16777619u;return h;}
void compat_fatal(const char* reason) {log_line("YRAW_FATAL reason=%s node=%u",reason,current_node);for(;;){}}
namespace {
alignas(64) uint8_t arena[2*1024*1024];
alignas(64) uint8_t snapshot[kInputBytes];
uint32_t frame_id;
class Resolver:public tflite::MicroMutableOpResolver<13> {
  mutable TfLiteRegistration entries[6];
 public:
  using tflite::MicroMutableOpResolver<13>::FindOp;
  const TfLiteRegistration* FindOp(tflite::BuiltinOperator op)const override {
    const auto* r=tflite::MicroMutableOpResolver<13>::FindOp(op);
    int slot=op==tflite::BuiltinOperator_CONV_2D?0:op==tflite::BuiltinOperator_ADD?1:-1;
    if(r&&slot>=0) {entries[slot]=checked_registration(*r,op);return entries+slot;}
    slot=op==tflite::BuiltinOperator_PAD?3:op==tflite::BuiltinOperator_PADV2?4:op==tflite::BuiltinOperator_MAX_POOL_2D?5:-1;
    if(r&&slot>=0){entries[slot]=fast_memory_registration(*r,op);return entries+slot;}return r;
  }
};
class Profile:public tflite::MicroProfiler {
 public:
  static void operator delete(void*) {}
  ~Profile()override=default;
  unsigned node=0;uint32_t started;
  uint64_t BeginEvent(const char*)override {current_node=node++;started=milliseconds();return current_node;}
  void EndEvent(uint64_t n)override {
    node_ms[n]=milliseconds()-started;
#ifdef YOLO_MULTIMODAL
    // Poll autonomous I2C and process one bounded thermal subpage between nodes.
    // This runs after each operator completes, outside accelerator ownership.
    camera_auto_service::service();
    multimodal_sensors::service();
    syn6658_voice::service();
    network_monitor::service();
#endif
  }
};
using Box=person_roi::Box;
Box candidates[32],boxes[8];unsigned candidate_count,box_count;
void candidate(Box b) {
  if(b.x2<=b.x1||b.y2<=b.y1)return;
  unsigned where=candidate_count;
  if(where==32) {if(b.score<=candidates[31].score)return;where=31;}else ++candidate_count;
  while(where&&candidates[where-1].score<b.score) {candidates[where]=candidates[where-1];--where;}
  candidates[where]=b;
}
void decode(tflite::MicroInterpreter& interpreter) {
  candidate_count=box_count=0;
  for(unsigned h=0;h<3;++h) {
    const auto* q=interpreter.output(h)->data.int8;
    for(unsigned y=0;y<kHeadHeight[h];++y)for(unsigned x=0;x<kHeadWidth[h];++x)
      for(unsigned a=0;a<3;++a,q+=6) {
        const auto* lut=kSigmoid[h];
        const unsigned score=(unsigned(lut[q[4]+128])*lut[q[5]+128]+16384u)>>15;
        if(score<8192)continue; // .25; score threshold is explicit, no expected class.
        const int px=lut[q[0]+128],py=lut[q[1]+128],pw=lut[q[2]+128],ph=lut[q[3]+128];
        const int cx=(((px*512+16384)>>15)-128+int(x)*256)*kHeadStride[h];
        const int cy=(((py*512+16384)>>15)-128+int(y)*256)*kHeadStride[h];
        const int w=(int64_t(pw)*pw*4*kAnchorQ8[h][a*2]+(1ll<<29))>>30;
        const int height=(int64_t(ph)*ph*4*kAnchorQ8[h][a*2+1]+(1ll<<29))>>30;
        Box b={std::max(0,cx-w/2),std::max(0,cy-height/2),
               std::min(int(kInputWidth*256),cx+w/2),std::min(int(kInputHeight*256),cy+height/2),score};
        candidate(b);
      }
  }
  for(unsigned i=0;i<candidate_count&&box_count<8;++i) {
    const auto& a=candidates[i];bool suppress=false;
    for(unsigned j=0;j<box_count;++j) {
      const auto& b=boxes[j];
      const int w=std::max(0,std::min(a.x2,b.x2)-std::max(a.x1,b.x1));
      const int h=std::max(0,std::min(a.y2,b.y2)-std::max(a.y1,b.y1));
      const int64_t intersection=int64_t(w)*h;
      const int64_t sum=int64_t(a.x2-a.x1)*(a.y2-a.y1)+int64_t(b.x2-b.x1)*(b.y2-b.y1)-intersection;
      if(intersection*100>sum*45) {suppress=true;break;}
    }
    if(!suppress)boxes[box_count++]=a;
  }
}
bool read_bytes(uint8_t* p,unsigned n) {
  uint32_t last=milliseconds();
  while(n) {int c=read_command();if(c>=0) {*p++=c;--n;last=milliseconds();}
    else if(milliseconds()-last>3000)return false;}
  return true;
}
unsigned le32(const uint8_t* p) {return unsigned(p[0])|(unsigned(p[1])<<8)|(unsigned(p[2])<<16)|(unsigned(p[3])<<24);}
unsigned invoke(tflite::MicroInterpreter& interpreter,Profile& profile) {
  profile.node=0;const uint32_t t=milliseconds();
  if(interpreter.Invoke()!=kTfLiteOk||profile.node!=kNodeCount)compat_fatal("invoke");
  return milliseconds()-t;
}
uint32_t output_hash(tflite::MicroInterpreter& interpreter) {
  uint32_t h=2166136261u;
  for(unsigned j=0;j<3;++j) {
    const auto* p=reinterpret_cast<const uint8_t*>(interpreter.output(j)->data.int8);
    for(unsigned i=0;i<kHeadBytes[j];++i)h=(h^p[i])*16777619u;
  }return h;
}
}
extern "C" int main() {
  // Sapphire UART samples each bit eight times, UART clock is verified 100 MHz.
  auto* uart=reinterpret_cast<volatile uint32_t*>(0xf8010000u);
  while(((uart[1]>>16)&255)!=128) {} // drain constructor output before baud change
  uart[2]=24;uart[3]=7; // offsets 0x08 divider, 0x0c 8N1
  log_line("YRAW_BOOT variant=%s input=%ux%ux3 baud=500000",kVariant,kInputWidth,kInputHeight);
  if(fnv(yolo_model,kModelBytes)!=kModelHash||fnv(yolo_input,kInputBytes)!=kInputHash)compat_fatal("assets");
  hardware_initialize();conv_tile_weight_bytes=16384;
  static tflite::MicroErrorReporter reporter;static Resolver resolver;
  resolver.AddConv2D();resolver.AddPad();resolver.AddAdd();resolver.AddConcatenation();
  resolver.AddPadV2();resolver.AddMaxPool2D();resolver.AddResizeNearestNeighbor();
  static Profile profile;
  static tflite::MicroInterpreter interpreter(tflite::GetModel(yolo_model),resolver,arena,sizeof(arena),&reporter,&profile);
  if(interpreter.AllocateTensors()!=kTfLiteOk)compat_fatal("allocate");
  memcpy(interpreter.input(0)->data.int8,yolo_input,kInputBytes);
  phase=Phase::Qualify;invoke(interpreter,profile);
  if(output_hash(interpreter)!=kExpectedHash)compat_fatal("fixture_reference");
  unsigned accepted=0,software=0;for(bool q:qualified)accepted+=q;
  for(bool q:software_qualified)software+=q;
  phase=Phase::Hybrid;
  unsigned times[3];
  for(unsigned i=0;i<3;++i) {
    // The arena planner can reuse the consumed input tensor's bytes.
    memcpy(interpreter.input(0)->data.int8,yolo_input,kInputBytes);
    times[i]=invoke(interpreter,profile);if(output_hash(interpreter)!=kExpectedHash)compat_fatal("hybrid_reference");
  }
  std::sort(times,times+3);
  log_line("YRAW_QUALIFIED hw_nodes=%u software_lut_nodes=%u rejected=%u reference=EXACT",accepted,software,qualify_failures);
  log_line("YRAW_BENCH min_ms=%u median_ms=%u max_ms=%u",times[0],times[1],times[2]);
  for(unsigned i=0;i<kNodeCount;++i)log_line("YRAW_PROFILE node=%u op=%s ms=%u",i,kNodeMetadata[i].name,node_ms[i]);
  log_line("YRAW_READY bytes=%u output_bytes=%u variant=%s",kInputBytes,kOutputBytes,kVariant);
#ifdef YOLO_CAMERA_LIVE
  namespace cam=camera_live_source;
  const auto* tensor=interpreter.input(0);
  if(tensor->type!=kTfLiteInt8||tensor->bytes!=kInputBytes||tensor->params.zero_point!=-128||
     tensor->params.scale<0.003921567f||tensor->params.scale>0.003921571f)compat_fatal("camera_input_quantization");
  if(!cam::available())compat_fatal("camera_live_bit_identity");
#ifdef YOLO_MULTIMODAL
  camera_auto_service::initialize();
  multimodal_sensors::initialize();
  syn6658_voice::initialize();
  network_monitor::initialize();
  // Verify real accelerator output while the independent hardware camera stream runs.
  for(unsigned i=0;i<3;++i){
    memcpy(interpreter.input(0)->data.int8,yolo_input,kInputBytes);
    invoke(interpreter,profile);
    if(output_hash(interpreter)!=kExpectedHash)compat_fatal("network_concurrent_reference");
  }
  log_line("NET_CONCURRENT_SELFTEST passes=3 reference=EXACT source=hardware_camera");
  log_line("YCAM_READY build=yolo_auto_v24_transfer_opt source=MIPI_RGB565 size=1280x720 input=192x96x3 automatic=1 sensors=SHT30,MLX90640 detector=yolo_visual_v4 fall=geometry_sensitive_v3 max_box_age_ms=1000 max_people=2 search=full_scene per_id_fall=1 tracker=iou_motion_v1 prediction=disabled yellow_warning=disabled");
  unsigned previous_result=0;
#else
  log_line("YCAM_READY build=camera_live_v2 source=MIPI_RGB565 size=1280x720 input=192x96x3 automatic=1 max_box_age_ms=1000");
#endif
  bool paused=false;unsigned sequence=0,last_good=milliseconds(),last_wait=0;
  bool stale_cleared=false;const unsigned epoch=milliseconds();
  fall_detection::MotionGrid motion;
  person_roi::Planner person;
  static person_visual_track::Tracker visual;
  static two_person_analysis::Manager analysis;
  log_line("YTRACK_READY algorithm=iou_motion_v1 capacity=2 lost_ms=1200 history=32 predicted_boxes=0 fall_rules=unchanged hdmi=ids_colors trajectory=serial_viewer");
#ifdef YOLO_MULTIMODAL
  scene_power::Manager power;
  scene_power::Mode logged_power=scene_power::Normal;
  unsigned wake_thermal_sequence=0,last_power_log=0,last_monitor=0,power_frame_count=cam::lease[9];
  unsigned camera_fps_x10=0;bool camera_fps_valid=false;
  cam::hdmi[0x1090/4]=0;cam::hdmi[0x1094/4]=scene_power::Normal;
  log_line("POWER_READY empty_timeout_ms=%u verify_timeout_ms=%u normal_fps=30 low_fps=5 sleep_inference=0 wake=thermal_region led=LED0 pin=N14 active_high=1 osd=measured_camera_fps timebase=video_apb_ms",scene_power::Manager::kEmptyMs,scene_power::Manager::kVerifyMs);
  log_line("MM_ALIGN_READY clock=video_apb_ms video_stamp=ddr_sof ir_stamp=data_ready_observed env_stamp=sample_ready policy=nearest ir_limit_ms=350 env_limit_ms=1500");
#endif
  cam::Rectangle previous_box={0,0,0,0,false};
  log_line("YFALL_READY algorithm=geometry_sensitive_v3 arm_ms=%u confirm_ms=%u reference_ms=%u drop_window_ms=%u drop_evidence_ms=%u gap_ms=%u candidate_grace_ms=%u transition_ms=%u recover_ms=%u green_control=3 red_control=7 fixed_camera=1 single_person=0 per_id=1 alarm_hold=until_standing recovery_voice=green_once",
    fall_detection::Detector::kArmMs,fall_detection::Detector::kConfirmMs,fall_detection::Detector::kReferenceMs,
    fall_detection::Detector::kDropWindowMs,fall_detection::Detector::kDropEvidenceMs,fall_detection::Detector::kEvidenceGapMs,
    fall_detection::Detector::kCandidateGraceMs,fall_detection::Detector::kTransitionMs,fall_detection::Detector::kRecoverMs);
  for(;;){
#ifdef YOLO_MULTIMODAL
    camera_auto_service::service();
    multimodal_sensors::service();
    syn6658_voice::service();
    network_monitor::service(unsigned(power.mode));
    const unsigned power_now=milliseconds();
    power.camera_state(power_now,camera_auto_service::low_power(),camera_auto_service::rate_settled(),camera_auto_service::rate_failed());
    const bool was_verifying=power.mode==scene_power::Verifying;
    power.tick(power_now);
    if(was_verifying&&power.verification_rejected){
      multimodal_sensors::reject_thermal_candidate(power_now);
      log_line("POWER_CONFIRM present=0 next=LOW verify_ms=%u reason=window_expired",power_now-power.verify_started);
    }
    camera_auto_service::request_low_power(power.want_low());
    multimodal_sensors::set_low_power_monitor(power.mode==scene_power::Sleep);
    cam::hdmi[0x1090/4]=power.led()?1:0;
    cam::hdmi[0x1094/4]=scene_power::display_status(power.mode,camera_fps_x10,camera_fps_valid);
    if(power.mode!=logged_power){
      camera_fps_valid=false;power_frame_count=cam::lease[9];last_power_log=power_now;
      cam::hdmi[0x1094/4]=scene_power::display_status(power.mode,0,false);
      log_line("POWER_STATE state=%s at_ms=%u empty_ms=%u inference=%u led=%u leds=LED0 camera_low=%u",
       scene_power::name(power.mode),power_now,power.empty_ms(power_now),power.inference_allowed(),power.led(),camera_auto_service::low_power());
      if(power.mode==scene_power::Sleep){
       cam::overlay(++sequence,cam::rectangle(false,0,0,0,0));
       multimodal_sensors::write_metrics(0,0,0);
       analysis.reset();motion.reset();person.reset();visual.reset();previous_box.valid=false;
#ifdef YOLO_MULTIMODAL
       syn6658_voice::observe(false,false,0);
#endif
      }
      logged_power=power.mode;
    }
    if(power_now-last_power_log>=2000){
      const unsigned count=cam::lease[9];
      camera_fps_x10=(count-power_frame_count)*10000u/(power_now-last_power_log);
      camera_fps_valid=last_power_log!=0;
      log_line("POWER_STATUS state=%s empty_ms=%u inference=%u led=%u leds=LED0 camera_fps_x10=%u camera_fault=%u",
       scene_power::name(power.mode),power.empty_ms(power_now),power.inference_allowed(),power.led(),
       camera_fps_x10,camera_auto_service::rate_failed());
      power_frame_count=count;last_power_log=power_now;
    }
#endif
    const int command=read_command();
    // Keep result/ID trajectories at every update. Extra diagnostics are
    // sampled once a second; D enables full diagnostics, d restores fast mode.
    static bool verbose=false;
    static unsigned last_detail=0;
    if(command=='D'||command=='d'){verbose=command=='D';log_line("YCAM_DIAGNOSTICS verbose=%u interval_ms=%u",verbose,verbose?0:1000);}
    const unsigned detail_now=milliseconds();
    const bool details=verbose||command=='Q'||detail_now-last_detail>=1000;
#ifdef YOLO_MULTIMODAL
    if(command=='J')log_line("SMART_CAPS version=1 thermal=surface_region voice=U priority=fall_first");
    if(command=='U')syn6658_voice::request_unauthorized();
    if(command=='V')syn6658_voice::request_test(); // Test phrase; never injects a fall.
#endif
    if(command=='R'||command=='C'){
      paused=command=='R';cam::overlay(++sequence,cam::rectangle(false,0,0,0,0));
      analysis.reset();motion.reset();person.reset();visual.reset();previous_box.valid=false;
#ifdef YOLO_MULTIMODAL
       syn6658_voice::observe(false,false,0);
#endif
      log_line("YCAM_CONTROL paused=%u",paused);
    }
    if(command=='F'){
      analysis.reset();motion.reset();person.reset();visual.reset();previous_box.valid=false;
#ifdef YOLO_MULTIMODAL
       syn6658_voice::observe(false,false,0);
#endif
      cam::overlay(++sequence,cam::rectangle(false,0,0,0,0));
      log_line("YFALL_RESET manual=1");
    }
    if(command=='Q')log_line("YCAM_STATUS paused=%u setup=%08x source_count=%u shown_seq=%u",
        paused,cam::camera[1],cam::lease[9],cam::hdmi[0x107c/4]);
    if(paused)continue;
#ifdef YOLO_MULTIMODAL
    if(!power.inference_allowed()){
      if(power.mode==scene_power::Sleep&&multimodal_sensors::thermal_wake(wake_thermal_sequence)){
       power.wake(milliseconds());log_line("POWER_WAKE reason=thermal_region confirm_with_yolo=1");
      }
      if(power.mode==scene_power::Sleep&&power_now-power.last_change>=3000&&!multimodal_sensors::thermal_monitor_healthy(power_now)){
       power.wake(power_now);log_line("POWER_WAKE reason=thermal_unavailable fail_open=1");
      }
      if(power.mode==scene_power::Sleep&&milliseconds()-last_monitor>=50){
       last_monitor=milliseconds();cam::Frame monitor;
       if(cam::capture_monitor(&monitor)){
        network_monitor::low_camera(monitor.motion_gray,24,16,monitor.count,monitor.started_ms);
        last_good=milliseconds();
       }else if(milliseconds()-last_good>3000){
        power.wake(milliseconds());log_line("POWER_WAKE reason=camera_fault recover=1");
       }
      }
      continue;
    }
#endif
    cam::Frame frame;
    const bool debug_image=command=='P';
    const auto primary=person_roi::full();
    // Always search the full scene first, so a new second entrant cannot be
    // excluded by the first person's ROI. Retain a same-frame rescue view.
    const auto secondary=debug_image?primary:person.alternate(person.next(milliseconds()),milliseconds());
    if(!cam::capture_views(interpreter.input(0)->data.int8,cam::same_view(primary,secondary)?nullptr:reinterpret_cast<int8_t*>(snapshot),&frame,primary,secondary)){
      const unsigned now=milliseconds();
#ifdef YOLO_MULTIMODAL
      power.no_frame(now);
#endif
      if(now-last_good>1000&&!stale_cleared){
        cam::overlay(++sequence,cam::rectangle(false,0,0,0,0));stale_cleared=true;
        // No image can prove recovery. Preserve per-ID alarms across a camera
        // gap, clear only the stale overlay and acquisition diagnostics.
        motion.reset();person.reset();visual.reset();previous_box.valid=false;
#ifdef YOLO_MULTIMODAL
       syn6658_voice::observe(false,false,0);
#endif
        log_line("YFALL_HOLD camera_stale=1 alarm_state_preserved=1");
      }
      if(now-last_wait>2000){
        log_line("YCAM_WAIT setup=%08x lease=%08x source_count=%u published=%u write_errors=%u read_errors=%u underflows=%u",
            cam::camera[1],cam::lease[2],cam::lease[9],cam::camera[6],cam::camera[8],cam::camera[9],cam::camera[10]);
        last_wait=now;
      }
      continue;
    }
    if(debug_image){
      // Export a copied, full-scene model input at a safe loop boundary. The
      // DDR lease has already been released. Do not halt a running accelerator
      // to read image RAM: its completion timeout would no longer be valid.
      log_line("YCAM_IMAGE source_seq=%u source_count=%u bytes=%u width=%u height=%u input_hash=%08x format=rgb_int8",
         frame.sequence,frame.count,kInputBytes,kInputWidth,kInputHeight,fnv(snapshot,kInputBytes));
      uart_write_bytes(snapshot,kInputBytes);log_line("YCAM_IMAGE_END");
      continue;
    }
#ifdef YOLO_MULTIMODAL
    network_monitor::camera_input(interpreter.input(0)->data.int8,kInputWidth,kInputHeight,
      cam::kPadX,cam::kPadY,cam::kNewWidth,cam::kNewHeight,frame.count,frame.started_ms);
#endif
    person.acquired();
    unsigned input_hash=details?fnv(reinterpret_cast<const uint8_t*>(interpreter.input(0)->data.int8),kInputBytes):0;
    // Motion diagnostics retain a full-scene coordinate grid, independently of ROI.
    motion.capture_gray(frame.motion_gray);
    unsigned infer_ms=invoke(interpreter,profile),post_begin=milliseconds();decode(interpreter);
    unsigned post_ms=milliseconds()-post_begin,passes=1;
    person_pair::Detections frame_people;frame_people.add(primary,boxes,box_count);
    auto selected_view=primary;
    auto selected=person.select(primary,boxes,box_count,frame.started_ms);
    post_begin=milliseconds();
    auto supported=visual.update(frame.started_ms,frame.support_rgb565,selected);
    unsigned tracking_ms=milliseconds()-post_begin;post_ms+=tracking_ms;
    // A failed search gets one genuine model inference on the alternate view.
    // Both tensors came from the same immutable frame; no stale box is drawn.
    // Current-pixel evidence can continue a person with one inference. Search
    // an alternate direction every fourth update even when tracking succeeds.
    if(!selected.valid&&(secondary.zoom||secondary.turns)&&(!supported.detection.valid||sequence%4==0)){
      memcpy(interpreter.input(0)->data.int8,snapshot,kInputBytes);
      input_hash=details?fnv(snapshot,kInputBytes):0;
      infer_ms+=invoke(interpreter,profile);post_begin=milliseconds();decode(interpreter);
      post_ms+=milliseconds()-post_begin;passes=2;selected_view=secondary;
      selected=person.select(secondary,boxes,box_count,frame.started_ms);
      frame_people.add(secondary,boxes,box_count);
      if(selected.valid){
        const unsigned confirm_start=milliseconds();
        visual.confirm(frame.started_ms,frame.support_rgb565,selected);
        const unsigned confirm_ms=milliseconds()-confirm_start;tracking_ms+=confirm_ms;post_ms+=confirm_ms;
        supported.detection=selected;supported.fallback=false;
      }
    }
    selected=supported.detection;
    bool fresh=milliseconds()-frame.started_ms<=800;
    if(!fresh)selected.valid=false;
    person.commit(frame.started_ms,selected,supported.fallback?0:selected_view.turns);
    auto other=frame_people.second(selected,fresh);
    const unsigned association_begin=milliseconds();
    auto people=analysis.update(frame.started_ms,milliseconds(),selected,other,supported.fallback&&fresh,fresh,frame.support_rgb565);
    const unsigned association_ms=milliseconds()-association_begin;post_ms+=association_ms;
    selected=people.detections[0];other=people.detections[1];
    if(people.rescued[0])supported=people.supports[0];
    if(people.pixels[0])people.supports[0]=supported;
    fresh=fresh&&milliseconds()-frame.started_ms<=800;
    if(!fresh){selected.valid=false;other.valid=false;people.ids[0]=people.ids[1]=0;}
    const cam::Rectangle r={selected.box.x1,selected.box.y1,selected.box.x2,selected.box.y2,selected.valid};
    const cam::Rectangle r2={other.box.x1,other.box.y1,other.box.x2,other.box.y2,other.valid};
    const unsigned drawn_count=unsigned(r.valid)+unsigned(r2.valid);
    const bool any_present=drawn_count!=0;
    const auto& fall_result=people.falls[0];
    const unsigned first_flags=two_person_analysis::flags(selected,people.ids[0],people.alarm[0]);
    const unsigned second_flags=two_person_analysis::flags(other,people.ids[1],people.alarm[1]);
    const auto movement=motion.region(previous_box.valid?std::min(r.x1,previous_box.x1):r.x1,
       previous_box.valid?std::min(r.y1,previous_box.y1):r.y1,
       previous_box.valid?std::max(r.x2,previous_box.x2):r.x2,
       previous_box.valid?std::max(r.y2,previous_box.y2):r.y2);
    previous_box=r;
#ifdef YOLO_MULTIMODAL
    if(fresh){
     const bool confirming=power.mode==scene_power::Verifying;
     power.observe(frame.started_ms,any_present,people.any_alarm);
     multimodal_sensors::observe_visual_presence(frame.started_ms,any_present||people.any_alarm);
     if(confirming&&power.mode==scene_power::Normal)log_line("POWER_CONFIRM present=%u alarm=%u next=NORMAL verify_ms=%u",any_present,people.any_alarm,frame.started_ms-power.verify_started);
    }else power.no_frame(milliseconds());
    const auto& net_alignment=multimodal_sensors::align_video(frame.started_ms,frame.sequence);
    const unsigned now_result=milliseconds();
    const unsigned elapsed_result=now_result-previous_result;
    multimodal_sensors::write_metrics(previous_result&&elapsed_result?10000/elapsed_result:0,infer_ms,selected.score);
    network_monitor::observe(people,net_alignment,
      frame.count,frame.started_ms,infer_ms,previous_result&&elapsed_result?10000/elapsed_result:0);
    previous_result=now_result;
#endif
    const unsigned submit_begin=milliseconds();
    const bool ack=cam::overlay_metadata(++sequence,r,r2,first_flags,second_flags);
#ifdef YOLO_MULTIMODAL
    // Recovery audio waits until this identity's current green rectangle is
    // committed to HDMI. A failed/stale submit cannot announce recovery.
    syn6658_voice::FallEvent voice_events[2];
    for(unsigned lane=0;lane<2;++lane){
      const auto& f=people.lane_falls[lane];const unsigned id=analysis.track(lane).id;
      const bool displayed=ack&&fresh&&((r.valid&&people.ids[0]==id)||(r2.valid&&people.ids[1]==id));
      voice_events[lane]={id,f.events,f.alarm,f.event,f.recovered,displayed};
      if(f.recovered)log_line("YFALL_RECOVERED person_id=%u event_id=%u standing_confirm_ms=%u green_committed=%u",id,f.events,fall_detection::Detector::kRecoverMs,displayed);
    }
    syn6658_voice::observe_pair(voice_events);
#endif
    const unsigned done=milliseconds(),submit_ms=done-submit_begin;
    log_line("YCAM_RESULT seq=%u source_seq=%u source_count=%u present=%u boxes=%u drawn=%u score_q15=%u pre_ms=%u infer_ms=%u post_ms=%u submit_ms=%u cycle_ms=%u uptime_ms=%u skipped=%u result_age_ms_est=%u overlay_ok=%u shown_seq=%u write_errors=%u read_errors=%u underflows=%u input_hash=%08x hash_sampled=%u",
       sequence,frame.sequence,frame.count,any_present,frame_people.count,drawn_count,selected.score,frame.pre_ms,infer_ms,post_ms,
       submit_ms,done-frame.started_ms,done-epoch,frame.skipped,done-frame.started_ms,ack,cam::hdmi[0x107c/4],
       cam::camera[8],cam::camera[9],cam::camera[10],input_hash,details);
    if(details){
    if(r.valid)log_line("YCAM_BOX seq=%u x1=%d y1=%d x2=%d y2=%d score_q15=%u",sequence,r.x1,r.y1,r.x2,r.y2,selected.score);
    if(r2.valid)log_line("YCAM_BOX2 seq=%u x1=%d y1=%d x2=%d y2=%d score_q15=%u",sequence,r2.x1,r2.y1,r2.x2,r2.y2,other.score);
    log_line("YCAM_PEOPLE seq=%u count=%u primary=%u secondary=%u full_scene=1 stale=%u",sequence,drawn_count,r.valid,r2.valid,!fresh);
    }
    log_line("YTRACK_FRAME seq=%u source_seq=%u ms=%u visible=%u active=%u primary_id=%u secondary_id=%u processing_ms=%u",
       sequence,frame.sequence,frame.started_ms,drawn_count,people.active,people.ids[0],people.ids[1],association_ms);
    for(unsigned slot=0;slot<2;++slot){
      const auto& t=analysis.track(slot);
      const bool is_primary=people.ids[0]&&t.id==people.ids[0];
      const bool is_secondary=people.ids[1]&&t.id==people.ids[1];
      if(!is_primary&&!is_secondary)continue;
      log_line("YTRACK_POINT seq=%u id=%u lane=%u ms=%u cx=%d cy=%d x1=%d y1=%d x2=%d y2=%d vx=%d vy=%d history=%u primary=%u alarm=%u",
         sequence,t.id,slot,frame.started_ms,(t.box.x1+t.box.x2)/2,(t.box.y1+t.box.y2)/2,
         t.box.x1,t.box.y1,t.box.x2,t.box.y2,t.vx,t.vy,t.history_count,is_primary,people.alarm[is_primary?0:1]);
    }
    for(unsigned j=0;j<2;++j){
      const bool visible=j==0?r.valid:r2.valid;if(!visible)continue;
      const auto& f=people.falls[j];
      const unsigned control=(j==0?first_flags:second_flags)&15u;
      log_line("YBEHAVIOR seq=%u id=%u index=%u ms=%u state=%s alarm=%u event=%u armed=%u prediction_enabled=0 control=%u pixels=%u support=%u appearance=%u bg_ready=%u",
        sequence,people.ids[j],j,frame.started_ms,fall_detection::state_name(f.state),f.alarm,f.event,f.armed,
        control,people.pixels[j],people.supports[j].support,people.supports[j].appearance,people.supports[j].ready);
    }
    if(details){
    log_line("YCAM_ROI seq=%u zoom=%u rotation=%u passes=%u x1=%d y1=%d x2=%d y2=%d held=0 threshold_q15=8192",
       sequence,selected_view.zoom,selected_view.turns*90,passes,selected_view.roi.x1,selected_view.roi.y1,selected_view.roi.x2,selected_view.roi.y2);
    log_line("YCAM_TRACK seq=%u source=%s bg_ready=%u foreground=%u support=%u known=%u scene_change=%u appearance=%u model_score_q15=%u processing_ms=%u held=0",
       sequence,!r.valid?"NONE":supported.fallback?"PIXELS":"YOLO",supported.ready,supported.foreground,
       supported.support,supported.known,supported.scene_change,supported.appearance,selected.score,tracking_ms);
    }
    if(details||fall_result.event)log_line("YFALL_RESULT seq=%u state=%s alarm=%u event=%u armed=%u tracked=%u track=%u events=%u w=%d h=%d ratio_milli=%d cx=%d cy=%d dy=%d drop_milli=%d evidence=%u candidate_ms=%u reference_height=%d reference_age_ms=%d drop_age_ms=%d motion_ready=%u diff_area=%u diff_cx=%d diff_cy=%d energy=%u control=%u",
       sequence,fall_detection::state_name(fall_result.state),fall_result.alarm,fall_result.event,fall_result.armed,
       fall_result.tracked,fall_result.track,fall_result.events,fall_result.width,fall_result.height,
       fall_result.ratio_milli,fall_result.cx,fall_result.cy,fall_result.dy,fall_result.drop_milli,
       fall_result.evidence,fall_result.candidate_ms,fall_result.reference_height,fall_result.reference_age_ms,fall_result.drop_age_ms,
       movement.ready,movement.changed_pixels,movement.cx,movement.cy,movement.energy,first_flags&15u);
    if(details){
    log_line("%s",any_present?"\xd3\xd0\xc8\xcb":"\xce\xde\xc8\xcb");
    // UART text is GBK, matching the existing Chinese person/empty output.
    if(people.any_alarm)log_line("\xc8\xcb\xcc\xe5\xb5\xf8\xb5\xb9");
    else if(any_present)log_line("\xd5\xfd\xb3\xa3");
    last_detail=detail_now;
    }
    last_good=done;stale_cleared=false;
  }
#else
  uint32_t magic=0;bool camera_mode=false;unsigned last_camera_log=0;
  for(;;) {
    const int c=read_command();
    if(c=='C'&&magic==0) {
      camera_mode=camera_source::available();log_line("YRAW_CAMERA enabled=%u",camera_mode);continue;
    }
    if(c=='R'&&magic==0) {camera_mode=false;camera_source::overlay(false,0,0,0,0);continue;}
    if(c=='P'&&magic==0) {
      camera_mode=false;unsigned sequence,pre_ms;
      if(!camera_source::capture(interpreter.input(0)->data.int8,&sequence,&pre_ms)) {
        log_line("YRAW_ERROR reason=camera_snapshot_unavailable");continue;
      }
      memcpy(snapshot,interpreter.input(0)->data.int8,kInputBytes);
      const unsigned infer_ms=invoke(interpreter,profile);decode(interpreter);
      for(unsigned i=0;i<box_count;++i) {
        const auto& b=boxes[i];
        log_line("YRAW_BOX frame=%u index=%u x1q=%d y1q=%d x2q=%d y2q=%d score_q15=%u",sequence,i,b.x1,b.y1,b.x2,b.y2,b.score);
      }
      log_line("YRAW_IMAGE seq=%u bytes=%u input_hash=%08x output_hash=%08x infer_ms=%u boxes=%u",
          sequence,kInputBytes,fnv(snapshot,kInputBytes),output_hash(interpreter),infer_ms,box_count);
      uart_write_bytes(snapshot,kInputBytes);log_line("YRAW_IMAGE_END");continue;
    }
    if(c=='Q'&&magic==0) {log_line("YRAW_READY bytes=%u output_bytes=%u variant=%s",kInputBytes,kOutputBytes,kVariant);continue;}
    if(camera_mode) {
      unsigned sequence,pre_ms;
      if(camera_source::capture(interpreter.input(0)->data.int8,&sequence,&pre_ms)) {
        const unsigned infer_ms=invoke(interpreter,profile),begin=milliseconds();decode(interpreter);
        const auto& b=boxes[0];const bool committed=camera_source::overlay(box_count!=0,b.x1,b.y1,b.x2,b.y2);
        log_line("YRAW_LIVE seq=%u present=%u boxes=%u pre_ms=%u infer_ms=%u post_ms=%u overlay_ok=%u",
            sequence,box_count!=0,box_count,pre_ms,infer_ms,milliseconds()-begin,committed);
        log_line("%s",box_count?"\xd3\xd0\xc8\xcb":"\xce\xde\xc8\xcb");last_camera_log=milliseconds();
      } else if(milliseconds()-last_camera_log>2000) {
        log_line("YRAW_CAMERA_WAIT setup=%08x lease=%08x",*reinterpret_cast<volatile uint32_t*>(0xf8105004u),camera_source::lease[2]);
        last_camera_log=milliseconds();
      }
      continue;
    }
    if(c<0)continue;
    magic=(magic>>8)|(uint32_t(c)<<24);
    if(magic!=0x31524659u) { // Keep only a prefix of YFR1; ignore CR/LF/noise.
      if(magic!=0x59000000u && magic!=0x46590000u && magic!=0x52465900u)
        magic=c=='Y'?0x59000000u:0;
      continue;
    }
    magic=0;uint8_t header[8];
    if(!read_bytes(header,8)||!read_bytes(reinterpret_cast<uint8_t*>(interpreter.input(0)->data.int8),kInputBytes)) {
      log_line("YRAW_ERROR reason=receive_timeout");continue;}
    frame_id=le32(header);const unsigned expected=le32(header+4);
    const auto hash=fnv(reinterpret_cast<uint8_t*>(interpreter.input(0)->data.int8),kInputBytes);
    if(hash!=expected) {log_line("YRAW_ERROR reason=input_hash frame=%u",frame_id);continue;}
    const unsigned elapsed=invoke(interpreter,profile);const uint32_t begin=milliseconds();
    decode(interpreter);const unsigned post_ms=milliseconds()-begin;
    const auto ohash=output_hash(interpreter);
    for(unsigned i=0;i<box_count;++i) {
      const auto& b=boxes[i];
      log_line("YRAW_BOX frame=%u index=%u x1q=%d y1q=%d x2q=%d y2q=%d score_q15=%u",frame_id,i,b.x1,b.y1,b.x2,b.y2,b.score);
    }
    log_line("YRAW_RESULT frame=%u input_hash=%08x output_hash=%08x infer_ms=%u post_ms=%u boxes=%u present=%u",
             frame_id,hash,ohash,elapsed,post_ms,box_count,box_count!=0);
  }
#endif
}
