// What the ESP32 beside a VanTurtle board does with a press request (option E,
// firmware/vanturtle-board.yaml). Plain C++ without ESPHome, so tests/test_relay.cpp can check
// it on a desktop. The other end is venus/dbus-maxxfan-bridge/vtboard.py.
#pragma once
#include <cstdint>

enum RelayAction : uint8_t {
  RELAY_PRESS,   // new press: hold the key, release, wait the gap, then call finished()
  RELAY_REPEAT,  // pressed already: send the remembered answer again, do not press again
  RELAY_WAIT,    // that very press is still going: its answer follows by itself
  RELAY_REFUSE,  // bad request, or busy with another press: answer ok=false, err=refusal
};

struct RelayAnswer {
  uint32_t seq = 0;
  bool ok = false;     // the key went down and came back up
  bool fresh = false;  // in1 / in2 were read after the press (else the bus has a problem)
  uint8_t in1 = 0xFF, in2 = 0xFF;
};

struct Relay {
  // The driver retries an unanswered key with the same seq, possibly after outages and wake
  // beeps in between. Beeps are not remembered (a second beep does no harm), so they can never
  // push that key out; a few answers are kept anyway.
  static constexpr int REMEMBER = 4;
  static constexpr int BEEP = 0x80;  // RJ45 port; bit 7 is never pressed on an RJ11 port
  RelayAnswer answers[REMEMBER];     // newest first
  RelayAnswer last;                  // answer to the press just finished
  uint32_t busy = 0;                 // seq of the press in progress, 0 when idle
  int ch = 0, key = 0, ms = 0, gap = 0;
  const char *refusal = "";

  RelayAction request(uint32_t seq, int ch_, int key_, int ms_, int gap_) {
    if (seq == 0) {
      refusal = "bad";
      return RELAY_REFUSE;
    }
    if (seq == busy) return RELAY_WAIT;
    if (find(seq) != nullptr) return RELAY_REPEAT;
    if (busy != 0) {
      refusal = "busy";
      return RELAY_REFUSE;
    }
    // Bit 0 of each port is the auto-sense input and must stay low; bit 1 is the board's
    // activity LED, which press_bits() adds. Holds beyond 2 s would block the fan's keypad.
    if ((ch_ != 1 && ch_ != 2) || key_ <= 0 || key_ > 0xFF || (key_ & 0x03) != 0 ||
        ms_ < 50 || ms_ > 2000 || gap_ < 0 || gap_ > 2000) {
      refusal = "bad";
      return RELAY_REFUSE;
    }
    busy = seq;
    ch = ch_;
    key = key_;
    ms = ms_;
    gap = gap_;
    return RELAY_PRESS;
  }

  const RelayAnswer &finished(bool ok, bool fresh, uint8_t in1, uint8_t in2) {
    last.seq = busy;
    last.ok = ok;
    last.fresh = fresh;
    last.in1 = in1;
    last.in2 = in2;
    if (key != BEEP) {
      for (int i = REMEMBER - 1; i > 0; i--) answers[i] = answers[i - 1];
      answers[0] = last;
    }
    busy = 0;
    return last;
  }

  const RelayAnswer *find(uint32_t seq) const {
    for (const auto &a : answers)
      if (seq != 0 && a.seq == seq) return &a;
    return nullptr;
  }

  uint8_t out_reg() const { return ch == 1 ? 0x02 : 0x03; }
  uint8_t press_bits() const { return static_cast<uint8_t>(key | 0x02); }
};
