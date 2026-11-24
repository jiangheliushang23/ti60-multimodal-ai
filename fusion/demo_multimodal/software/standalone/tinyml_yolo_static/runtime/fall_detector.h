#ifndef FUSION_FALL_DETECTOR_H_
#define FUSION_FALL_DETECTOR_H_
#include "motion_features.h"

namespace vision {
struct FallConfig {
  uint32_t still_ms, transition_ms, baseline_ms, candidate_timeout_ms, max_gap_ms;
  int upright_ratio_q1000, low_ratio_q1000, ratio_change_q1000;
  int drop_q1000, remaining_height_bp;
  int still_area_bp, still_energy_bp, burst_area_bp, burst_energy_bp;
};
FallConfig DefaultFallConfig();
enum FallState {
  kFallCalibrating, kFallEmpty, kFallNormal, kFallLowPosture,
  kFallSuspected, kFallStill, kFallUnreliable, kFallAlarm
};
const char* FallStateName(FallState state);
const char* FallResultName(FallState state);
struct GeometryFeatures {
  bool valid;
  int width, height, ratio_q1000, center_x, center_y;
  int delta_y, velocity_y, drop_q1000;
};
struct FallResult {
  FallState state;
  bool alarm, valid, person_tracked, baseline_ready;
  uint32_t still_ms;
  GeometryFeatures geometry;
};

// Fixed-camera, single-person visual heuristic. Alarm is latched until Reset.
// It does not use temperature or claim full-body keypoint estimation.
class FallDetector {
 public:
  void Reset(const FallConfig& config = DefaultFallConfig());
  bool WantsRegion(uint32_t now) const;
  FallResult Update(const Box& region, bool human_confirmed, bool model_person,
                    bool background_ready, uint32_t seq, uint32_t sample_ms,
                    const MotionFeatures& motion);
 private:
  struct Sample { GeometryFeatures geometry; uint32_t ms; };
  FallConfig config_;
  Sample history_[8];
  unsigned history_count_, history_next_;
  Box tracked_region_;
  GeometryFeatures previous_geometry_, origin_;
  uint32_t last_ms_, last_track_ms_, last_seq_, candidate_ms_, still_ms_;
  uint32_t last_human_ms_;
  unsigned human_confirmations_;
  bool have_track_, have_sample_, candidate_, previous_still_, alarm_;
  FallResult last_result_;
  void ClearTrack();
};
}  // namespace vision
#endif
