"""The tests for sensor recorder platform."""
# pylint: disable=protected-access,invalid-name
from datetime import timedelta
from unittest.mock import patch

import pytest
from pytest import approx

from homeassistant.components.recorder import history
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.components.recorder.models import process_timestamp_to_utc_isoformat
from homeassistant.components.recorder.statistics import (
    list_statistic_ids,
    statistics_during_period,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.setup import setup_component
import homeassistant.util.dt as dt_util

from tests.components.recorder.common import wait_recording_done

ENERGY_SENSOR_ATTRIBUTES = {
    "device_class": "energy",
    "state_class": "measurement",
    "unit_of_measurement": "kWh",
}
POWER_SENSOR_ATTRIBUTES = {
    "device_class": "power",
    "state_class": "measurement",
    "unit_of_measurement": "kW",
}
PRESSURE_SENSOR_ATTRIBUTES = {
    "device_class": "pressure",
    "state_class": "measurement",
    "unit_of_measurement": "hPa",
}
TEMPERATURE_SENSOR_ATTRIBUTES = {
    "device_class": "temperature",
    "state_class": "measurement",
    "unit_of_measurement": "°C",
}


@pytest.mark.parametrize(
    "device_class,unit,native_unit,mean,min,max",
    [
        ("battery", "%", "%", 16.440677, 10, 30),
        ("battery", None, None, 16.440677, 10, 30),
        ("humidity", "%", "%", 16.440677, 10, 30),
        ("humidity", None, None, 16.440677, 10, 30),
        ("pressure", "Pa", "Pa", 16.440677, 10, 30),
        ("pressure", "hPa", "Pa", 1644.0677, 1000, 3000),
        ("pressure", "mbar", "Pa", 1644.0677, 1000, 3000),
        ("pressure", "inHg", "Pa", 55674.53, 33863.89, 101591.67),
        ("pressure", "psi", "Pa", 113354.48, 68947.57, 206842.71),
        ("temperature", "°C", "°C", 16.440677, 10, 30),
        ("temperature", "°F", "°C", -8.644068, -12.22222, -1.111111),
    ],
)
def test_compile_hourly_statistics(
    hass_recorder, caplog, device_class, unit, native_unit, mean, min, max
):
    """Test compiling hourly statistics."""
    zero = dt_util.utcnow()
    hass = hass_recorder()
    recorder = hass.data[DATA_INSTANCE]
    setup_component(hass, "sensor", {})
    attributes = {
        "device_class": device_class,
        "state_class": "measurement",
        "unit_of_measurement": unit,
    }
    four, states = record_states(hass, zero, "sensor.test1", attributes)
    hist = history.get_significant_states(hass, zero, four)
    assert dict(states) == dict(hist)

    recorder.do_adhoc_statistics(period="hourly", start=zero)
    wait_recording_done(hass)
    statistic_ids = list_statistic_ids(hass)
    assert statistic_ids == [
        {"statistic_id": "sensor.test1", "unit_of_measurement": native_unit}
    ]
    stats = statistics_during_period(hass, zero)
    assert stats == {
        "sensor.test1": [
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero),
                "mean": approx(mean),
                "min": approx(min),
                "max": approx(max),
                "last_reset": None,
                "state": None,
                "sum": None,
            }
        ]
    }
    assert "Error while processing event StatisticsTask" not in caplog.text


@pytest.mark.parametrize("attributes", [TEMPERATURE_SENSOR_ATTRIBUTES])
def test_compile_hourly_statistics_unsupported(hass_recorder, caplog, attributes):
    """Test compiling hourly statistics for unsupported sensor."""
    attributes = dict(attributes)
    zero = dt_util.utcnow()
    hass = hass_recorder()
    recorder = hass.data[DATA_INSTANCE]
    setup_component(hass, "sensor", {})
    four, states = record_states(hass, zero, "sensor.test1", attributes)
    if "unit_of_measurement" in attributes:
        attributes["unit_of_measurement"] = "invalid"
        _, _states = record_states(hass, zero, "sensor.test2", attributes)
        states = {**states, **_states}
        attributes.pop("unit_of_measurement")
        _, _states = record_states(hass, zero, "sensor.test3", attributes)
        states = {**states, **_states}
    attributes["state_class"] = "invalid"
    _, _states = record_states(hass, zero, "sensor.test4", attributes)
    states = {**states, **_states}
    attributes.pop("state_class")
    _, _states = record_states(hass, zero, "sensor.test5", attributes)
    states = {**states, **_states}
    attributes["state_class"] = "measurement"
    _, _states = record_states(hass, zero, "sensor.test6", attributes)
    states = {**states, **_states}
    attributes["state_class"] = "unsupported"
    _, _states = record_states(hass, zero, "sensor.test7", attributes)
    states = {**states, **_states}

    hist = history.get_significant_states(hass, zero, four)
    assert dict(states) == dict(hist)

    recorder.do_adhoc_statistics(period="hourly", start=zero)
    wait_recording_done(hass)
    statistic_ids = list_statistic_ids(hass)
    assert statistic_ids == [
        {"statistic_id": "sensor.test1", "unit_of_measurement": "°C"}
    ]
    stats = statistics_during_period(hass, zero)
    assert stats == {
        "sensor.test1": [
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero),
                "mean": approx(16.440677966101696),
                "min": approx(10.0),
                "max": approx(30.0),
                "last_reset": None,
                "state": None,
                "sum": None,
            }
        ]
    }
    assert "Error while processing event StatisticsTask" not in caplog.text


@pytest.mark.parametrize(
    "device_class,unit,native_unit,factor",
    [
        ("energy", "kWh", "kWh", 1),
        ("energy", "Wh", "kWh", 1 / 1000),
        ("monetary", "€", "€", 1),
        ("monetary", "SEK", "SEK", 1),
    ],
)
def test_compile_hourly_energy_statistics(
    hass_recorder, caplog, device_class, unit, native_unit, factor
):
    """Test compiling hourly statistics."""
    zero = dt_util.utcnow()
    hass = hass_recorder()
    recorder = hass.data[DATA_INSTANCE]
    setup_component(hass, "sensor", {})
    attributes = {
        "device_class": device_class,
        "state_class": "measurement",
        "unit_of_measurement": unit,
        "last_reset": None,
    }
    seq = [10, 15, 20, 10, 30, 40, 50, 60, 70]

    four, eight, states = record_energy_states(
        hass, zero, "sensor.test1", attributes, seq
    )
    hist = history.get_significant_states(
        hass, zero - timedelta.resolution, eight + timedelta.resolution
    )
    assert dict(states)["sensor.test1"] == dict(hist)["sensor.test1"]

    recorder.do_adhoc_statistics(period="hourly", start=zero)
    wait_recording_done(hass)
    recorder.do_adhoc_statistics(period="hourly", start=zero + timedelta(hours=1))
    wait_recording_done(hass)
    recorder.do_adhoc_statistics(period="hourly", start=zero + timedelta(hours=2))
    wait_recording_done(hass)
    statistic_ids = list_statistic_ids(hass)
    assert statistic_ids == [
        {"statistic_id": "sensor.test1", "unit_of_measurement": native_unit}
    ]
    stats = statistics_during_period(hass, zero)
    assert stats == {
        "sensor.test1": [
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(zero),
                "state": approx(factor * seq[2]),
                "sum": approx(factor * 10.0),
            },
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero + timedelta(hours=1)),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(four),
                "state": approx(factor * seq[5]),
                "sum": approx(factor * 10.0),
            },
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero + timedelta(hours=2)),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(four),
                "state": approx(factor * seq[8]),
                "sum": approx(factor * 40.0),
            },
        ]
    }
    assert "Error while processing event StatisticsTask" not in caplog.text


def test_compile_hourly_energy_statistics_unsupported(hass_recorder, caplog):
    """Test compiling hourly statistics."""
    zero = dt_util.utcnow()
    hass = hass_recorder()
    recorder = hass.data[DATA_INSTANCE]
    setup_component(hass, "sensor", {})
    sns1_attr = {
        "device_class": "energy",
        "state_class": "measurement",
        "unit_of_measurement": "kWh",
        "last_reset": None,
    }
    sns2_attr = {"device_class": "energy"}
    sns3_attr = {}
    sns4_attr = {
        "device_class": "energy",
        "state_class": "measurement",
        "unit_of_measurement": "kWh",
    }
    seq1 = [10, 15, 20, 10, 30, 40, 50, 60, 70]
    seq2 = [110, 120, 130, 0, 30, 45, 55, 65, 75]
    seq3 = [0, 0, 5, 10, 30, 50, 60, 80, 90]
    seq4 = [0, 0, 5, 10, 30, 50, 60, 80, 90]

    four, eight, states = record_energy_states(
        hass, zero, "sensor.test1", sns1_attr, seq1
    )
    _, _, _states = record_energy_states(hass, zero, "sensor.test2", sns2_attr, seq2)
    states = {**states, **_states}
    _, _, _states = record_energy_states(hass, zero, "sensor.test3", sns3_attr, seq3)
    states = {**states, **_states}
    _, _, _states = record_energy_states(hass, zero, "sensor.test4", sns4_attr, seq4)
    states = {**states, **_states}

    hist = history.get_significant_states(
        hass, zero - timedelta.resolution, eight + timedelta.resolution
    )
    assert dict(states)["sensor.test1"] == dict(hist)["sensor.test1"]

    recorder.do_adhoc_statistics(period="hourly", start=zero)
    wait_recording_done(hass)
    recorder.do_adhoc_statistics(period="hourly", start=zero + timedelta(hours=1))
    wait_recording_done(hass)
    recorder.do_adhoc_statistics(period="hourly", start=zero + timedelta(hours=2))
    wait_recording_done(hass)
    statistic_ids = list_statistic_ids(hass)
    assert statistic_ids == [
        {"statistic_id": "sensor.test1", "unit_of_measurement": "kWh"}
    ]
    stats = statistics_during_period(hass, zero)
    assert stats == {
        "sensor.test1": [
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(zero),
                "state": approx(20.0),
                "sum": approx(10.0),
            },
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero + timedelta(hours=1)),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(four),
                "state": approx(40.0),
                "sum": approx(10.0),
            },
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero + timedelta(hours=2)),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(four),
                "state": approx(70.0),
                "sum": approx(40.0),
            },
        ]
    }
    assert "Error while processing event StatisticsTask" not in caplog.text


def test_compile_hourly_energy_statistics_multiple(hass_recorder, caplog):
    """Test compiling multiple hourly statistics."""
    zero = dt_util.utcnow()
    hass = hass_recorder()
    recorder = hass.data[DATA_INSTANCE]
    setup_component(hass, "sensor", {})
    sns1_attr = {**ENERGY_SENSOR_ATTRIBUTES, "last_reset": None}
    sns2_attr = {**ENERGY_SENSOR_ATTRIBUTES, "last_reset": None}
    sns3_attr = {
        **ENERGY_SENSOR_ATTRIBUTES,
        "unit_of_measurement": "Wh",
        "last_reset": None,
    }
    sns4_attr = {**ENERGY_SENSOR_ATTRIBUTES}
    seq1 = [10, 15, 20, 10, 30, 40, 50, 60, 70]
    seq2 = [110, 120, 130, 0, 30, 45, 55, 65, 75]
    seq3 = [0, 0, 5, 10, 30, 50, 60, 80, 90]
    seq4 = [0, 0, 5, 10, 30, 50, 60, 80, 90]

    four, eight, states = record_energy_states(
        hass, zero, "sensor.test1", sns1_attr, seq1
    )
    _, _, _states = record_energy_states(hass, zero, "sensor.test2", sns2_attr, seq2)
    states = {**states, **_states}
    _, _, _states = record_energy_states(hass, zero, "sensor.test3", sns3_attr, seq3)
    states = {**states, **_states}
    _, _, _states = record_energy_states(hass, zero, "sensor.test4", sns4_attr, seq4)
    states = {**states, **_states}
    hist = history.get_significant_states(
        hass, zero - timedelta.resolution, eight + timedelta.resolution
    )
    assert dict(states)["sensor.test1"] == dict(hist)["sensor.test1"]

    recorder.do_adhoc_statistics(period="hourly", start=zero)
    wait_recording_done(hass)
    recorder.do_adhoc_statistics(period="hourly", start=zero + timedelta(hours=1))
    wait_recording_done(hass)
    recorder.do_adhoc_statistics(period="hourly", start=zero + timedelta(hours=2))
    wait_recording_done(hass)
    statistic_ids = list_statistic_ids(hass)
    assert statistic_ids == [
        {"statistic_id": "sensor.test1", "unit_of_measurement": "kWh"},
        {"statistic_id": "sensor.test2", "unit_of_measurement": "kWh"},
        {"statistic_id": "sensor.test3", "unit_of_measurement": "kWh"},
    ]
    stats = statistics_during_period(hass, zero)
    assert stats == {
        "sensor.test1": [
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(zero),
                "state": approx(20.0),
                "sum": approx(10.0),
            },
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero + timedelta(hours=1)),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(four),
                "state": approx(40.0),
                "sum": approx(10.0),
            },
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero + timedelta(hours=2)),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(four),
                "state": approx(70.0),
                "sum": approx(40.0),
            },
        ],
        "sensor.test2": [
            {
                "statistic_id": "sensor.test2",
                "start": process_timestamp_to_utc_isoformat(zero),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(zero),
                "state": approx(130.0),
                "sum": approx(20.0),
            },
            {
                "statistic_id": "sensor.test2",
                "start": process_timestamp_to_utc_isoformat(zero + timedelta(hours=1)),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(four),
                "state": approx(45.0),
                "sum": approx(-95.0),
            },
            {
                "statistic_id": "sensor.test2",
                "start": process_timestamp_to_utc_isoformat(zero + timedelta(hours=2)),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(four),
                "state": approx(75.0),
                "sum": approx(-65.0),
            },
        ],
        "sensor.test3": [
            {
                "statistic_id": "sensor.test3",
                "start": process_timestamp_to_utc_isoformat(zero),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(zero),
                "state": approx(5.0 / 1000),
                "sum": approx(5.0 / 1000),
            },
            {
                "statistic_id": "sensor.test3",
                "start": process_timestamp_to_utc_isoformat(zero + timedelta(hours=1)),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(four),
                "state": approx(50.0 / 1000),
                "sum": approx(30.0 / 1000),
            },
            {
                "statistic_id": "sensor.test3",
                "start": process_timestamp_to_utc_isoformat(zero + timedelta(hours=2)),
                "max": None,
                "mean": None,
                "min": None,
                "last_reset": process_timestamp_to_utc_isoformat(four),
                "state": approx(90.0 / 1000),
                "sum": approx(70.0 / 1000),
            },
        ],
    }
    assert "Error while processing event StatisticsTask" not in caplog.text


@pytest.mark.parametrize(
    "device_class,unit,value",
    [
        ("battery", "%", 30),
        ("battery", None, 30),
        ("humidity", "%", 30),
        ("humidity", None, 30),
        ("pressure", "Pa", 30),
        ("pressure", "hPa", 3000),
        ("pressure", "mbar", 3000),
        ("pressure", "inHg", 101591.67),
        ("pressure", "psi", 206842.71),
        ("temperature", "°C", 30),
        ("temperature", "°F", -1.111111),
    ],
)
def test_compile_hourly_statistics_unchanged(
    hass_recorder, caplog, device_class, unit, value
):
    """Test compiling hourly statistics, with no changes during the hour."""
    zero = dt_util.utcnow()
    hass = hass_recorder()
    recorder = hass.data[DATA_INSTANCE]
    setup_component(hass, "sensor", {})
    attributes = {
        "device_class": device_class,
        "state_class": "measurement",
        "unit_of_measurement": unit,
    }
    four, states = record_states(hass, zero, "sensor.test1", attributes)
    hist = history.get_significant_states(hass, zero, four)
    assert dict(states) == dict(hist)

    recorder.do_adhoc_statistics(period="hourly", start=four)
    wait_recording_done(hass)
    stats = statistics_during_period(hass, four)
    assert stats == {
        "sensor.test1": [
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(four),
                "mean": approx(value),
                "min": approx(value),
                "max": approx(value),
                "last_reset": None,
                "state": None,
                "sum": None,
            }
        ]
    }
    assert "Error while processing event StatisticsTask" not in caplog.text


def test_compile_hourly_statistics_partially_unavailable(hass_recorder, caplog):
    """Test compiling hourly statistics, with the sensor being partially unavailable."""
    zero = dt_util.utcnow()
    hass = hass_recorder()
    recorder = hass.data[DATA_INSTANCE]
    setup_component(hass, "sensor", {})
    four, states = record_states_partially_unavailable(
        hass, zero, "sensor.test1", TEMPERATURE_SENSOR_ATTRIBUTES
    )
    hist = history.get_significant_states(hass, zero, four)
    assert dict(states) == dict(hist)

    recorder.do_adhoc_statistics(period="hourly", start=zero)
    wait_recording_done(hass)
    stats = statistics_during_period(hass, zero)
    assert stats == {
        "sensor.test1": [
            {
                "statistic_id": "sensor.test1",
                "start": process_timestamp_to_utc_isoformat(zero),
                "mean": approx(21.1864406779661),
                "min": approx(10.0),
                "max": approx(25.0),
                "last_reset": None,
                "state": None,
                "sum": None,
            }
        ]
    }
    assert "Error while processing event StatisticsTask" not in caplog.text


@pytest.mark.parametrize(
    "device_class,unit,value",
    [
        ("battery", "%", 30),
        ("battery", None, 30),
        ("humidity", "%", 30),
        ("humidity", None, 30),
        ("pressure", "Pa", 30),
        ("pressure", "hPa", 3000),
        ("pressure", "mbar", 3000),
        ("pressure", "inHg", 101591.67),
        ("pressure", "psi", 206842.71),
        ("temperature", "°C", 30),
        ("temperature", "°F", -1.111111),
    ],
)
def test_compile_hourly_statistics_unavailable(
    hass_recorder, caplog, device_class, unit, value
):
    """Test compiling hourly statistics, with the sensor being unavailable."""
    zero = dt_util.utcnow()
    hass = hass_recorder()
    recorder = hass.data[DATA_INSTANCE]
    setup_component(hass, "sensor", {})
    attributes = {
        "device_class": device_class,
        "state_class": "measurement",
        "unit_of_measurement": unit,
    }
    four, states = record_states_partially_unavailable(
        hass, zero, "sensor.test1", attributes
    )
    _, _states = record_states(hass, zero, "sensor.test2", attributes)
    states = {**states, **_states}
    hist = history.get_significant_states(hass, zero, four)
    assert dict(states) == dict(hist)

    recorder.do_adhoc_statistics(period="hourly", start=four)
    wait_recording_done(hass)
    stats = statistics_during_period(hass, four)
    assert stats == {
        "sensor.test2": [
            {
                "statistic_id": "sensor.test2",
                "start": process_timestamp_to_utc_isoformat(four),
                "mean": approx(value),
                "min": approx(value),
                "max": approx(value),
                "last_reset": None,
                "state": None,
                "sum": None,
            }
        ]
    }
    assert "Error while processing event StatisticsTask" not in caplog.text


def test_compile_hourly_statistics_fails(hass_recorder, caplog):
    """Test compiling hourly statistics throws."""
    zero = dt_util.utcnow()
    hass = hass_recorder()
    recorder = hass.data[DATA_INSTANCE]
    setup_component(hass, "sensor", {})
    with patch(
        "homeassistant.components.sensor.recorder.compile_statistics",
        side_effect=Exception,
    ):
        recorder.do_adhoc_statistics(period="hourly", start=zero)
        wait_recording_done(hass)
    assert "Error while processing event StatisticsTask" in caplog.text


def record_states(hass, zero, entity_id, attributes):
    """Record some test states.

    We inject a bunch of state updates for temperature sensors.
    """
    attributes = dict(attributes)

    def set_state(entity_id, state, **kwargs):
        """Set the state."""
        hass.states.set(entity_id, state, **kwargs)
        wait_recording_done(hass)
        return hass.states.get(entity_id)

    one = zero + timedelta(minutes=1)
    two = one + timedelta(minutes=10)
    three = two + timedelta(minutes=40)
    four = three + timedelta(minutes=10)

    states = {entity_id: []}
    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=one):
        states[entity_id].append(set_state(entity_id, "10", attributes=attributes))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=two):
        states[entity_id].append(set_state(entity_id, "15", attributes=attributes))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=three):
        states[entity_id].append(set_state(entity_id, "30", attributes=attributes))

    return four, states


def record_energy_states(hass, zero, entity_id, _attributes, seq):
    """Record some test states.

    We inject a bunch of state updates for energy sensors.
    """

    def set_state(entity_id, state, **kwargs):
        """Set the state."""
        hass.states.set(entity_id, state, **kwargs)
        wait_recording_done(hass)
        return hass.states.get(entity_id)

    one = zero + timedelta(minutes=15)
    two = one + timedelta(minutes=30)
    three = two + timedelta(minutes=15)
    four = three + timedelta(minutes=15)
    five = four + timedelta(minutes=30)
    six = five + timedelta(minutes=15)
    seven = six + timedelta(minutes=15)
    eight = seven + timedelta(minutes=30)

    attributes = dict(_attributes)
    if "last_reset" in _attributes:
        attributes["last_reset"] = zero.isoformat()

    states = {entity_id: []}
    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=zero):
        states[entity_id].append(set_state(entity_id, seq[0], attributes=attributes))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=one):
        states[entity_id].append(set_state(entity_id, seq[1], attributes=attributes))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=two):
        states[entity_id].append(set_state(entity_id, seq[2], attributes=attributes))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=three):
        states[entity_id].append(set_state(entity_id, seq[3], attributes=attributes))

    attributes = dict(_attributes)
    if "last_reset" in _attributes:
        attributes["last_reset"] = four.isoformat()

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=four):
        states[entity_id].append(set_state(entity_id, seq[4], attributes=attributes))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=five):
        states[entity_id].append(set_state(entity_id, seq[5], attributes=attributes))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=six):
        states[entity_id].append(set_state(entity_id, seq[6], attributes=attributes))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=seven):
        states[entity_id].append(set_state(entity_id, seq[7], attributes=attributes))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=eight):
        states[entity_id].append(set_state(entity_id, seq[8], attributes=attributes))

    return four, eight, states


def record_states_partially_unavailable(hass, zero, entity_id, attributes):
    """Record some test states.

    We inject a bunch of state updates temperature sensors.
    """

    def set_state(entity_id, state, **kwargs):
        """Set the state."""
        hass.states.set(entity_id, state, **kwargs)
        wait_recording_done(hass)
        return hass.states.get(entity_id)

    one = zero + timedelta(minutes=1)
    two = one + timedelta(minutes=15)
    three = two + timedelta(minutes=30)
    four = three + timedelta(minutes=15)

    states = {entity_id: []}
    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=one):
        states[entity_id].append(set_state(entity_id, "10", attributes=attributes))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=two):
        states[entity_id].append(set_state(entity_id, "25", attributes=attributes))

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=three):
        states[entity_id].append(
            set_state(entity_id, STATE_UNAVAILABLE, attributes=attributes)
        )

    return four, states
