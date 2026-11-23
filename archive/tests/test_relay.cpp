// Desktop test of firmware/vanturtle_relay.h: what the ESP32 beside a VanTurtle board does
// with press requests (option E).
//   mkdir -p .build && c++ -std=c++17 -o .build/test_relay archive/tests/test_relay.cpp && .build/test_relay
#include <cstdio>
#include <cstdlib>
#include <string_view>

#include "../firmware/vanturtle_relay.h"

static int failures = 0;
#define CHECK(cond)                                                \
  do {                                                             \
    if (!(cond)) {                                                 \
      std::printf("FAILED line %d: %s\n", __LINE__, #cond);        \
      failures++;                                                  \
    }                                                              \
  } while (0)

int main() {
  Relay r;

  // A press: decided, then finished with the inputs read afterwards.
  CHECK(r.request(101, 1, 0x10, 750, 250) == RELAY_PRESS);
  CHECK(r.busy == 101 && r.out_reg() == 0x02 && r.press_bits() == 0x12);  // LED lit with the key
  CHECK(r.request(101, 1, 0x10, 750, 250) == RELAY_WAIT);     // resent while pressing: no answer yet
  CHECK(r.request(102, 1, 0x20, 150, 250) == RELAY_REFUSE);   // another press while busy
  CHECK(std::string_view(r.refusal) == "busy");
  const RelayAnswer &a = r.finished(true, true, 0x01, 0xFF);
  CHECK(a.seq == 101 && a.ok && a.fresh && a.in1 == 0x01 && r.busy == 0);

  // The same seq again (its answer was lost): answer, never press twice.
  CHECK(r.request(101, 1, 0x10, 750, 250) == RELAY_REPEAT);
  CHECK(r.find(101) != nullptr && r.find(101)->ok);

  // Port 2 uses the second output register.
  CHECK(r.request(102, 2, 0x20, 150, 250) == RELAY_PRESS && r.out_reg() == 0x03);
  r.finished(false, false, 0xFF, 0xFF);  // I2C failed: remembered as not pressed
  CHECK(r.request(102, 2, 0x20, 150, 250) == RELAY_REPEAT && !r.find(102)->ok);

  // Bad requests are refused and change nothing.
  const int bad[][4] = {
      {0, 0x10, 150, 250},     // no port 0
      {3, 0x10, 150, 250},     // no port 3
      {1, 0x00, 150, 250},     // no key
      {1, 0x11, 150, 250},     // bit 0 is the auto-sense input
      {1, 0x12, 150, 250},     // bit 1 is the LED, added by the relay
      {1, 0x100, 150, 250},    // more than 8 bits
      {1, 0x10, 10, 250},      // too short for the fan to notice
      {1, 0x10, 2500, 250},    // held so long the keypad is blocked
      {1, 0x10, 150, -1},
      {1, 0x10, 150, 2500},
  };
  for (const auto &b : bad) {
    CHECK(r.request(200, b[0], b[1], b[2], b[3]) == RELAY_REFUSE);
    CHECK(std::string_view(r.refusal) == "bad" && r.busy == 0);
  }
  CHECK(r.request(0, 1, 0x10, 150, 250) == RELAY_REFUSE);  // seq 0 means none was sent

  // Beeps are not remembered: a repeated beep beeps again, and beeps never push a key out.
  CHECK(r.request(299, 1, 0x20, 150, 250) == RELAY_PRESS);
  r.finished(true, true, 0x01, 0xFF);
  for (uint32_t seq = 300; seq < 310; seq++) {
    CHECK(r.request(seq, 1, 0x80, 150, 250) == RELAY_PRESS);
    CHECK(r.finished(true, true, 0x01, 0xFF).seq == seq);  // still answered
  }
  CHECK(r.request(305, 1, 0x80, 150, 250) == RELAY_PRESS);
  r.finished(true, true, 0x01, 0xFF);
  CHECK(r.request(299, 1, 0x20, 150, 250) == RELAY_REPEAT);

  // Keys: the last four answers are kept.
  for (uint32_t seq = 400; seq < 404; seq++) {
    CHECK(r.request(seq, 1, 0x40, 150, 250) == RELAY_PRESS);
    r.finished(true, true, 0x01, 0xFF);
  }
  CHECK(r.find(400) && r.find(403) && !r.find(299));
  CHECK(r.request(299, 1, 0x20, 150, 250) == RELAY_PRESS);  // forgotten: a new press

  if (failures) return 1;
  std::printf("relay: all checks passed\n");
  return 0;
}
