"""The tests for sensor recorder platform."""
# pylint: disable=protected-access,invalid-name
from datetime import timedelta
from unittest.mock import patch, sentinel

from pytest import approx

from homeassistant.components.recorder import history
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.components.recorder.models import process_timestamp_to_utc_isoformat
from homeassistant.components.recorder.statistics import (
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import TEMP_CELSIUS
from homeassistant.setup import setup_component
import homeassistant.util.dt as dt_util

from tests.components.recorder.common import wait_recording_done


def test_compile_hourly_statistics(hass_recorder):
    """Test compiling hourly statistics."""
    hass = hass_recorder()
    recorder = hass.data[DATA_INSTANCE]
    setup_component(hass, "sensor", {})
    zero, four, states = record_states(hass)
    hist = history.get_significant_states(hass, zero, four)
    assert dict(states) == dict(hist)

    for kwargs in ({}, {"statistic_ids": ["sensor.test1"]}):
        stats = statistics_during_period(hass, zero, **kwargs)
        assert stats == {}
    stats = get_last_statistics(hass, 0, "sensor.test1")
    assert stats == {}

    recorder.do_adhoc_statistics(period="hourly", start=zero)
    recorder.do_adhoc_statistics(period="hourly", start=four)
    wait_recording_done(hass)
    expected_1 = {
        "statistic_id": "sensor.test1",
        "start": process_timestamp_to_utc_isoformat(zero),
        "mean": approx(14.915254237288135),
        "min": approx(10.0),
        "max": approx(20.0),
        "last_reset": None,
        "state": None,
        "sum": None,
    }
    expected_2 = {
        "statistic_id": "sensor.test1",
        "start": process_timestamp_to_utc_isoformat(four),
        "mean": approx(20.0),
        "min": approx(20.0),
        "max": approx(20.0),
        "last_reset": None,
        "state": None,
        "sum": None,
    }
    expected_stats1 = [
        {**expected_1, "statistic_id": "sensor.test1"},
        {**expected_2, "statistic_id": "sensor.test1"},
    ]
    expected_stats2 = [
        {**expected_1, "statistic_id": "sensor.test2"},
        {**expected_2, "statistic_id": "sensor.test2"},
    ]

    # Test statistics_during_period
    stats = statistics_during_period(hass, zero)
    assert stats == {"sensor.test1": expected_stats1, "sensor.test2": expected_stats2}

    stats = statistics_during_period(hass, zero, statistic_ids=["sensor.test2"])
    assert stats == {"sensor.test2": expected_stats2}

    stats = statistics_during_period(hass, zero, statistic_ids=["sensor.test3"])
    assert stats == {}

    # Test get_last_statistics
    stats = get_last_statistics(hass, 0, "sensor.test1")
    assert stats == {}

    stats = get_last_statistics(hass, 1, "sensor.test1")
    assert stats == {"sensor.test1": [{**expected_2, "statistic_id": "sensor.test1"}]}

    stats = get_last_statistics(hass, 2, "sensor.test1")
    assert stats == {"sensor.test1": expected_stats1[::-1]}

    stats = get_last_statistics(hass, 3, "sensor.test1")
    assert stats == {"sensor.test1": expected_stats1[::-1]}

    stats = get_last_statistics(hass, 1, "sensor.test3")
    assert stats == {}


def record_states(hass):
    """Record some test states.

    We inject a bunch of state updates temperature sensors.
    """
    mp = "media_player.test"
    sns1 = "sensor.test1"
    sns2 = "sensor.test2"
    sns3 = "sensor.test3"
    sns4 = "sensor.test4"
    sns1_attr = {
        "device_class": "temperature",
        "state_class": "measurement",
        "unit_of_measurement": TEMP_CELSIUS,
    }
    sns2_attr = {
        "device_class": "humidity",
        "state_class": "measurement",
        "unit_of_measurement": "%",
    }
    sns3_attr = {"device_class": "temperature"}
    sns4_attr = {}

    def set_state(entity_id, state, **kwargs):
        """Set the state."""
        hass.states.set(entity_id, state, **kwargs)
        wait_recording_done(hass)
        return hass.states.get(entity_id)

    zero = dt_util.utcnow()
    one = zero + timedelta(minutes=1)
    two = one + timedelta(minutes=15)
    three = two + timedelta(minutes=30)
    four = three + timedelta(minutes=15)

    states = {mp: [], sns1: [], sns2: [], sns3: [], sns4: []}
    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=one):
        states[mp].append(
            set_state(mp, "idle", attributes={"media_title": str(sentinel.mt1)})
        )
        states[mp].append(
            set_state(mp, "YouTube", attributes={"media_title": str(sentinel.mt2)})
        )
        states[sns1].append(set_state(sns1, "10", attributes=sns1_attr))
        states[sns2].append(set_state(sns2, "10", attributes=sns2_attr))
        states[sns3].append(set_state(sns3, "10", attributes=sns3_attr))
        states[sns4].append(set_state(sns4, "10", attributes=sns4_attr))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=two):
        states[sns1].append(set_state(sns1, "15", attributes=sns1_attr))
        states[sns2].append(set_state(sns2, "15", attributes=sns2_attr))
        states[sns3].append(set_state(sns3, "15", attributes=sns3_attr))
        states[sns4].append(set_state(sns4, "15", attributes=sns4_attr))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=three):
        states[sns1].append(set_state(sns1, "20", attributes=sns1_attr))
        states[sns2].append(set_state(sns2, "20", attributes=sns2_attr))
        states[sns3].append(set_state(sns3, "20", attributes=sns3_attr))
        states[sns4].append(set_state(sns4, "20", attributes=sns4_attr))

    return zero, four, states
