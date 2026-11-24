#ifndef FUSION_PERSON_LAYER_H_
#define FUSION_PERSON_LAYER_H_

#include <stdint.h>

namespace vision {
constexpr int kImageWidth = 96;
constexpr int kImageHeight = 96;
constexpr int kImagePixels = kImageWidth * kImageHeight;
constexpr int kBackgroundFrames = 8;
constexpr int kEmptyConfidenceBp = 7000;
constexpr int kRegionConfidenceBp = 6000;
constexpr int kBootstrapFrames = 5;
constexpr int kWholePersonConfidenceBp = 6000;
constexpr int kPresenceRoiConfidenceBp = 5500;
constexpr uint32_t kPersonHoldMs = 800;
constexpr uint32_t kPersonMaxGapMs = 2500;
enum BackgroundMode { kBackgroundNone, kEmptyMean, kTemporalMedian, kExplicitEmpty };

// Basis points of the model's dequantized Softmax score, not accuracy.
int ProbabilityBasisPoints(int8_t raw, float scale, int zero_point);

struct Box {
  int x, y, width, height, foreground_area;
  bool valid;
};

bool RegionsAssociated(const Box& a, const Box& b);
enum PresenceSource {
  kPresenceNone, kPresencePending, kPresenceWhole, kPresenceRoi,
  kPresenceHold, kPresenceSceneChange, kPresenceExpired
};
const char* PresenceSourceName(PresenceSource source);
struct PresenceResult {
  bool present;
  PresenceSource source;
  unsigned positive_samples;
  int support_age_ms;
  Box box;
  bool coarse_box;
};

// Combine whole-frame and local evidence. Two positives in three NEW samples
// establish presence; weak scores can maintain a confirmed person briefly.
// Strong whole-frame evidence remains usable without a calibrated background.
// A full-frame box is explicitly coarse until a local region is confirmed.
class PersonPresenceFilter {
 public:
  void Reset();
  PresenceResult Observe(int whole_person_bp, int roi_person_bp, const Box& box,
                         bool background_ready, bool scene_change,
                         uint32_t seq, uint32_t ms,
                         BackgroundMode mode = kBackgroundNone,
                         bool verified_fall_track = false);
 private:
  Box candidate_;
  PresenceResult last_result_;
  uint32_t last_seq_, last_ms_, last_support_ms_;
  unsigned roi_history_, whole_hits_, missing_frames_;
  bool have_sample_, have_support_, background_ready_;
};

enum RegionState {
  kWaitEmpty, kCalibrating, kNoPerson, kNoForeground, kSceneChange,
  kRoiPending, kRoiRejected, kRegionValid
};
const char* RegionStateName(RegionState state);

// A foreground proposal for a fixed camera. It is not a detector output:
// the caller must separately classify its crop before marking a person region.
class PersonRegionLocator {
 public:
  void Reset();
  // Only after the operator explicitly confirms an empty, fixed camera view.
  void StartEmptyCalibration() { Reset(); explicit_calibration_ = true; }
  bool explicit_calibration_pending() const { return explicit_calibration_; }
  // keep_tracking freezes background adaptation and searches foreground even
  // when MobileNet briefly misses an already verified tracked person.
  Box Observe(const uint8_t* gray, bool person, int no_person_confidence_bp,
              bool keep_tracking = false);
  bool background_ready() const { return background_frames_ == kBackgroundFrames; }
  unsigned background_frames() const { return background_frames_; }
  RegionState state() const { return state_; }
  BackgroundMode background_mode() const { return background_mode_; }
  // The caller replays these already received frames once, to establish motion
  // history. This is an estimated background, never a declared empty image.
  bool bootstrap_pending() const { return bootstrap_pending_; }
  const uint8_t* bootstrap_frame(unsigned i) const {
    return i < kBootstrapFrames ? bootstrap_[i] : nullptr;
  }

 private:
  unsigned background_frames_;
  RegionState state_;
  BackgroundMode background_mode_;
  unsigned bootstrap_count_;
  bool bootstrap_pending_;
  bool explicit_calibration_;
  uint8_t bootstrap_[kBootstrapFrames][kImagePixels];
  bool TryTemporalBootstrap(const uint8_t* gray);
  // Empty-frame sums during calibration; Q8 grayscale once calibrated.
  uint16_t background_[kImagePixels];
  uint8_t foreground_[kImagePixels];
  uint16_t queue_[kImagePixels];
  uint16_t difference_histogram_[511];
};

// Both operations reject invalid boxes; bounds use inclusive origin and size.
Box MapBoxToVideo(const Box& box, int video_width, int video_height);
bool QuantizeRegion(const uint8_t* gray, const Box& box,
                    const int8_t* gray_lut, int8_t* input,
                    int width_multiplier = 1);
}  // namespace vision
#endif
