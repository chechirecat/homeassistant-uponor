from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_ECO,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import UponorConfigEntry
from .const import DOMAIN, DEVICE_MANUFACTURER


async def async_setup_entry(
    hass: HomeAssistant, entry: UponorConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    state_proxy = runtime.state_proxy

    entities = []
    for thermostat in runtime.thermostats:
        if thermostat.lower() in entry.data:
            name = entry.data[thermostat.lower()]
        else:
            name = state_proxy.get_room_name(thermostat)
        entities.append(UponorClimate(runtime.coordinator, state_proxy, thermostat, name))
    async_add_entities(entities)


class UponorClimate(CoordinatorEntity, ClimateEntity):

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    def __init__(self, coordinator, state_proxy, thermostat, name):
        super().__init__(coordinator)
        self._state_proxy = state_proxy
        self._thermostat = thermostat
        self._attr_name = name
        self._attr_unique_id = state_proxy.get_thermostat_id(thermostat)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=name,
            manufacturer=DEVICE_MANUFACTURER,
            model=state_proxy.get_model(),
            sw_version=state_proxy.get_version(thermostat),
        )

    @property
    def _is_on(self):
        return self._state_proxy.is_on(self._thermostat)

    @property
    def hvac_modes(self):
        if self._state_proxy.is_cool_enabled():
            return [HVACMode.COOL, HVACMode.OFF]
        return [HVACMode.HEAT, HVACMode.OFF]

    @property
    def preset_modes(self):
        return [self.preset_mode] if self.preset_mode is not None else []

    @property
    def current_humidity(self):
        return self._state_proxy.get_humidity(self._thermostat)

    @property
    def current_temperature(self):
        return self._state_proxy.get_temperature(self._thermostat)

    @property
    def target_temperature(self):
        return self._state_proxy.get_setpoint(self._thermostat)

    @property
    def min_temp(self):
        return self._state_proxy.get_min_limit(self._thermostat)

    @property
    def max_temp(self):
        return self._state_proxy.get_max_limit(self._thermostat)

    @property
    def extra_state_attributes(self):
        return {
            'id': self._thermostat,
            'status': self._state_proxy.get_status(self._thermostat),
            'pulse_width_modulation': self._state_proxy.get_pwm(self._thermostat),
            'last_update': self._state_proxy.get_last_update(),
            'eco_setback': self._state_proxy.get_eco_setback(self._thermostat),
        }

    @property
    def preset_mode(self):
        if self._state_proxy.is_eco(self._thermostat):
            return PRESET_ECO
        if self._state_proxy.is_away():
            return PRESET_AWAY
        return None

    @property
    def hvac_mode(self):
        if not self._is_on:
            return HVACMode.OFF
        if self._state_proxy.is_cool_enabled():
            return HVACMode.COOL
        return HVACMode.HEAT

    @property
    def hvac_action(self):
        if not self._is_on:
            return HVACAction.OFF
        if self._state_proxy.is_active(self._thermostat):
            return HVACAction.COOLING if self._state_proxy.is_cool_enabled() else HVACAction.HEATING
        return HVACAction.IDLE

    async def async_turn_off(self):
        if self._is_on:
            await self._state_proxy.async_turn_off(self._thermostat)

    async def async_turn_on(self):
        if not self._is_on:
            await self._state_proxy.async_turn_on(self._thermostat)

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        elif hvac_mode in (HVACMode.HEAT, HVACMode.COOL):
            await self.async_turn_on()

    async def async_set_temperature(self, **kwargs):
        if kwargs.get(ATTR_TEMPERATURE) is None:
            return
        await self._state_proxy.set_setpoint(self._thermostat, kwargs.get(ATTR_TEMPERATURE))
