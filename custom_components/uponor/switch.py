from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_NAME
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
    name = entry.data[CONF_NAME]
    entities = [AwaySwitch(runtime.coordinator, state_proxy, name)]

    if state_proxy.is_cool_available():
        entities.append(CoolSwitch(runtime.coordinator, state_proxy, name))

    async_add_entities(entities)


class UponorSystemSwitch(CoordinatorEntity, SwitchEntity):
    """Base for switches attached to the whole Uponor system device."""

    _name_suffix = ""

    def __init__(self, coordinator, state_proxy, name):
        super().__init__(coordinator)
        self._state_proxy = state_proxy
        self._attr_name = f"{name} {self._name_suffix}"
        # Kept identical to earlier releases so existing entity registry entries survive.
        self._attr_unique_id = self._attr_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "c")},
            name=name,
            manufacturer=DEVICE_MANUFACTURER,
            model=state_proxy.get_model(),
        )


class AwaySwitch(UponorSystemSwitch):
    _name_suffix = "Away"
    _attr_icon = "mdi:home-export-outline"

    @property
    def is_on(self):
        return self._state_proxy.is_away()

    async def async_turn_on(self, **kwargs):
        await self._state_proxy.async_set_away(True)

    async def async_turn_off(self, **kwargs):
        await self._state_proxy.async_set_away(False)


class CoolSwitch(UponorSystemSwitch):
    _name_suffix = "Cooling Mode"
    _attr_icon = "mdi:snowflake"

    @property
    def is_on(self):
        return self._state_proxy.is_cool_enabled()

    async def async_turn_on(self, **kwargs):
        await self._state_proxy.async_switch_to_cooling()

    async def async_turn_off(self, **kwargs):
        await self._state_proxy.async_switch_to_heating()
