#ifndef FUSION_PERSON_BOX_TRACKER_H_
#define FUSION_PERSON_BOX_TRACKER_H_

#include "person_layer.h"

namespace vision {
constexpr int kBoxRoiConfirmBp = 6000;
constexpr int kBoxRoiMaintainBp = 5000;
constexpr uint32_t kBoxConfirmWindowMs = 1500;
constexpr uint32_t kBoxMaxHoldMs = 1200;
constexpr uint32_t kBoxMaxSampleGapMs = 2500;

enum BoxTrackSource {
  kBoxNone, kBoxPending, kBoxRoiConfirmed, kBoxTrackHold,
  kBoxWaitBackground, kBoxCalibrating, kBoxSceneChange, kBoxExpired
};
const char* BoxTrackSourceName(BoxTrackSource source);

struct BoxTrackResult {
  bool present;
  Box box;
  BoxTrackSource source;
  unsigned positive_samples;
  int support_age_ms;
  unsigned missing_samples;
};

// Fixed-camera display tracker. A binary whole-frame score cannot supply a
// location: only an actual foreground crop independently accepted by MobileNet
// may establish a box. This class never supplies a full-image fallback box.
// It is independent of FallDetector and must not replace fall geometry.
class PersonBoxTracker {
 public:
  void Reset();
  BoxTrackResult Observe(const Box& foreground, bool roi_accepted, int roi_bp,
                         int whole_bp, bool bg_ready, bool calibrating,
                         bool scene_change, uint32_t seq, uint32_t ms);
 private:
  Box candidate_;
  BoxTrackResult last_result_;
  uint32_t last_seq_, last_sample_ms_, last_strong_ms_, pending_start_ms_;
  unsigned history_, missing_;
  bool have_sample_, have_strong_, active_;
};
}  // namespace vision
#endif
