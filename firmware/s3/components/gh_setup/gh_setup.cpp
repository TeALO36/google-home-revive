#include "gh_setup.h"

#include <array>
#include <cstdio>
#include <map>

#include "esp_netif.h"
#include "esp_wifi.h"
#include "esphome/components/wifi/wifi_component.h"
#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"
#include "mbedtls/sha256.h"
#include "setup_page.h"

namespace esphome {
namespace gh_setup {

static const char *const TAG = "gh_setup";
static const size_t MIN_ADMIN_LENGTH = 8;
static const size_t MIN_WPA_KEY_LENGTH = 8;
static const size_t MAX_SSID_LENGTH = 32;

static std::string json_escape(const std::string &text) {
  std::string out;
  out.reserve(text.size() + 2);
  for (const char c : text) {
    if (c == '"' || c == '\\') {
      out += '\\';
      out += c;
    } else if (static_cast<unsigned char>(c) < 0x20) {
      char code[7];
      snprintf(code, sizeof(code), "\\u%04x", static_cast<unsigned>(static_cast<unsigned char>(c)));
      out += code;
    } else {
      out += c;
    }
  }
  return out;
}

static const char *state_name(TestState state) {
  switch (state) {
    case TestState::CONNECTING:
      return "connecting";
    case TestState::CONNECTED:
      return "connected";
    case TestState::WRONG_KEY:
      return "wrong_key";
    case TestState::NOT_FOUND:
      return "not_found";
    case TestState::UNSUPPORTED:
      return "unsupported";
    case TestState::FAILED:
      return "failed";
    default:
      return "idle";
  }
}

// ESP-IDF disconnect reason -> page state; IDLE means "keep waiting, ESPHome retries"
static TestState state_from_reason(uint16_t reason) {
  switch (reason) {
    case WIFI_REASON_AUTH_FAIL:
    case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_MIC_FAILURE:
      return TestState::WRONG_KEY;
    case WIFI_REASON_NO_AP_FOUND:
      return TestState::NOT_FOUND;
    case WIFI_REASON_NO_AP_FOUND_W_COMPATIBLE_SECURITY:
    case WIFI_REASON_NO_AP_FOUND_IN_AUTHMODE_THRESHOLD:
      return TestState::UNSUPPORTED;
    default:
      return TestState::IDLE;
  }
}

void GhSetup::setup() {
  this->pref_ = global_preferences->make_preference<StoredSettings>(fnv1_hash("gh_setup"), true);
  if (!this->pref_.load(&this->settings_)) {
    this->settings_ = StoredSettings{};
  }
  this->settings_.admin_hash[sizeof(this->settings_.admin_hash) - 1] = '\0';
  // the page is reachable on the access point and on the home network, it protects itself with the admin password
  this->base_->add_handler_without_auth(this);
}

// Runs once from loop(): Wi-Fi has created the event loop and the network interfaces by then.
void GhSetup::start_() {
  this->started_ = true;
  esp_err_t err = esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, &GhSetup::on_wifi_event, this);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Wi-Fi event handler registration failed: %s", esp_err_to_name(err));
  }
  this->base_->init();  // keeps the HTTP server running after captive_portal stops it
  ESP_LOGI(TAG, "Setup page ready (admin password %s)", this->settings_.admin_hash[0] ? "set" : "not set yet");
}

void GhSetup::on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data) {
  if (base != WIFI_EVENT || id != WIFI_EVENT_STA_DISCONNECTED || arg == nullptr || data == nullptr) {
    return;
  }
  auto *self = static_cast<GhSetup *>(arg);
  self->last_reason_.store(static_cast<const wifi_event_sta_disconnected_t *>(data)->reason);
}

void GhSetup::loop() {
  if (!this->started_) {
    this->start_();
  }
  if (this->state_ == TestState::CONNECTING) {
    this->update_test_();
  }
}

void GhSetup::update_test_() {
  if (wifi::global_wifi_component->is_connected() && !this->station_ip().empty()) {
    this->state_ = TestState::CONNECTED;
    this->announce_pending_ = true;
    ESP_LOGI(TAG, "Key test passed, IP %s", this->station_ip().c_str());
    return;
  }
  const TestState from_reason = state_from_reason(this->last_reason_.load());
  if (from_reason != TestState::IDLE) {
    this->state_ = from_reason;
    ESP_LOGW(TAG, "Key test failed: %s (reason %u)", state_name(from_reason), this->last_reason_.load());
  } else if (millis() - this->test_started_ms_ > this->test_timeout_ms_) {
    this->state_ = TestState::FAILED;
    ESP_LOGW(TAG, "Key test timed out");
  }
}

static std::string request_url(AsyncWebServerRequest *request) {
  char buffer[AsyncWebServerRequest::URL_BUF_SIZE];
  return request->url_to(buffer).str();
}

static std::string interface_ip(const char *key) {
  esp_netif_t *netif = esp_netif_get_handle_from_ifkey(key);
  esp_netif_ip_info_t info{};
  if (netif == nullptr || esp_netif_get_ip_info(netif, &info) != ESP_OK || info.ip.addr == 0) {
    return "";
  }
  char text[16];
  snprintf(text, sizeof(text), IPSTR, IP2STR(&info.ip));
  return text;
}

// On the access point every GET is ours (phones probe /generate_204 etc. and get sent to the page).
bool GhSetup::canHandle(AsyncWebServerRequest *request) const {
  if (request->method() != HTTP_GET) {
    return false;
  }
  if (this->ap_active()) {
    return true;
  }
  const std::string url = request_url(request);
  return url == "/" || url == "/index.html" || url.rfind("/gh/", 0) == 0;
}

void GhSetup::handleRequest(AsyncWebServerRequest *request) {
  const std::string url = request_url(request);
  if (url == "/gh/scan") {
    this->handle_scan_(request);
  } else if (url == "/gh/connect") {
    this->handle_connect_(request);
  } else if (url == "/gh/status") {
    this->handle_status_(request);
  } else if (url == "/" || url == "/index.html") {
    request->send(200, "text/html", SETUP_PAGE);
  } else {
    request->redirect("http://" + interface_ip("WIFI_AP_DEF") + "/");
  }
}

void GhSetup::handle_scan_(AsyncWebServerRequest *request) {
  std::map<std::string, std::pair<int8_t, bool>> best;  // ssid -> (rssi, secured)
  for (const auto &scan : wifi::global_wifi_component->get_scan_result()) {
    const std::string ssid = scan.get_ssid().str();
    if (scan.get_is_hidden() || ssid.empty()) {
      continue;
    }
    auto found = best.find(ssid);
    if (found == best.end() || found->second.first < scan.get_rssi()) {
      best[ssid] = {scan.get_rssi(), scan.get_with_auth()};
    }
  }
  std::string body = "[";
  for (const auto &entry : best) {
    if (body.size() > 1) {
      body += ',';
    }
    body += "{\"ssid\":\"" + json_escape(entry.first) + "\",\"rssi\":" + std::to_string(entry.second.first) +
            ",\"secure\":" + (entry.second.second ? "true" : "false") + "}";
  }
  body += "]";
  request->send(200, "application/json", body.c_str());
}

void GhSetup::handle_connect_(AsyncWebServerRequest *request) {
  const std::string ssid = request->arg("ssid");
  const std::string key = request->arg("key");
  std::string error;
  if (ssid.empty() || ssid.size() > MAX_SSID_LENGTH) {
    error = "Nom de réseau invalide.";
  } else if (!key.empty() && key.size() < MIN_WPA_KEY_LENGTH) {
    error = "La clé Wi-Fi doit faire au moins 8 caractères (le WEP n'est pas pris en charge).";
  } else {
    this->check_admin_(request->arg("admin"), request->arg("confirm"), error);
  }
  if (!error.empty()) {
    request->send(200, "application/json", ("{\"ok\":false,\"error\":\"" + json_escape(error) + "\"}").c_str());
    return;
  }
  this->last_reason_.store(0);
  this->test_started_ms_ = millis();
  this->state_ = TestState::CONNECTING;
  ESP_LOGI(TAG, "Testing Wi-Fi network '%s'", ssid.c_str());
  wifi::global_wifi_component->save_wifi_sta(ssid, key);
  request->send(200, "application/json", "{\"ok\":true}");
}

void GhSetup::handle_status_(AsyncWebServerRequest *request) {
  const std::string body = std::string("{\"admin_set\":") + (this->settings_.admin_hash[0] ? "true" : "false") +
                           ",\"state\":\"" + state_name(this->state_) + "\",\"ip\":\"" + this->station_ip() + "\"}";
  request->send(200, "application/json", body.c_str());
}

// First use: the password is created (twice, 8+ characters). Afterwards it must match the stored hash.
bool GhSetup::check_admin_(const std::string &password, const std::string &confirm, std::string &error) {
  if (this->settings_.admin_hash[0] == '\0') {
    if (password.size() < MIN_ADMIN_LENGTH) {
      error = "Le mot de passe administrateur doit faire au moins 8 caractères.";
      return false;
    }
    if (password != confirm) {
      error = "Les deux mots de passe administrateur ne correspondent pas.";
      return false;
    }
    snprintf(this->settings_.admin_hash, sizeof(this->settings_.admin_hash), "%s", this->hash_(password).c_str());
    this->save_settings_();
    ESP_LOGI(TAG, "Admin password created");
    return true;
  }
  if (this->hash_(password) != this->settings_.admin_hash) {
    error = "Mot de passe administrateur incorrect.";
    return false;
  }
  return true;
}

std::string GhSetup::hash_(const std::string &password) const {
  uint8_t mac[6];
  get_mac_address_raw(mac);
  std::string salted = password;
  salted.append(reinterpret_cast<const char *>(mac), sizeof(mac));
  std::array<uint8_t, 32> digest{};
  if (mbedtls_sha256(reinterpret_cast<const unsigned char *>(salted.data()), salted.size(), digest.data(), 0) != 0) {
    ESP_LOGE(TAG, "SHA-256 failed");
    return "";
  }
  return format_hex(digest);
}

void GhSetup::save_settings_() {
  if (!this->pref_.save(&this->settings_) || !global_preferences->sync()) {
    ESP_LOGE(TAG, "Saving settings to flash failed");
  }
}

bool GhSetup::ap_active() const {
  wifi_mode_t mode = WIFI_MODE_NULL;
  if (esp_wifi_get_mode(&mode) != ESP_OK) {
    return false;
  }
  const bool ap = mode == WIFI_MODE_AP || mode == WIFI_MODE_APSTA;
  return ap && !wifi::global_wifi_component->is_connected();
}

bool GhSetup::take_announce_request() {
  if (!wifi::global_wifi_component->is_connected()) {
    return false;
  }
  if (!this->announce_pending_ && this->settings_.ip_announced) {
    return false;
  }
  this->announce_pending_ = false;
  if (!this->settings_.ip_announced) {
    this->settings_.ip_announced = true;
    this->save_settings_();
  }
  return true;
}

std::string GhSetup::station_ip() const { return interface_ip("WIFI_STA_DEF"); }

}  // namespace gh_setup
}  // namespace esphome
