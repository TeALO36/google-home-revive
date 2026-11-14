// Host unit test of the spoken IP address sequence.
//   g++ -std=c++17 -Wall -Wextra -Werror -I firmware/s3 firmware/tests/test_ip_speech.cpp -o test_ip && ./test_ip
#include <cstdio>
#include <string>

#include "ip_speech.h"

namespace {

int failures = 0;

// Clips are plain names here; on the device they are audio::AudioFile pointers.
const ip_speech::BasicClips<std::string> kClips = {{"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}, "point"};

std::string spoken(const std::string &ip) {
  std::string out;
  for (const std::string &clip : ip_speech::sequence(ip, kClips)) {
    out += out.empty() ? clip : " " + clip;
  }
  return out;
}

void expect_spoken(const std::string &ip, const std::string &expected) {
  const std::string got = spoken(ip);
  if (got != expected) {
    std::fprintf(stderr, "FAIL: %s -> '%s', expected '%s'\n", ip.c_str(), got.c_str(), expected.c_str());
    ++failures;
  }
}

}  // namespace

int main() {
  expect_spoken("192.168.1.20", "1 9 2 point 1 6 8 point 1 point 2 0");
  expect_spoken("10.0.0.7", "1 0 point 0 point 0 point 7");
  expect_spoken("", "");
  expect_spoken("1.2 x", "1 point 2");  // anything else is skipped
  if (failures == 0) {
    std::puts("ip_speech: all tests passed");
  }
  return failures == 0 ? 0 : 1;
}
