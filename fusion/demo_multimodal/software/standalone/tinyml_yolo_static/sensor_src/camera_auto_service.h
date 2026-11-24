#pragma once
#include "camera_auto.h"
#include "camera_rate.h"
#include "port.h"

// Independent of the frame lease at 0xF8105100 and thermal I2C at 0xF8103000.
// Each call advances at most one AE/AWB state; it never waits on a frame or bus.
namespace camera_auto_service {
static volatile uint32_t* const registers=reinterpret_cast<volatile uint32_t*>(0xf8105200u);
static volatile uint32_t* const camera=reinterpret_cast<volatile uint32_t*>(0xf8105000u);
static CameraAuto automatic(registers,camera);
static bool enabled=false;
static unsigned last_log=0;
static CameraRate rate;
static bool desired_low=false;
static unsigned logged_rate_retry=0;
inline void request_low_power(bool low){desired_low=low;}
inline bool low_power(){return rate.low;}
inline bool rate_settled(){return rate.settled();}
inline bool rate_failed(){return rate.fault!=0;}

inline void initialize() {
  if(registers[0]!=0x41555431u||camera[0]!=0x43414d32u) {
    log_line("CAM_AUTO_FATAL reason=register_identity base=f8105200");
    compat_fatal("camera_auto_bit_identity");
  }
  enabled=true;
  log_line("CAM_AUTO_READY build=yolo_auto_v1 base=f8105200 algorithm=cpu_ae_awb_v1 cooperative=1");
}
inline void service() {
  if(!enabled)return;
  const unsigned now=milliseconds();
  if(rate.state==CameraRate::Failed&&unsigned(now-rate.entered)>=CameraRate::kRecoveryMs){
    rate.retry_recovery(now,registers[13]);logged_rate_retry=0;
    log_line("POWER_CAMERA_RETRY normal_restore=1 cooldown_ms=%u",CameraRate::kRecoveryMs);
  }
  if(rate.busy()){
    rate.step(now,registers);
    if(rate.settled()){
      automatic.since=registers[13];automatic.settle=0;automatic.enter(CameraAuto::WaitFrames,now);
      log_line("POWER_CAMERA low=%u requested_fps=%u vts=%u verified=1 algorithm=vts_mailbox_v2",rate.low,rate.low?5:30,rate.low?9000:1500);
    }else if(rate.fault&&logged_rate_retry!=rate.retries+1){
      logged_rate_retry=rate.retries+1;
      log_line("POWER_CAMERA_ERROR code=%u restore_attempt=%u terminal=%u command=%u reg=%04x expected=%02x response=%03x bus_status=%x inference_fallback=1 retry_ms=%u",
        rate.fault,rate.retries,rate.state==CameraRate::Failed,rate.failed_command,CameraRate::address(rate.failed_command),
        CameraRate::value(rate.failed_command,rate.target),rate.failed_response,rate.bus_status,CameraRate::kRecoveryMs);
    }
    return;
  }
  if(!rate.fault&&desired_low!=rate.low&&automatic.ready&&
     (automatic.state==CameraAuto::WaitFrames||automatic.state==CameraAuto::Stopped)){
    logged_rate_retry=0;rate.request(desired_low,now,registers[13]);return;
  }
  if(rate.low||rate.fault)return;
  automatic.step(now);
  if(!automatic.fresh)return;
  if(!automatic.fault&&unsigned(now-last_log)<1000u)return;
  automatic.fresh=false;last_log=now;
  const CameraStats& s=automatic.stats;
  const CameraDecision& d=automatic.next;
  log_line("CAM_AUTO ms=%u frame=%u state=%u mean=%u rgb=%u,%u,%u clip=%u samples=%u exposure=%u gain=%x wb=%u,%u updates=%u fault=%x",
    now,unsigned(s.sequence),unsigned(automatic.state),unsigned(d.mean),unsigned(d.r_mean),unsigned(d.g_mean),unsigned(d.b_mean),
    unsigned(s.clipped),unsigned(s.samples),unsigned(automatic.exposure),unsigned(camera_gain_code(automatic.gain_index)),
    unsigned(automatic.r),unsigned(automatic.b),unsigned(automatic.updates),unsigned(automatic.fault));
}
}
