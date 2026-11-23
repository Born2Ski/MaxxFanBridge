// Desktop test of the packet encoder/decoder.
//   c++ -std=c++17 -o /dev/null ... ; see tests/run.sh
#include <cassert>
#include <cstdio>
#include "../firmware/maxxfan_packet.h"

int main() {
  uint8_t p[MAXX_PACKET_LEN];

  // Fan on, 60 %, exhaust, lid open, manual, 24 °C
  MaxxState s{true, 60, true, true, false, 24};
  maxx_encode(s, p);
  assert(p[0] == 0x5A && p[9] == 0xCC);
  assert(p[10] == (0x01 | 0x04 | 0x08));
  assert(p[11] == 60);
  assert(p[12] == 75);                       // trunc(24 * 1.8) + 32
  assert(p[13] == 0xFF && p[14] == 0x23);
  assert(p[15] == (uint8_t) (p[10] ^ p[11] ^ p[12] ^ p[13] ^ p[14]));

  // Ceiling-fan mode (on, lid closed) and auto mode both set the "special" bit
  maxx_encode(MaxxState{true, 30, false, false, false, 20}, p);
  assert(p[10] == (0x01 | 0x02));
  maxx_encode(MaxxState{false, 30, true, false, true, 20}, p);
  assert(p[10] == (0x02 | 0x04 | 0x10));

  // Every state survives a round trip, also with noise bytes in front
  for (int on = 0; on < 2; on++)
    for (int ex = 0; ex < 2; ex++)
      for (int lid = 0; lid < 2; lid++)
        for (int au = 0; au < 2; au++)
          for (int speed = 10; speed <= 100; speed += 10)
            for (int sp = -2; sp <= 37; sp++) {
              MaxxState in{(bool) on, speed, (bool) ex, (bool) lid, (bool) au, sp}, out{};
              uint8_t buf[3 + MAXX_PACKET_LEN] = {0x00, 0x5A, 0xFF};
              maxx_encode(in, buf + 3);
              assert(maxx_decode(buf, sizeof(buf), &out));
              assert(out.on == in.on && out.exhaust == in.exhaust && out.lid_open == in.lid_open);
              assert(out.auto_mode == in.auto_mode && out.speed == in.speed);
              assert(out.setpoint_c == in.setpoint_c);
            }

  // Corruption and truncation are rejected
  MaxxState out{};
  maxx_encode(s, p);
  p[11] ^= 0x10;
  assert(!maxx_decode(p, MAXX_PACKET_LEN, &out));
  maxx_encode(s, p);
  assert(!maxx_decode(p, MAXX_PACKET_LEN - 1, &out));

  puts("packet: all checks passed");
  return 0;
}
