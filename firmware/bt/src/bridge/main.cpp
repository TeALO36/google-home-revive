// GH-Revive flashing bridge, runs on the ESP32-S3: native USB CDC <-> UART1 to the Bluetooth module.
//
// esptool drives DTR/RTS like on a classic USB-UART adapter; they are mapped to the module's EN (S3 IO2) and
// BOOT (S3 IO1) lines with the usual auto-reset truth table, so `pio run -e bt -t upload` works unchanged.
// The baud rate requested by the host is applied to UART1 on the fly.
#include <Arduino.h>

#include "USB.h"

namespace {

constexpr int kPinBtRx = 41;  // S3 receives the module's TXD0
constexpr int kPinBtTx = 42;  // S3 drives the module's RXD0
constexpr int kPinBtEn = 2;
constexpr int kPinBtBoot = 1;
constexpr uint32_t kDefaultBaud = 115200;
constexpr size_t kChunk = 256;

USBCDC usb_serial;
HardwareSerial bt_serial(1);

// DTR RTS -> EN BOOT: 1 1 -> 1 1, 0 0 -> 1 1, 1 0 -> 1 0, 0 1 -> 0 1
void apply_line_state(bool dtr, bool rts) {
  digitalWrite(kPinBtEn, (rts && !dtr) ? LOW : HIGH);
  digitalWrite(kPinBtBoot, (dtr && !rts) ? LOW : HIGH);
}

void on_usb_event(void * /*arg*/, esp_event_base_t base, int32_t id, void *data) {
  if (base != ARDUINO_USB_CDC_EVENTS || data == nullptr) {
    return;
  }
  const auto *event = static_cast<const arduino_usb_cdc_event_data_t *>(data);
  if (id == ARDUINO_USB_CDC_LINE_STATE_EVENT) {
    apply_line_state(event->line_state.dtr, event->line_state.rts);
  } else if (id == ARDUINO_USB_CDC_LINE_CODING_EVENT && event->line_coding.bit_rate > 0) {
    bt_serial.updateBaudRate(event->line_coding.bit_rate);
  }
}

void copy(Stream &from, Stream &to) {
  uint8_t buffer[kChunk];
  const int available = from.available();
  if (available <= 0) {
    return;
  }
  const size_t count = from.readBytes(buffer, min(static_cast<size_t>(available), kChunk));
  to.write(buffer, count);
}

}  // namespace

void setup() {
  pinMode(kPinBtEn, OUTPUT);
  pinMode(kPinBtBoot, OUTPUT);
  apply_line_state(false, false);
  bt_serial.begin(kDefaultBaud, SERIAL_8N1, kPinBtRx, kPinBtTx);
  usb_serial.onEvent(on_usb_event);
  usb_serial.begin();
  USB.productName("GH-Revive BT bridge");
  USB.begin();
}

void loop() {
  copy(usb_serial, bt_serial);
  copy(bt_serial, usb_serial);
}
