"""Fixtures for Uponor tests."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom_components/uponor."""
    yield


def _vars(data):
    return {"output": {"vars": [{"waspVarName": k, "waspVarValue": v} for k, v in data.items()]}}


# 21.0 C  -> 21 * 18 + 320 = 698 ; min 5 C -> 410 ; max 35 C -> 950
CONTROLLER_DATA = {
    "sys_controller_1_presence": "1",
    "sys_controller_2_presence": "0",
    "C1_thermostat_1_presence": "1",
    "C1_thermostat_2_presence": "0",
    "C1_thermostat1_id": "1234",
    "cust_C1_T1_name": "Living room",
    "cust_SW_version_update": "X265_1.2",
    "C1_sw_version": "09.00_x",
    "C1_T1_room_temperature": "698",
    "C1_T1_setpoint": "698",
    "C1_T1_minimum_setpoint": "410",
    "C1_T1_maximum_setpoint": "950",
    "C1_T1_rh": "45",
    "C1_T1_eco_offset": "0",
    "C1_T1_stat_cb_actuator": "1",
    "C1_T1_ufh_pwm_output": "0",
    "sys_heat_cool_mode": "0",
    "sys_cooling_available": "1",
    "sys_forced_eco_mode": "0",
}


@pytest.fixture
def controller_data():
    return dict(CONTROLLER_DATA)


@pytest.fixture
def mock_controller(aioclient_mock, controller_data):
    """Fake JNAP endpoint at 192.168.1.10."""
    aioclient_mock.post(
        "http://192.168.1.10/JNAP/",
        json=_vars(controller_data),
    )
    return aioclient_mock
