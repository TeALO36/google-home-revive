// GH-Revive flashing bridge, runs on the ESP32-S3: USB-C (TinyUSB CDC) <-> UART1 (IO41 / IO42) to the Bluetooth
// module. esptool's DTR / RTS reset sequence on the USB port is replayed on the module's EN (S3 IO2) and BOOT
// (S3 IO1), like the classic two-transistor auto-reset circuit, and the USB baud rate is applied to UART1:
//   pio run -e bt -t upload --upload-port <COMx>
// Flash the main firmware back on the S3 afterwards (hold BOOT while plugging the USB-C, then esphome run).
#include <Arduino.h>
#include <USB.h>
#include <USBCDC.h>

namespace {

constexpr int kPinBtRx = 41;  // S3 receives the module's TXD0
constexpr int kPinBtTx = 42;  // S3 drives the module's RXD0
constexpr int kPinBtEn = 2;
constexpr int kPinBtBoot = 1;
constexpr uint32_t kDefaultBaud = 115200;
constexpr size_t kChunk = 256;

USBCDC usb_serial;
HardwareSerial bt_serial(1);

// Auto-reset truth table: (DTR, RTS) = (0, 1) -> EN low, (1, 0) -> BOOT low, otherwise both released.
void apply_line_state(bool dtr, bool rts) {
  digitalWrite(kPinBtEn, (rts && !dtr) ? LOW : HIGH);
  digitalWrite(kPinBtBoot, (dtr && !rts) ? LOW : HIGH);
}

void on_usb_event(void *, esp_event_base_t base, int32_t id, void *data) {
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
  bt_serial.setRxBufferSize(4096);
  bt_serial.begin(kDefaultBaud, SERIAL_8N1, kPinBtRx, kPinBtTx);
  usb_serial.onEvent(on_usb_event);
  usb_serial.begin(kDefaultBaud);
  USB.productName("GH-Revive BT bridge");
  USB.begin();
}

void loop() {
  copy(usb_serial, bt_serial);
  copy(bt_serial, usb_serial);
}
