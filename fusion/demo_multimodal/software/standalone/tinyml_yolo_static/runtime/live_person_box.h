#ifndef FUSION_LIVE_PERSON_BOX_H_
#define FUSION_LIVE_PERSON_BOX_H_

#include "person_layer.h"

namespace vision {
constexpr uint32_t kLiveBoxPeriodMs = 50;
constexpr uint32_t kLiveBoxEvidenceMs = 1200;

struct LiveBoxResult {
  Box proposal, display;
  uint32_t seq, sample_ms, generation;
  unsigned background_frames, foreground_pixels;
  bool background_ready, calibrating, scene_change, verified;
};

// Fixed-camera, single-person localization. Geometry is measured from NEW
// frames; only a separately classified crop can establish a human identity.
// No temporal-median background, whole-image placeholder, or held old box.
class LivePersonBox {
 public:
  LivePersonBox() : next_generation_(0) { Reset(); }
  void Reset();
  void CalibrateEmpty();
  LiveBoxResult Observe(const uint8_t* gray, uint32_t seq, uint32_t ms,
                        bool confident_empty, bool whole_person);
  bool Verify(uint32_t generation, bool person, uint32_t ms);
  LiveBoxResult result() const { return result_; }
 private:
  uint16_t background_[kImagePixels], queue_[kImagePixels];
  uint8_t minimum_[kImagePixels], maximum_[kImagePixels];
  uint8_t mask_[kImagePixels], work_[kImagePixels];
  uint16_t histogram_[511], rows_[kImageHeight], columns_[kImageWidth];
  LiveBoxResult result_;
  Box rejected_;
  uint32_t evidence_ms_, rejected_ms_, next_generation_, previous_ms_;
  unsigned calibration_frames_, rejected_attempts_;
  bool explicit_empty_, have_frame_, confirmed_;
  Box Segment(const uint8_t* gray, int shift, uint32_t ms);
};

// The 96x96 capture stretches a 1280x720 image. Choose a square in ORIGINAL
// video coordinates, with context, before resizing for the binary classifier.
// A tight tall crop stretched directly to 96x96 badly distorts the subject.
bool QuantizePersonContext(const uint8_t* gray, const Box& box,
                           const int8_t* lut, int8_t* input, unsigned view = 0);
}  // namespace vision
#endif
