#ifndef FUSION_MOTION_FEATURES_H_
#define FUSION_MOTION_FEATURES_H_
#include "person_layer.h"

namespace vision {
constexpr uint32_t kMotionMaxGapMs = 1200;
struct MotionFeatures {
  bool valid, centroid_valid, scene_change;
  uint32_t dt_ms;
  int pixels, area, area_bp, energy_bp, centroid_x, centroid_y;
  int brightness_shift, global_area_bp;
};

// Differences are computed in fixed camera coordinates, before ROI resizing.
class MotionAnalyzer {
 public:
  void Reset();
  MotionFeatures Observe(const uint8_t* gray, uint32_t seq, uint32_t sample_ms,
                         const Box& region);
 private:
  uint8_t previous_[kImagePixels];
  uint16_t histogram_[511];
  uint32_t previous_seq_, previous_ms_;
  Box previous_region_;
  bool have_previous_;
};
}  // namespace vision
#endif
