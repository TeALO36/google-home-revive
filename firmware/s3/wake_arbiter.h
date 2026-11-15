// Nearest-device arbitration between GH-Revive speakers that heard the same wake word.
//
// Every speaker keeps the loudest microphone level of the last moments (the wake word itself). On detection it
// broadcasts a claim {device id, level} on the LAN and waits a short window for the claims of the others. The
// loudest claim wins (equal levels: the highest id), so only the speaker closest to the voice starts the pipeline.
// Home Assistant still drops a second pipeline (duplicate_wake_up_detected) if a claim is lost on the network.
//
// The phone does not take part: it streams as soon as it hears the wake word, before any speaker has finished
// waiting, so a phone that heard the wake word always wins.
//
// Pure C++ (no ESPHome dependency): compiled by ESPHome through `includes:` and by the host unit test.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace wake_arbiter {

// ------------------------------------------------------------------ loudness of the last moments

// Rolling maximum of the microphone level (dB) over `span_ms`, fed by the sound_level sensor.
class LoudnessTracker {
 public:
  static constexpr size_t kSlots = 32;

  explicit LoudnessTracker(uint32_t span_ms = 1500) : span_ms_(span_ms) {}

  void add(float level_db, uint32_t now_ms) {
    samples_[next_] = Sample{level_db, now_ms, true};
    next_ = (next_ + 1) % kSlots;
  }

  // Loudest level inside the span, or `floor_db` when nothing was measured.
  float recent_max(uint32_t now_ms, float floor_db = -120.0f) const {
    float best = floor_db;
    for (const Sample &s : samples_) {
      if (s.valid && now_ms - s.at_ms <= span_ms_ && s.level_db > best) {
        best = s.level_db;
      }
    }
    return best;
  }

 private:
  struct Sample {
    float level_db = 0.0f;
    uint32_t at_ms = 0;
    bool valid = false;
  };

  uint32_t span_ms_;
  std::array<Sample, kSlots> samples_{};
  size_t next_ = 0;
};

// ------------------------------------------------------------------ claim packet

// 10 bytes: "GHW1", device id (big endian), level in tenths of dB (signed, big endian).
struct Claim {
  uint32_t device_id = 0;
  int16_t level_ddb = 0;
};

constexpr std::array<uint8_t, 4> kMagic = {'G', 'H', 'W', '1'};
constexpr size_t kPacketSize = 10;

inline int16_t to_ddb(float level_db) {
  const float scaled = level_db * 10.0f;
  if (scaled > 32767.0f) {
    return 32767;
  }
  if (scaled < -32768.0f) {
    return -32768;
  }
  return static_cast<int16_t>(scaled < 0.0f ? scaled - 0.5f : scaled + 0.5f);
}

inline std::vector<uint8_t> encode(const Claim &claim) {
  std::vector<uint8_t> out(kMagic.begin(), kMagic.end());
  for (int shift = 24; shift >= 0; shift -= 8) {
    out.push_back(static_cast<uint8_t>(claim.device_id >> shift));
  }
  const uint16_t level = static_cast<uint16_t>(claim.level_ddb);
  out.push_back(static_cast<uint8_t>(level >> 8));
  out.push_back(static_cast<uint8_t>(level));
  return out;
}

// Returns false for anything that is not a claim (other UDP traffic on the port).
inline bool decode(const uint8_t *data, size_t size, Claim &claim) {
  if (data == nullptr || size != kPacketSize) {
    return false;
  }
  for (size_t i = 0; i < kMagic.size(); ++i) {
    if (data[i] != kMagic[i]) {
      return false;
    }
  }
  claim.device_id = (static_cast<uint32_t>(data[4]) << 24) | (static_cast<uint32_t>(data[5]) << 16) |
                    (static_cast<uint32_t>(data[6]) << 8) | static_cast<uint32_t>(data[7]);
  claim.level_ddb = static_cast<int16_t>((static_cast<uint16_t>(data[8]) << 8) | data[9]);
  return true;
}

// ------------------------------------------------------------------ decision

enum class Verdict : uint8_t { Idle, Waiting, Won, Lost };

class Arbiter {
 public:
  static constexpr size_t kPeers = 8;

  // `lead_ms`: a peer claim this much older than the local detection still counts (devices detect at
  // slightly different moments). `stale_ms`: claims older than this belong to an earlier wake word.
  explicit Arbiter(uint32_t lead_ms = 1000, uint32_t stale_ms = 3000) : lead_ms_(lead_ms), stale_ms_(stale_ms) {}

  void set_device_id(uint32_t device_id) { self_id_ = device_id; }
  uint32_t device_id() const { return self_id_; }

  // Local wake word detected: returns the claim to broadcast.
  Claim claim(float level_db, uint32_t now_ms) {
    local_ = Claim{self_id_, to_ddb(level_db)};
    local_ms_ = now_ms;
    pending_ = true;
    return local_;
  }

  // Last claim made by this device (what is broadcast, possibly several times against packet loss).
  const Claim &last_claim() const { return local_; }

  // Claim received from the network (our own broadcast echoes back and is ignored).
  void peer(const Claim &claim, uint32_t now_ms) {
    if (claim.device_id == self_id_) {
      return;
    }
    Slot &slot = slot_for(claim.device_id, now_ms);
    slot = Slot{claim, now_ms, true};
  }

  // Decision once the wait window is over. Clears the pending claim.
  Verdict decide(uint32_t now_ms) {
    if (!pending_) {
      return Verdict::Idle;
    }
    pending_ = false;
    for (const Slot &slot : peers_) {
      if (counts(slot, now_ms) && beats(slot.claim, local_)) {
        return Verdict::Lost;
      }
    }
    return Verdict::Won;
  }

  // True while a louder peer already claimed this wake word: no need to wait for the window.
  bool already_lost(uint32_t now_ms) const {
    if (!pending_) {
      return false;
    }
    for (const Slot &slot : peers_) {
      if (counts(slot, now_ms) && beats(slot.claim, local_)) {
        return true;
      }
    }
    return false;
  }

 private:
  struct Slot {
    Claim claim;
    uint32_t at_ms = 0;
    bool valid = false;
  };

  static bool beats(const Claim &a, const Claim &b) {
    return a.level_ddb != b.level_ddb ? a.level_ddb > b.level_ddb : a.device_id > b.device_id;
  }

  bool counts(const Slot &slot, uint32_t now_ms) const {
    if (!slot.valid || now_ms - slot.at_ms > stale_ms_) {
      return false;
    }
    const int32_t age_at_detection = static_cast<int32_t>(local_ms_ - slot.at_ms);
    return age_at_detection <= static_cast<int32_t>(lead_ms_);
  }

  // Same device -> same slot; otherwise a free or stale slot; otherwise the oldest one.
  Slot &slot_for(uint32_t device_id, uint32_t now_ms) {
    Slot *oldest = &peers_[0];
    for (Slot &slot : peers_) {
      if (slot.valid && slot.claim.device_id == device_id) {
        return slot;
      }
    }
    for (Slot &slot : peers_) {
      if (!slot.valid || now_ms - slot.at_ms > stale_ms_) {
        return slot;
      }
      if (slot.at_ms < oldest->at_ms) {
        oldest = &slot;
      }
    }
    return *oldest;
  }

  uint32_t lead_ms_;
  uint32_t stale_ms_;
  uint32_t self_id_ = 0;
  Claim local_{};
  uint32_t local_ms_ = 0;
  bool pending_ = false;
  std::array<Slot, kPeers> peers_{};
};

// Device-wide instances used by the ESPHome lambdas (ESPHome emits `includes:` after its globals).
inline LoudnessTracker &loudness() {
  static LoudnessTracker instance;
  return instance;
}

inline Arbiter &arbiter() {
  static Arbiter instance;
  return instance;
}

}  // namespace wake_arbiter
