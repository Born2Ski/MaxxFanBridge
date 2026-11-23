// ESPHome side of the VanTurtle relay (option E, firmware/vanturtle-board.yaml): register
// access to the board's TCA9555 and the answer message. The decisions are in vanturtle_relay.h.
#pragma once
#include "esphome/components/i2c/i2c_bus.h"
#include "esphome/components/mqtt/mqtt_client.h"
#include "vanturtle_relay.h"

// The relay's memory. A function-local static, because ESPHome declares its globals before
// it includes this file.
inline Relay &vt_relay() {
  static Relay relay;
  return relay;
}

// Registers of the board, per port: input 0x00 / 0x01, output 0x02 / 0x03, direction 0x06 / 0x07.
inline bool vt_write(esphome::i2c::I2CBus *bus, uint8_t address, uint8_t reg, uint8_t value) {
  const uint8_t data[2] = {reg, value};
  return bus->write(address, data, 2) == esphome::i2c::ERROR_OK;
}

inline bool vt_read(esphome::i2c::I2CBus *bus, uint8_t address, uint8_t reg, uint8_t *value) {
  return bus->write_readv(address, &reg, 1, value, 1) == esphome::i2c::ERROR_OK;
}

// Outputs low first, then directions: the chip powers up with its output latches high, so
// making the pins outputs first would press every key at once for a moment. This also
// releases a key left held by a reset in the middle of a press.
inline bool vt_prepare(esphome::i2c::I2CBus *bus, uint8_t address) {
  return vt_write(bus, address, 0x02, 0x00) && vt_write(bus, address, 0x03, 0x00) &&
         vt_write(bus, address, 0x06, 0x01) && vt_write(bus, address, 0x07, 0x01);
}

inline void vt_answer(const std::string &topic, const RelayAnswer &a, const char *err) {
  esphome::mqtt::global_mqtt_client->publish_json(topic, [&](JsonObject root) {
    root["seq"] = a.seq;
    root["ok"] = a.ok;
    if (!a.ok) root["err"] = err;
    root["i2c"] = a.fresh;
    if (a.fresh) {
      root["in1"] = a.in1;
      root["in2"] = a.in2;
    }
  });
}
