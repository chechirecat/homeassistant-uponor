"""Setup, entity and write tests for the Uponor integration."""

import json

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.uponor.const import DOMAIN

ENTRY_DATA = {CONF_HOST: "192.168.1.10", CONF_NAME: "Uponor", "c1_t1": "Living"}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _sent_vars(aioclient_mock):
    """Variables posted with SetAttributes calls."""
    out = {}
    for method, url, data, headers in aioclient_mock.mock_calls:
        if headers and headers.get("x-jnap-action", "").endswith("SetAttributes"):
            for var in json.loads(data)["vars"]:
                out[var["waspVarName"]] = var["waspVarValue"]
    return out


async def test_setup_creates_entities(hass: HomeAssistant, mock_controller) -> None:
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    state = hass.states.get("climate.living")
    assert state is not None
    assert state.state == "heat"
    assert state.attributes["current_temperature"] == 21.0
    assert state.attributes["temperature"] == 21.0
    assert state.attributes["current_humidity"] == 45
    assert state.attributes["hvac_action"] == "heating"
    assert state.attributes["status"] == "OK"

    assert hass.states.get("switch.uponor_away").state == "off"
    assert hass.states.get("switch.uponor_cooling_mode").state == "off"

    # Unique IDs must stay compatible with releases <= 0.9.x.
    registry = er.async_get(hass)
    assert registry.async_get("climate.living").unique_id == "1234"
    assert registry.async_get("switch.uponor_away").unique_id == "Uponor Away"
    assert registry.async_get("switch.uponor_cooling_mode").unique_id == "Uponor Cooling Mode"


async def test_unload(hass: HomeAssistant, mock_controller) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_when_unreachable(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post("http://192.168.1.10/JNAP/", status=500)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_set_temperature(hass: HomeAssistant, mock_controller) -> None:
    await _setup(hass)
    await hass.services.async_call(
        "climate", "set_temperature",
        {"entity_id": "climate.living", "temperature": 22.5}, blocking=True,
    )
    assert _sent_vars(mock_controller) == {"C1_T1_setpoint": str(int(22.5 * 18 + 320))}
    assert hass.states.get("climate.living").attributes["temperature"] == 22.5


async def test_turn_off_and_on(hass: HomeAssistant, mock_controller) -> None:
    await _setup(hass)
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.living", "hvac_mode": "off"}, blocking=True,
    )
    assert _sent_vars(mock_controller)["C1_T1_setpoint"] == "410"
    assert hass.states.get("climate.living").state == "off"

    await hass.services.async_call(
        "climate", "turn_on", {"entity_id": "climate.living"}, blocking=True,
    )
    # Restores the setpoint stored when it was turned off.
    assert _sent_vars(mock_controller)["C1_T1_setpoint"] == "698"
    assert hass.states.get("climate.living").state == "heat"


async def test_away_switch(hass: HomeAssistant, mock_controller) -> None:
    await _setup(hass)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.uponor_away"}, blocking=True,
    )
    assert _sent_vars(mock_controller) == {"sys_forced_eco_mode": "1"}
    assert hass.states.get("switch.uponor_away").state == "on"
    assert hass.states.get("climate.living").attributes["preset_mode"] == "away"


async def test_set_variable_service(hass: HomeAssistant, mock_controller) -> None:
    await _setup(hass)
    await hass.services.async_call(
        DOMAIN, "set_variable",
        {"var_name": "sys_heat_cool_mode", "var_value": "1"}, blocking=True,
    )
    assert _sent_vars(mock_controller) == {"sys_heat_cool_mode": "1"}
    assert hass.states.get("switch.uponor_cooling_mode").state == "on"
