// Ring gesture decoder for the 10 capacitive sectors of the top board (MPR121 ELE0..ELE9).
//
// Viewed from the top of the device the electrode index increases ANTICLOCKWISE (the electrodes sit on
// B.Cu, facing the plastic). Clockwise rotation therefore walks the indexes downwards.
//
//   clockwise one sector      -> VolumeUp
//   anticlockwise one sector  -> VolumeDown
//   short touch, no rotation  -> Tap (reported once the double-tap window has expired)
//   two taps in a row         -> DoubleTap
//
// Pure C++ (no ESPHome dependency): compiled by ESPHome through `includes:` and by the host unit test.
#pragma once

#include <cstdint>

namespace ring {

enum class Event : uint8_t { None, VolumeUp, VolumeDown, Tap, DoubleTap };

struct Timing {
  uint32_t tap_max_ms = 350;         // longer touches are not taps
  uint32_t double_tap_gap_ms = 400;  // max release-to-release gap between two taps
};

class Decoder {
 public:
  static constexpr int kSectors = 10;
  static constexpr int kNoSector = -1;

  explicit Decoder(Timing timing = Timing()) : timing_(timing) {}

  // A sector reports touched. Returns a volume event when the finger moved to an adjacent sector.
  Event press(int sector, uint32_t now_ms) {
    if (sector < 0 || sector >= kSectors) {
      return Event::None;
    }
    if (current_ == kNoSector) {
      current_ = sector;
      touch_start_ms_ = now_ms;
      rotated_ = false;
      return Event::None;
    }
    return step_to(sector);
  }

  // A sector reports released. Only the release of the last touched sector ends the touch.
  Event release(int sector, uint32_t now_ms) {
    if (sector != current_) {
      return Event::None;
    }
    current_ = kNoSector;
    const bool short_touch = !rotated_ && (now_ms - touch_start_ms_) <= timing_.tap_max_ms;
    if (!short_touch) {
      pending_tap_ = false;
      return Event::None;
    }
    if (pending_tap_ && (now_ms - last_tap_ms_) <= timing_.double_tap_gap_ms) {
      pending_tap_ = false;
      return Event::DoubleTap;
    }
    pending_tap_ = true;
    last_tap_ms_ = now_ms;
    return Event::None;
  }

  // Call periodically: emits the single Tap once no second tap can follow.
  Event poll(uint32_t now_ms) {
    if (pending_tap_ && current_ == kNoSector && (now_ms - last_tap_ms_) > timing_.double_tap_gap_ms) {
      pending_tap_ = false;
      return Event::Tap;
    }
    return Event::None;
  }

 private:
  Event step_to(int sector) {
    const int delta = (sector - current_ + kSectors) % kSectors;
    if (delta == kSectors - 1) {  // index - 1: clockwise seen from the top
      current_ = sector;
      rotated_ = true;
      pending_tap_ = false;
      return Event::VolumeUp;
    }
    if (delta == 1) {  // index + 1: anticlockwise seen from the top
      current_ = sector;
      rotated_ = true;
      pending_tap_ = false;
      return Event::VolumeDown;
    }
    return Event::None;  // same sector or a jump (two fingers, noise): ignored
  }

  Timing timing_;
  int current_ = kNoSector;
  bool rotated_ = false;
  bool pending_tap_ = false;
  uint32_t touch_start_ms_ = 0;
  uint32_t last_tap_ms_ = 0;
};

}  // namespace ring
