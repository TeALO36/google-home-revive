"""GH-Revive setup portal: admin password, Wi-Fi network choice and live key test, served on the fallback AP.

Works next to ESPHome's `captive_portal` (which keeps the DNS redirection): this handler is registered first, so
"/" and "/gh/*" are answered here.
"""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import web_server_base
from esphome.components.web_server_base import CONF_WEB_SERVER_BASE_ID
from esphome.const import CONF_ID

DEPENDENCIES = ["wifi"]
AUTO_LOAD = ["web_server_base"]

gh_setup_ns = cg.esphome_ns.namespace("gh_setup")
GhSetup = gh_setup_ns.class_("GhSetup", cg.Component)

CONF_TEST_TIMEOUT = "test_timeout"

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(GhSetup),
            cv.GenerateID(CONF_WEB_SERVER_BASE_ID): cv.use_id(web_server_base.WebServerBase),
            cv.Optional(CONF_TEST_TIMEOUT, default="25s"): cv.positive_time_period_milliseconds,
        }
    ).extend(cv.COMPONENT_SCHEMA),
    cv.only_on_esp32,
)


async def to_code(config):
    base = await cg.get_variable(config[CONF_WEB_SERVER_BASE_ID])
    var = cg.new_Pvariable(config[CONF_ID], base)
    await cg.register_component(var, config)
    cg.add(var.set_test_timeout(config[CONF_TEST_TIMEOUT]))
