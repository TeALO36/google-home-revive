// Host unit test of the nearest-device wake arbitration.
//   g++ -std=c++17 -Wall -Wextra -Werror -I firmware/s3 firmware/tests/test_wake_arbiter.cpp -o test_arbiter && ./test_arbiter
#include <cstdio>
#include <cstdlib>
#include <vector>

#include "wake_arbiter.h"

using wake_arbiter::Arbiter;
using wake_arbiter::Claim;
using wake_arbiter::Verdict;

namespace {

int failures = 0;

void expect(bool condition, const char *what) {
  if (!condition) {
    std::fprintf(stderr, "FAIL: %s\n", what);
    ++failures;
  }
}

void test_loudness_window() {
  wake_arbiter::LoudnessTracker t(1500);
  expect(t.recent_max(0) == -120.0f, "empty tracker gives the floor");
  t.add(-50.0f, 1000);
  t.add(-32.5f, 1100);
  t.add(-45.0f, 1200);
  expect(t.recent_max(1300) == -32.5f, "loudest recent level");
  expect(t.recent_max(2700) == -45.0f, "levels older than the span are forgotten");
  for (uint32_t i = 0; i < 40; ++i) {
    t.add(-60.0f, 3000 + i * 10);
  }
  expect(t.recent_max(3400) == -60.0f, "ring buffer overwrites old samples");
}

void test_packet_round_trip() {
  const Claim in{0x00A1B2C3u, wake_arbiter::to_ddb(-31.26f)};
  const std::vector<uint8_t> bytes = wake_arbiter::encode(in);
  expect(bytes.size() == wake_arbiter::kPacketSize, "packet size");
  Claim out;
  expect(wake_arbiter::decode(bytes.data(), bytes.size(), out), "packet decodes");
  expect(out.device_id == in.device_id, "id survives");
  expect(out.level_ddb == -313, "level rounded to tenths of dB");
  std::vector<uint8_t> bad = bytes;
  bad[0] = 'X';
  expect(!wake_arbiter::decode(bad.data(), bad.size(), out), "wrong magic rejected");
  expect(!wake_arbiter::decode(bytes.data(), 9, out), "short packet rejected");
  expect(!wake_arbiter::decode(nullptr, 10, out), "null rejected");
}

void test_loudest_wins() {
  Arbiter bedroom;
  Arbiter living;
  bedroom.set_device_id(1);
  living.set_device_id(2);
  const Claim b = bedroom.claim(-30.0f, 1000);
  const Claim l = living.claim(-42.0f, 1060);
  bedroom.peer(l, 1065);
  living.peer(b, 1070);
  expect(living.already_lost(1070), "quieter device knows it lost early");
  expect(!bedroom.already_lost(1070), "louder device does not");
  expect(bedroom.decide(1300) == Verdict::Won, "closest device wins");
  expect(living.decide(1360) == Verdict::Lost, "farther device stays silent");
  expect(bedroom.decide(1400) == Verdict::Idle, "decision is taken once");
}

void test_alone_and_echo() {
  Arbiter a;
  a.set_device_id(7);
  const Claim own = a.claim(-50.0f, 500);
  a.peer(own, 505);
  expect(a.decide(800) == Verdict::Won, "own broadcast echo is ignored, a lone device wins");
}

void test_tie_and_stale() {
  Arbiter a;
  a.set_device_id(3);
  a.peer(Claim{9, -400}, 100);
  a.claim(-40.0f, 5000);
  expect(a.decide(5300) == Verdict::Won, "claim from an earlier wake word is ignored");
  a.peer(Claim{9, -400}, 6000);
  a.claim(-40.0f, 6050);
  expect(a.decide(6300) == Verdict::Lost, "equal level: highest id wins");
  Arbiter b;
  b.set_device_id(12);
  b.peer(Claim{9, -400}, 6000);
  b.claim(-40.0f, 6050);
  expect(b.decide(6300) == Verdict::Won, "equal level, higher id");
}

void test_many_peers() {
  Arbiter a;
  a.set_device_id(100);
  for (uint32_t id = 1; id <= 12; ++id) {
    a.peer(Claim{id, -600}, 1000 + id);
  }
  a.peer(Claim{5, -200}, 1020);
  a.claim(-35.0f, 1030);
  expect(a.decide(1300) == Verdict::Lost, "updated claim of a known peer is kept");
}

}  // namespace

int main() {
  test_loudness_window();
  test_packet_round_trip();
  test_loudest_wins();
  test_alone_and_echo();
  test_tie_and_stale();
  test_many_peers();
  if (failures != 0) {
    std::fprintf(stderr, "%d check(s) failed\n", failures);
    return EXIT_FAILURE;
  }
  std::puts("wake_arbiter: all checks passed");
  return EXIT_SUCCESS;
}
