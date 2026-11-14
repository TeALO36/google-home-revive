#pragma once

// Turns an IPv4 address into the list of voice clips to play: "192.168.1.20" -> 1 9 2 point 1 6 8 point 1 point 2 0.
// Header-only and template-based so the host test (firmware/tests) runs without ESPHome.
#include <array>
#include <string>
#include <vector>

namespace ip_speech {

template<typename Clip> struct BasicClips {
  std::array<Clip, 10> digits;
  Clip point;
};

template<typename Clip> std::vector<Clip> sequence(const std::string &ip, const BasicClips<Clip> &clips) {
  std::vector<Clip> out;
  out.reserve(ip.size());
  for (const char c : ip) {
    if (c >= '0' && c <= '9') {
      out.push_back(clips.digits[static_cast<size_t>(c - '0')]);
    } else if (c == '.') {
      out.push_back(clips.point);
    }
  }
  return out;
}

#ifdef USE_ESP32
using Clips = BasicClips<const esphome::audio::AudioFile *>;
#endif

}  // namespace ip_speech
