"""Uponor Smatrix Pulse integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .api import UponorApiError, UponorJnapClient
from .const import (
    DOMAIN,
    SCAN_INTERVAL,
    STORAGE_KEY,
    STORAGE_VERSION,
    STATUS_OK,
    STATUS_ERROR_BATTERY,
    STATUS_ERROR_VALVE,
    STATUS_ERROR_GENERAL,
    STATUS_ERROR_AIR_SENSOR,
    STATUS_ERROR_EXT_SENSOR,
    STATUS_ERROR_RH_SENSOR,
    STATUS_ERROR_RF_SENSOR,
    STATUS_ERROR_TAMPER,
    STATUS_ERROR_TOO_HIGH_TEMP,
    TOO_HIGH_TEMP_LIMIT,
    TOO_LOW_HUMIDITY_LIMIT,
    DEFAULT_TEMP
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SWITCH]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SET_VARIABLE = "set_variable"
SERVICE_SET_VARIABLE_SCHEMA = vol.Schema(
    {
        vol.Required("var_name"): cv.string,
        vol.Required("var_value"): cv.string,
    }
)


@dataclass
class UponorRuntimeData:
    """Objects shared by the platforms of one config entry."""

    coordinator: UponorCoordinator
    state_proxy: UponorStateProxy
    thermostats: list[str]


type UponorConfigEntry = ConfigEntry[UponorRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-wide services."""

    async def handle_set_variable(call: ServiceCall) -> None:
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if not entries:
            raise ServiceValidationError("No loaded Uponor config entry")
        await entries[0].runtime_data.state_proxy.async_set_variable(
            call.data["var_name"], call.data["var_value"]
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_VARIABLE, handle_set_variable, schema=SERVICE_SET_VARIABLE_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: UponorConfigEntry) -> bool:
    client = UponorJnapClient(async_get_clientsession(hass), config_entry.data[CONF_HOST])
    coordinator = UponorCoordinator(hass, config_entry, client)
    # Raises ConfigEntryNotReady on failure, so HA retries setup later.
    await coordinator.async_config_entry_first_refresh()

    state_proxy = UponorStateProxy(
        hass, client, coordinator, Store(hass, STORAGE_VERSION, STORAGE_KEY)
    )
    config_entry.runtime_data = UponorRuntimeData(
        coordinator=coordinator,
        state_proxy=state_proxy,
        thermostats=state_proxy.get_active_thermostats(),
    )

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    config_entry.async_on_unload(config_entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: UponorConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: UponorConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)


class UponorCoordinator(DataUpdateCoordinator[dict[str, str]]):
    """Polls the controller for all variables."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, client: UponorJnapClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.last_update = None

    async def _async_update_data(self) -> dict[str, str]:
        try:
            data = await self.client.get_data()
        except UponorApiError as err:
            raise UpdateFailed(str(err)) from err
        self.last_update = dt_util.now()
        return data


class UponorStateProxy:
    """Translates raw controller variables into thermostat state."""

    def __init__(self, hass, client, coordinator, store):
        self._hass = hass
        self._client = client
        self._coordinator = coordinator
        self._store = store
        self._storage_data = {}

    @property
    def _data(self) -> dict[str, str]:
        return self._coordinator.data

    # Thermostats config

    def get_active_thermostats(self):
        active = []
        for c in range(1, 5):
            var = 'sys_controller_' + str(c) + '_presence'
            if var in self._data and self._data[var] != "1":
                continue
            for i in range(1, 13):
                var = 'C' + str(c) + '_thermostat_' + str(i) + '_presence'
                if var in self._data and self._data[var] == "1":
                    active.append('C' + str(c) + '_T' + str(i))
        return active

    def get_room_name(self, thermostat):
        var = 'cust_' + thermostat + '_name'
        if var in self._data:
            return self._data[var]
        return thermostat

    def get_thermostat_id(self, thermostat):
        var = thermostat.replace('T', 'thermostat') + '_id'
        if var in self._data:
            return self._data[var]

    def get_model(self):
        var = 'cust_SW_version_update'
        if var in self._data:
            return self._data[var].split('_')[0]
        return '-'

    def get_version(self, thermostat):
        var = thermostat[0:3] + 'sw_version'
        if var in self._data:
            return self._data[var].split('_')[0]

    # Temperatures & humidity

    def get_temperature(self, thermostat):
        var = thermostat + '_room_temperature'
        if var in self._data and int(self._data[var]) <= TOO_HIGH_TEMP_LIMIT:
            return round((int(self._data[var]) - 320) / 18, 1)

    def get_min_limit(self, thermostat):
        var = thermostat + '_minimum_setpoint'
        if var in self._data:
            return round((int(self._data[var]) - 320) / 18, 1)

    def get_max_limit(self, thermostat):
        var = thermostat + '_maximum_setpoint'
        if var in self._data:
            return round((int(self._data[var]) - 320) / 18, 1)

    def get_humidity(self, thermostat):
        var = thermostat + '_rh'
        if var in self._data and int(self._data[var]) >= TOO_LOW_HUMIDITY_LIMIT:
            return int(self._data[var])

    # Temperature setpoint

    def get_setpoint(self, thermostat):
        var = thermostat + '_setpoint'
        if var in self._data:
            temp = math.floor((int(self._data[var]) - 320) / 1.8) / 10
            return math.floor((int(self._data[var]) - self.get_active_setback(thermostat, temp) - 320) / 1.8) / 10

    def get_active_setback(self, thermostat, temp):
        if temp == self.get_min_limit(thermostat) or temp == self.get_max_limit(thermostat):
            return 0

        cool_setback = 0
        var_cool_setback = 'sys_heat_cool_offset'
        if var_cool_setback in self._data and self.is_cool_enabled():
            cool_setback = int(self._data[var_cool_setback]) * -1

        eco_setback = 0
        var_eco_setback = thermostat + '_eco_offset'
        mode = -1 if self.is_cool_enabled() else 1
        if var_eco_setback in self._data and (self.is_eco(thermostat) or self.is_away()):
            eco_setback = int(self._data[var_eco_setback]) * mode

        return cool_setback + eco_setback

    # State

    def is_on(self, thermostat):
        """Uponor has no real 'off'; off means setpoint parked at the min/max limit."""
        temp = self.get_setpoint(thermostat)
        if temp is None:
            return True
        if self.is_cool_enabled():
            max_temp = self.get_max_limit(thermostat)
            return max_temp is None or temp < max_temp
        min_temp = self.get_min_limit(thermostat)
        return min_temp is None or temp > min_temp

    def is_active(self, thermostat):
        var = thermostat + '_stat_cb_actuator'
        if var in self._data:
            return self._data[var] == "1"

    def get_pwm(self, thermostat):
        var = thermostat + '_ufh_pwm_output'
        if var in self._data:
            return int(self._data[var])

    def get_status(self, thermostat):
        var = thermostat + '_stat_battery_error'
        if var in self._data and self._data[var] == "1":
            return STATUS_ERROR_BATTERY
        var = thermostat + '_stat_valve_position_err'
        if var in self._data and self._data[var] == "1":
            return STATUS_ERROR_VALVE
        var = thermostat[0:3] + 'stat_general_system_alarm'
        if var in self._data and self._data[var] == "1":
            return STATUS_ERROR_GENERAL
        var = thermostat + '_stat_air_sensor_error'
        if var in self._data and self._data[var] == "1":
            return STATUS_ERROR_AIR_SENSOR
        var = thermostat + '_stat_external_sensor_err'
        if var in self._data and self._data[var] == "1":
            return STATUS_ERROR_EXT_SENSOR
        var = thermostat + '_stat_rh_sensor_error'
        if var in self._data and self._data[var] == "1":
            return STATUS_ERROR_RH_SENSOR
        var = thermostat + '_stat_rf_error'
        if var in self._data and self._data[var] == "1":
            return STATUS_ERROR_RF_SENSOR
        var = thermostat + '_stat_tamper_alarm'
        if var in self._data and self._data[var] == "1":
            return STATUS_ERROR_TAMPER
        var = thermostat + '_room_temperature'
        if var in self._data and int(self._data[var]) > TOO_HIGH_TEMP_LIMIT:
            return STATUS_ERROR_TOO_HIGH_TEMP
        return STATUS_OK

    # HVAC modes

    async def async_switch_to_cooling(self):
        for thermostat in self._thermostats():
            if self.get_setpoint(thermostat) == self.get_min_limit(thermostat):
                await self.set_setpoint(thermostat, self.get_max_limit(thermostat))
        await self._async_send({'sys_heat_cool_mode': '1'})

    async def async_switch_to_heating(self):
        for thermostat in self._thermostats():
            if self.get_setpoint(thermostat) == self.get_max_limit(thermostat):
                await self.set_setpoint(thermostat, self.get_min_limit(thermostat))
        await self._async_send({'sys_heat_cool_mode': '0'})

    async def async_turn_on(self, thermostat):
        data = await self._store.async_load()
        self._storage_data = {} if data is None else data
        last_temp = self._storage_data.get(thermostat, DEFAULT_TEMP)
        await self.set_setpoint(thermostat, last_temp)

    async def async_turn_off(self, thermostat):
        data = await self._store.async_load()
        self._storage_data = {} if data is None else data
        self._storage_data[thermostat] = self.get_setpoint(thermostat)
        await self._store.async_save(self._storage_data)
        off_temp = self.get_max_limit(thermostat) if self.is_cool_enabled() else self.get_min_limit(thermostat)
        await self.set_setpoint(thermostat, off_temp)

    # Cooling

    def is_cool_available(self):
        var = 'sys_cooling_available'
        if var in self._data:
            return self._data[var] == "1"

    def is_cool_enabled(self):
        var = 'sys_heat_cool_mode'
        if var in self._data:
            return self._data[var] == "1"

    # Away & Eco

    def is_away(self):
        var = 'sys_forced_eco_mode'
        return var in self._data and self._data[var] == "1"

    async def async_set_away(self, is_away):
        await self._async_send({'sys_forced_eco_mode': "1" if is_away else "0"})

    def is_eco(self, thermostat):
        if self.get_eco_setback(thermostat) == 0:
            return False
        var = thermostat + '_stat_cb_comfort_eco_mode'
        var_temp = 'cust_Temporary_ECO_Activation'
        return (var in self._data and self._data[var] == "1") or (
                    var_temp in self._data and self._data[var_temp] == "1")

    def get_eco_setback(self, thermostat):
        var = thermostat + '_eco_offset'
        if var in self._data:
            return round(int(self._data[var]) / 18, 1)

    def get_last_update(self):
        return self._coordinator.last_update

    # Writes

    async def async_set_variable(self, var_name, var_value):
        _LOGGER.debug("Called set variable: name: %s, value: %s", var_name, var_value)
        await self._async_send({var_name: var_value})

    async def set_setpoint(self, thermostat, temp):
        var = thermostat + '_setpoint'
        setpoint = int(temp * 18 + self.get_active_setback(thermostat, temp) + 320)
        await self._async_send({var: setpoint})

    def _thermostats(self):
        return self._coordinator.config_entry.runtime_data.thermostats

    async def _async_send(self, data):
        try:
            await self._client.send_data(data)
        except UponorApiError as err:
            raise HomeAssistantError(f"Failed to update Uponor controller: {err}") from err
        # Optimistically apply the write so the UI reflects it before the next poll.
        for key, value in data.items():
            self._data[key] = str(value)
        self._coordinator.async_update_listeners()
