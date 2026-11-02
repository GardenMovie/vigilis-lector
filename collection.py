import json
import logging
import math
import os
import subprocess
import sys
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone

import psutil
import pymongo
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Database and collection names
DB_NAME = "Metrics"
COLLECTION_NAME = "hardwareMin"

COLLECTION_INTERVAL_SECONDS = 60

ID_LOG_PATH = os.path.join(os.path.dirname(__file__), "logs/insert_ids.json")
ID_LOG_MAXLEN = 100

SPOOL_PATH = os.path.join(os.path.dirname(__file__), "logs/spool.json")
SPOOL_MAXLEN = 100

ALERT_SETTINGS = {
    "cpu": ("ALERT_CPU_PERCENT", 90, float),
    "ram": ("ALERT_RAM_PERCENT", 90, float),
    "disk": ("ALERT_DISK_PERCENT", 90, float),
    "consecutive": ("ALERT_CONSECUTIVE_SAMPLES", 5, int),
}
ALERT_THRESHOLD_CHECKS = [
    ("cpu", "cpu_percent"),
    ("ram", "ram_percent"),
    ("disk", "disk_percent"),
]
DISCORD_TIMEOUT_SECONDS = 5
DISCORD_USER_AGENT = "vigilis-lector"

def load_id_log():
    if os.path.exists(ID_LOG_PATH):
        with open(ID_LOG_PATH) as f:
            return deque(json.load(f), maxlen=ID_LOG_MAXLEN)
    return deque(maxlen=ID_LOG_MAXLEN)

def save_id_log(log):
    with open(ID_LOG_PATH, "w") as f:
        json.dump(list(log), f)

def metrics_to_json(metrics):
    doc = dict(metrics)
    doc["timestamp"] = doc["timestamp"].isoformat()
    return doc

def metrics_from_json(doc):
    metrics = dict(doc)
    metrics["timestamp"] = datetime.fromisoformat(metrics["timestamp"])
    return metrics

def load_spool():
    if os.path.exists(SPOOL_PATH):
        with open(SPOOL_PATH) as f:
            return deque((metrics_from_json(doc) for doc in json.load(f)), maxlen=SPOOL_MAXLEN)
    return deque(maxlen=SPOOL_MAXLEN)

def save_spool(samples):
    if samples:
        with open(SPOOL_PATH, "w") as f:
            json.dump([metrics_to_json(m) for m in samples], f)
    elif os.path.exists(SPOOL_PATH):
        os.remove(SPOOL_PATH)

def ping_latency(host="8.8.8.8"):
    try:
        # Use 1 ping, wait max 2 seconds, output in ms
        result = subprocess.run([
            "ping", "-c", "1", "-W", "2", host
        ], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "time=" in line:
                    # Extract the time=XX ms part
                    try:
                        return float(line.split("time=")[1].split()[0])
                    except Exception:  # noqa: BLE001, S112
                        continue
        return None
    except Exception:  # noqa: BLE001
        return None

def collect_metrics(hostname):
    metrics = {
        "timestamp": datetime.now(timezone.utc),
        "metadata": {
            "hostname": hostname,
        },
        "fields": {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "ping_ms": ping_latency()
        },
    }
    return metrics

def parse_alert_setting(env, key, default, cast):
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(raw)
    except ValueError:
        logger.warning("Invalid %s=%r, using default %s", key, raw, default)
        return default
    return value

def load_alert_config(env):
    webhook_url = env.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return None
    config = {"webhook_url": webhook_url}
    for name, (key, default, cast) in ALERT_SETTINGS.items():
        config[name] = parse_alert_setting(env, key, default, cast)
    return config

def evaluate_alerts(metrics, config, state):
    hostname = metrics["metadata"]["hostname"]
    fields = metrics["fields"]
    messages = []
    new_state = {}

    checks = [
        (name, fields[field], config[name], lambda v, t: v is not None and v > t)
        for name, field in ALERT_THRESHOLD_CHECKS
    ]
    checks.append(("ping", fields["ping_ms"], None, lambda v, _t: v is None))

    for name, value, threshold, is_breach in checks:
        if not is_breach(value, threshold):
            new_state[name] = {"streak": 0, "alerted": False}
            continue

        previous = state.get(name, {"streak": 0, "alerted": False})
        streak = previous["streak"] + 1
        alerted = previous["alerted"]
        if streak >= config["consecutive"] and not alerted:
            if name == "ping":
                detail = "ping is failing (no response)"
            else:
                detail = f"{name} at {value}% (threshold {threshold}%)"
            messages.append(f"{hostname}: {detail} for {streak} consecutive samples")
            alerted = True
        new_state[name] = {"streak": streak, "alerted": alerted}

    return messages, new_state

def send_discord_alert(webhook_url, content, timeout=DISCORD_TIMEOUT_SECONDS):
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps({"content": content}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": DISCORD_USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception as e:  # noqa: BLE001
        logger.warning("Discord alert failed: %s", e)
        return False

if __name__ == "__main__":
    MONGO_URI = os.environ["MONGO_URI"]
    HOSTNAME = os.environ["HOSTNAME"]
    ALERT_CONFIG = load_alert_config(os.environ)
    alert_state = {}

    client = pymongo.MongoClient(MONGO_URI)
    collection = client[DB_NAME][COLLECTION_NAME]

    while True:
        cycle_start = time.monotonic()

        spooled = load_spool()
        if spooled:
            try:
                result = collection.insert_many(spooled)
                logger.info("Flushed %d spooled sample(s) from %s", len(result.inserted_ids), SPOOL_PATH)
                save_spool([])
            except Exception as e:  # noqa: BLE001
                logger.warning("Spool flush failed, will retry next cycle: %s", e)

        metrics = collect_metrics(HOSTNAME)

        if ALERT_CONFIG:
            try:
                messages, alert_state = evaluate_alerts(metrics, ALERT_CONFIG, alert_state)
                for message in messages:
                    send_discord_alert(ALERT_CONFIG["webhook_url"], message)
            except Exception as e:  # noqa: BLE001
                logger.warning("Alert check failed: %s", e)

        try:
            result = collection.insert_one(metrics)
            logger.info("Inserted document with _id: %s at %s", result.inserted_id, metrics['timestamp'])
            id_log = load_id_log()
            id_log.append(str(result.inserted_id))
            save_id_log(id_log)
        except Exception as e:  # noqa: BLE001
            logger.error("MongoDB insert failed, spooling for retry: %s", e)
            spooled = load_spool()
            spooled.append(metrics)
            save_spool(spooled)

        elapsed = time.monotonic() - cycle_start
        time.sleep(max(0, COLLECTION_INTERVAL_SECONDS - elapsed))
