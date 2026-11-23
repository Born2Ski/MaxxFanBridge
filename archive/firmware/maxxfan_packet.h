// MaxxFan infrared remote packet: 16 bytes, sent as 1200 baud 8N2 serial (on a 38 kHz carrier
// when in the air). Layout from the dbus-maxxfan project; see archive/hardware/option-a-tap.md.
#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>

struct MaxxState {
  bool on;
  int speed;       // 10..100, steps of 10
  bool exhaust;    // false = intake
  bool lid_open;
  bool auto_mode;
  int setpoint_c;  // -2..37
};

static const size_t MAXX_PACKET_LEN = 16;
static const uint8_t MAXX_PREAMBLE[10] = {0x5A, 0xA5, 0x80, 0x7F, 0x40, 0xBF, 0x20, 0xDF, 0x10, 0xCC};

inline void maxx_encode(const MaxxState &s, uint8_t out[MAXX_PACKET_LEN]) {
  memcpy(out, MAXX_PREAMBLE, sizeof(MAXX_PREAMBLE));
  uint8_t bits = 0;
  if (s.on) bits |= 0x01;
  if (s.auto_mode || (s.on && !s.lid_open)) bits |= 0x02;  // "special": auto, or ceiling-fan mode
  if (s.exhaust) bits |= 0x04;
  if (s.lid_open) bits |= 0x08;
  if (s.auto_mode) bits |= 0x10;
  out[10] = bits;
  out[11] = (uint8_t) s.speed;
  out[12] = (uint8_t) ((int) (s.setpoint_c * 1.8f) + 32);  // truncation, as the remote does
  out[13] = 0xFF;
  out[14] = 0x23;
  out[15] = out[10] ^ out[11] ^ out[12] ^ out[13] ^ out[14];
}

// Finds a valid packet anywhere in buf. Returns true and fills *s on success.
inline bool maxx_decode(const uint8_t *buf, size_t len, MaxxState *s) {
  for (size_t i = 0; i + MAXX_PACKET_LEN <= len; i++) {
    const uint8_t *p = buf + i;
    if (memcmp(p, MAXX_PREAMBLE, sizeof(MAXX_PREAMBLE)) != 0) continue;
    if ((uint8_t) (p[10] ^ p[11] ^ p[12] ^ p[13] ^ p[14]) != p[15]) continue;
    if (p[11] > 100) continue;
    s->on = p[10] & 0x01;
    s->exhaust = p[10] & 0x04;
    s->lid_open = p[10] & 0x08;
    s->auto_mode = p[10] & 0x10;
    s->speed = p[11] < 10 ? 10 : (p[11] / 10) * 10;
    s->setpoint_c = (int) lroundf((p[12] - 32) / 1.8f);
    return true;
  }
  return false;
}
