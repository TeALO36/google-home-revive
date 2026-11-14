// Host unit test of the ring gesture decoder.
//   g++ -std=c++17 -Wall -Wextra -Werror -I firmware/s3 firmware/tests/test_ring_gesture.cpp -o test_ring && ./test_ring
#include <cstdio>
#include <cstdlib>

#include "ring_gesture.h"

using ring::Decoder;
using ring::Event;

namespace {

int failures = 0;

void expect(bool condition, const char *what) {
  if (!condition) {
    std::fprintf(stderr, "FAIL: %s\n", what);
    ++failures;
  }
}

void test_clockwise_is_volume_up() {
  Decoder d;
  expect(d.press(5, 0) == Event::None, "first touch is silent");
  expect(d.press(4, 80) == Event::VolumeUp, "5 -> 4 is clockwise");
  expect(d.press(3, 160) == Event::VolumeUp, "4 -> 3 is clockwise");
  expect(d.release(3, 400) == Event::None, "release after rotation is silent");
  expect(d.poll(2000) == Event::None, "no tap after a rotation");
}

void test_anticlockwise_wraps() {
  Decoder d;
  d.press(9, 0);
  expect(d.press(0, 60) == Event::VolumeDown, "9 -> 0 is anticlockwise");
  Decoder e;
  e.press(0, 0);
  expect(e.press(9, 60) == Event::VolumeUp, "0 -> 9 is clockwise");
}

void test_single_tap() {
  Decoder d;
  d.press(2, 1000);
  expect(d.release(2, 1100) == Event::None, "tap waits for the double-tap window");
  expect(d.poll(1300) == Event::None, "still inside the window");
  expect(d.poll(1600) == Event::Tap, "tap emitted after the window");
  expect(d.poll(1700) == Event::None, "tap emitted once");
}

void test_double_tap() {
  Decoder d;
  d.press(7, 0);
  d.release(7, 100);
  d.press(1, 250);
  expect(d.release(1, 330) == Event::DoubleTap, "second short touch is a double tap");
  expect(d.poll(2000) == Event::None, "no extra tap");
}

void test_long_press_and_jumps() {
  Decoder d;
  d.press(4, 0);
  expect(d.release(4, 900) == Event::None, "long press is not a tap");
  expect(d.poll(3000) == Event::None, "long press emits nothing");
  d.press(1, 4000);
  expect(d.press(6, 4050) == Event::None, "jump across the ring is ignored");
  expect(d.release(6, 4100) == Event::None, "release of a non-current sector is ignored");
  expect(d.press(-1, 4200) == Event::None, "invalid sector ignored");
}

}  // namespace

int main() {
  test_clockwise_is_volume_up();
  test_anticlockwise_wraps();
  test_single_tap();
  test_double_tap();
  test_long_press_and_jumps();
  if (failures != 0) {
    std::fprintf(stderr, "%d check(s) failed\n", failures);
    return EXIT_FAILURE;
  }
  std::puts("ring_gesture: all checks passed");
  return EXIT_SUCCESS;
}
