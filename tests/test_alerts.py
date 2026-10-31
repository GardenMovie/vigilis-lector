import logging

import pytest

import collection

CONFIG = {"cpu": 90, "ram": 90, "disk": 90, "consecutive": 3}

DEFAULTS = {"cpu": 90, "ram": 90, "disk": 90, "consecutive": 5}


def make_metrics(cpu=10.0, ram=10.0, disk=10.0, ping=5.0, hostname="test-host"):
    return {
        "metadata": {"hostname": hostname},
        "fields": {"cpu_percent": cpu, "ram_percent": ram, "disk_percent": disk, "ping_ms": ping},
    }


def run(samples, config=CONFIG):
    state, per_cycle = {}, []
    for metrics in samples:
        messages, state = collection.evaluate_alerts(metrics, config, state)
        per_cycle.append(messages)
    return per_cycle


def test_no_alert_when_all_metrics_healthy():
    assert run([make_metrics()] * 5) == [[]] * 5


def test_no_alert_before_consecutive_threshold():
    assert run([make_metrics(cpu=95)] * 2) == [[], []]


def test_alert_fires_on_nth_consecutive_breach():
    cycles = run([make_metrics(cpu=95)] * 3)
    assert cycles[:2] == [[], []]
    assert len(cycles[2]) == 1


def test_sustained_breach_alerts_only_once():
    cycles = run([make_metrics(cpu=95)] * 10)
    assert sum(len(messages) for messages in cycles) == 1


def test_recovery_mid_streak_resets_count():
    samples = [make_metrics(cpu=95)] * 2 + [make_metrics(cpu=10)] + [make_metrics(cpu=95)] * 2
    assert run(samples) == [[]] * 5


def test_realerts_after_recovery_and_new_streak():
    samples = [make_metrics(cpu=95)] * 3 + [make_metrics(cpu=10)] + [make_metrics(cpu=95)] * 3
    cycles = run(samples)
    assert len(cycles[2]) == 1
    assert cycles[3] == []
    assert len(cycles[6]) == 1


def test_no_message_on_recovery():
    samples = [make_metrics(cpu=95)] * 3 + [make_metrics(cpu=10)]
    assert run(samples)[3] == []


def test_threshold_is_strictly_greater_than():
    assert run([make_metrics(cpu=90)] * 5) == [[]] * 5


@pytest.mark.parametrize("name,kwargs", [
    ("cpu", {"cpu": 95}),
    ("ram", {"ram": 95}),
    ("disk", {"disk": 95}),
])
def test_each_metric_alerts_independently(name, kwargs):
    cycles = run([make_metrics(**kwargs)] * 3)
    assert len(cycles[2]) == 1
    assert name in cycles[2][0].lower()


def test_two_metrics_breaching_give_two_messages():
    cycles = run([make_metrics(cpu=95, ram=95)] * 3)
    assert len(cycles[2]) == 2


def test_one_metric_streak_does_not_affect_another():
    samples = [make_metrics(cpu=95)] * 2 + [make_metrics(cpu=95, ram=95)]
    messages = run(samples)[2]
    assert len(messages) == 1
    assert "cpu" in messages[0].lower()


def test_ping_none_counts_as_breach():
    cycles = run([make_metrics(ping=None)] * 3)
    assert len(cycles[2]) == 1
    assert "ping" in cycles[2][0].lower()


def test_ping_value_is_healthy():
    assert run([make_metrics(ping=500.0)] * 5) == [[]] * 5


def test_message_contains_hostname_value_and_threshold():
    message = run([make_metrics(cpu=95.5, hostname="hewey-deb")] * 3)[2][0]
    assert "hewey-deb" in message
    assert "95.5" in message
    assert "90" in message


def test_input_state_is_not_mutated():
    state = {"cpu": {"streak": 1, "alerted": False}}
    snapshot = {"cpu": dict(state["cpu"])}
    collection.evaluate_alerts(make_metrics(cpu=95), CONFIG, state)
    assert state == snapshot


def test_per_host_threshold_via_config():
    config = {**CONFIG, "cpu": 50}
    assert len(run([make_metrics(cpu=60)] * 3, config)[2]) == 1


def test_per_host_consecutive_via_config():
    config = {**CONFIG, "consecutive": 1}
    assert len(run([make_metrics(cpu=95)], config)[0]) == 1


def test_config_disabled_when_webhook_unset():
    assert collection.load_alert_config({}) is None


def test_config_disabled_when_webhook_blank():
    assert collection.load_alert_config({"DISCORD_WEBHOOK_URL": ""}) is None


def test_config_defaults_applied():
    config = collection.load_alert_config({"DISCORD_WEBHOOK_URL": "https://hook"})
    assert config == {"webhook_url": "https://hook", **DEFAULTS}


def test_config_overrides_parsed_as_numbers():
    config = collection.load_alert_config({
        "DISCORD_WEBHOOK_URL": "https://hook",
        "ALERT_CPU_PERCENT": "75",
        "ALERT_RAM_PERCENT": "80.5",
        "ALERT_DISK_PERCENT": "95",
        "ALERT_CONSECUTIVE_SAMPLES": "3",
    })
    assert config["cpu"] == 75
    assert config["ram"] == 80.5
    assert config["disk"] == 95
    assert config["consecutive"] == 3


def test_config_partial_override_keeps_other_defaults():
    config = collection.load_alert_config({
        "DISCORD_WEBHOOK_URL": "https://hook",
        "ALERT_CPU_PERCENT": "50",
    })
    assert config["cpu"] == 50
    assert config["ram"] == DEFAULTS["ram"]


KEYS = [
    ("ALERT_CPU_PERCENT", "cpu"),
    ("ALERT_RAM_PERCENT", "ram"),
    ("ALERT_DISK_PERCENT", "disk"),
    ("ALERT_CONSECUTIVE_SAMPLES", "consecutive"),
]


@pytest.mark.parametrize("key,config_key", KEYS)
@pytest.mark.parametrize("bad", ["abc", "-5", "0"])
def test_config_invalid_value_falls_back_to_default_and_warns(key, config_key, bad, caplog):
    with caplog.at_level(logging.WARNING):
        config = collection.load_alert_config({"DISCORD_WEBHOOK_URL": "https://hook", key: bad})
    assert config[config_key] == DEFAULTS[config_key]
    assert key in caplog.text


@pytest.mark.parametrize("key,config_key", KEYS)
def test_config_blank_value_uses_default_without_warning(key, config_key, caplog):
    with caplog.at_level(logging.WARNING):
        config = collection.load_alert_config({"DISCORD_WEBHOOK_URL": "https://hook", key: ""})
    assert config[config_key] == DEFAULTS[config_key]
    assert caplog.text == ""
