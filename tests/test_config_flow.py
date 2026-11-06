"""Config flow tests."""

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.uponor.const import DOMAIN


async def test_flow_success(hass: HomeAssistant, mock_controller) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.10", CONF_NAME: "Uponor"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "rooms"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"c1_t1": "Living"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "192.168.1.10", CONF_NAME: "Uponor", "c1_t1": "Living"}


async def test_flow_cannot_connect(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post("http://192.168.1.10/JNAP/", status=500)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.10", CONF_NAME: "Uponor"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_host"}
