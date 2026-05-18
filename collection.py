import psutil
import json
from datetime import datetime, timezone
import subprocess
import sys
import os
import pymongo
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.environ["MONGO_URI"]

# Database and collection names
DB_NAME = "Metrics"
COLLECTION_NAME = "hardwareMin"

def ping_latency(host="8.8.8.8"):
    try:
        # Use 1 ping, wait max 2 seconds, output in ms
        result = subprocess.run([
            "ping", "-c", "1", "-W", "2", host
        ], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "time=" in line:
                    # Extract the time=XX ms part
                    try:
                        return float(line.split("time=")[1].split()[0])
                    except Exception:
                        continue
        return None
    except Exception:
        return None

def collect_metrics():
	from datetime import timezone
	metrics = {
        "timestamp": datetime.now(timezone.utc),
		"metadata": {
			"hostname": "bob-arch",
			"Disk Size GB": round(psutil.disk_usage('/').total / (1024**3), 2),
			"RAM Size GB": round(psutil.virtual_memory().total / (1024**3), 2),
		},
		"fields": {
			"cpu_percent": psutil.cpu_percent(interval=1),
			"ram_percent": psutil.virtual_memory().percent,
			"disk_percent": psutil.disk_usage('/').percent,
			"ping_ms": ping_latency()
		},
		"temps":{}
	}
	# Try to get temperature sensors if available, and show per-sensor details
	try:
		temps = psutil.sensors_temperatures()
		if temps:
			per_sensor = {}
			all_temps = []
			for sensor_name, sensor_entries in temps.items():
				per_sensor[sensor_name] = []
				for entry in sensor_entries:
					if entry.current is not None:
						per_sensor[sensor_name].append({
							"label": entry.label or "",
							"current": entry.current,
							"high": entry.high,
							"critical": entry.critical
						})
						all_temps.append(entry.current)
			# if all_temps:
			# 	metrics["avg_temp_c"] = sum(all_temps) / len(all_temps)
			# 	metrics["max_temp_c"] = max(all_temps)
			# 	metrics["min_temp_c"] = min(all_temps)
			metrics["temps"] = per_sensor
	except Exception:
		pass
	return metrics

if __name__ == "__main__":
	metrics = collect_metrics()
	# Check for argument
	try:
		client = pymongo.MongoClient(MONGO_URI)
		db = client[DB_NAME]
		collection = db[COLLECTION_NAME]
		result = collection.insert_one(metrics)
		print(f"Inserted document with _id: {result.inserted_id} at {metrics['timestamp']}")
	except Exception as e:
		print(f"MongoDB insert failed: {e}")
		# Save metrics to missed/ folder
		import pathlib
		missed_dir = pathlib.Path("missed")
		missed_dir.mkdir(exist_ok=True)
		# Use UTC timestamp for filename
		ts = metrics["timestamp"].strftime("%Y%m%dT%H%M%SZ")
		missed_file = missed_dir / f"{ts}.json"
		# Convert datetime to isoformat for JSON
		metrics_serializable = json.loads(json.dumps(metrics, default=str))
		with open(missed_file, "w") as f:
			json.dump(metrics_serializable, f, indent=2)
		print(f"Saved missed metrics to {missed_file}")
