// GH-Revive Bluetooth co-processor: A2DP sink, audio out as I2S master towards the ESP32-S3.
//
// Wiring (main board): I2S BCLK IO18, LRCK IO19, DATA IO21 -> S3 IO38/39/40; status IO22 -> S3 IO21;
// UART0 (115200) <-> S3 IO41/42. Line protocol, one command per line:
//   PAIR        become discoverable         -> "PAIRING"
//   HIDE        stop being discoverable     -> "HIDDEN"
//   DISCONNECT  drop the current source     -> "DISCONNECTED" (from the connection callback)
//   VOL <0-127> A2DP volume                 -> "VOL <n>"
//   STATUS      current state               -> "CONNECTED" / "DISCONNECTED"
// Unknown commands answer "ERR <command>".
#include <Arduino.h>

#include "AudioTools.h"
#include "BluetoothA2DPSink.h"

namespace {

constexpr int kPinBclk = 18;
constexpr int kPinLrck = 19;
constexpr int kPinData = 21;
constexpr int kPinConnected = 22;
constexpr uint32_t kBaud = 115200;
constexpr size_t kMaxLine = 32;
constexpr char kDeviceName[] = "GH Revive";

I2SStream i2s;
BluetoothA2DPSink sink(i2s);
String pending;

void on_connection(esp_a2d_connection_state_t state, void * /*context*/) {
  const bool connected = state == ESP_A2D_CONNECTION_STATE_CONNECTED;
  digitalWrite(kPinConnected, connected ? HIGH : LOW);
  if (connected) {
    Serial.println("CONNECTED");
  } else if (state == ESP_A2D_CONNECTION_STATE_DISCONNECTED) {
    Serial.println("DISCONNECTED");
  }
}

void set_volume(const String &argument) {
  const long volume = argument.toInt();
  if (argument.isEmpty() || volume < 0 || volume > 127) {
    Serial.println("ERR VOL");
    return;
  }
  sink.set_volume(static_cast<uint8_t>(volume));
  Serial.printf("VOL %ld\n", volume);
}

void handle_command(const String &command) {
  if (command == "PAIR") {
    sink.set_discoverability(ESP_BT_GENERAL_DISCOVERABLE);
    Serial.println("PAIRING");
  } else if (command == "HIDE") {
    sink.set_discoverability(ESP_BT_NON_DISCOVERABLE);
    Serial.println("HIDDEN");
  } else if (command == "DISCONNECT") {
    sink.disconnect();
  } else if (command.startsWith("VOL ")) {
    set_volume(command.substring(4));
  } else if (command == "STATUS") {
    Serial.println(sink.is_connected() ? "CONNECTED" : "DISCONNECTED");
  } else {
    Serial.printf("ERR %s\n", command.c_str());
  }
}

void read_commands() {
  while (Serial.available() > 0) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\n' || c == '\r') {
      pending.trim();
      if (!pending.isEmpty()) {
        handle_command(pending);
      }
      pending = "";
    } else if (pending.length() < kMaxLine) {
      pending += c;
    }
  }
}

void start_i2s() {
  auto config = i2s.defaultConfig(TX_MODE);
  config.pin_bck = kPinBclk;
  config.pin_ws = kPinLrck;
  config.pin_data = kPinData;
  config.sample_rate = 44100;  // updated by the sink to the rate negotiated with the source
  config.bits_per_sample = 16;
  config.channels = 2;
  if (!i2s.begin(config)) {
    Serial.println("ERR I2S");
  }
}

}  // namespace

void setup() {
  Serial.begin(kBaud);
  pinMode(kPinConnected, OUTPUT);
  digitalWrite(kPinConnected, LOW);
  start_i2s();
  sink.set_on_connection_state_changed(on_connection);
  sink.set_auto_reconnect(true);
  sink.start(kDeviceName);
  Serial.println("READY");
}

void loop() {
  read_commands();
  delay(5);
}
