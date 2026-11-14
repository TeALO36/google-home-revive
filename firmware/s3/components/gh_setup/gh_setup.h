#pragma once

#include <atomic>
#include <cstdint>
#include <string>

#include "esp_event.h"
#include "esphome/components/web_server_base/web_server_base.h"
#include "esphome/core/component.h"
#include "esphome/core/preferences.h"

namespace esphome {
namespace gh_setup {

// Result of the last key test started from the setup page.
enum class TestState : uint8_t { IDLE, CONNECTING, CONNECTED, WRONG_KEY, NOT_FOUND, UNSUPPORTED, FAILED };

struct StoredSettings {
  char admin_hash[65];  // hex SHA-256 of (password + MAC), empty string = no admin password yet
  bool ip_announced;    // the IP address was spoken at least once
};

class GhSetup : public Component, public AsyncWebHandler {
 public:
  explicit GhSetup(web_server_base::WebServerBase *base) : base_(base) {}

  void setup() override;
  void loop() override;
  // before captive_portal (WIFI + 1): this handler is registered first and answers every page
  float get_setup_priority() const override { return setup_priority::WIFI + 2.0f; }
  void set_test_timeout(uint32_t timeout_ms) { this->test_timeout_ms_ = timeout_ms; }

  bool canHandle(AsyncWebServerRequest *request) const override;
  void handleRequest(AsyncWebServerRequest *request) override;
  bool isRequestHandlerTrivial() const override { return false; }

  // true while the fallback access point is up (no Wi-Fi network joined)
  bool ap_active() const;
  // true once after a successful test from the page, or on the very first connection: speak the IP address
  bool take_announce_request();
  // IPv4 address of the station interface, "" when not connected
  std::string station_ip() const;

 protected:
  static void on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data);
  void start_();
  void handle_scan_(AsyncWebServerRequest *request);
  void handle_connect_(AsyncWebServerRequest *request);
  void handle_status_(AsyncWebServerRequest *request);
  bool check_admin_(const std::string &password, const std::string &confirm, std::string &error);
  std::string hash_(const std::string &password) const;
  void update_test_();
  void save_settings_();

  web_server_base::WebServerBase *base_;
  ESPPreferenceObject pref_;
  StoredSettings settings_{};
  TestState state_{TestState::IDLE};
  std::atomic<uint16_t> last_reason_{0};
  uint32_t test_started_ms_{0};
  uint32_t test_timeout_ms_{25000};
  bool announce_pending_{false};
  bool started_{false};
};

}  // namespace gh_setup
}  // namespace esphome
