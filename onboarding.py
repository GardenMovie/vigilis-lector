import os
import sys
import subprocess
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

MONGO_URI = os.environ["MONGO_URI"]
HOSTNAME = os.environ["HOSTNAME"]
RAM_CAPACITY = int(os.environ["RAMCAPACITY"])
DISK_CAPACITY = int(os.environ["DISKCAPACITY"])
CPU_MODEL = os.environ["CPUMODEL"]
GPU_MODEL = os.environ["GPUMODEL"]

SYSTEMD_SERVICE_SRC = os.path.join(os.path.dirname(__file__), "systemd", "vigilis-lector.service")
SYSTEMD_SERVICE_DEST = "/etc/systemd/system/vigilis-lector.service"


def step(msg):
    print(f"\n==> {msg}")


def ping_cluster(client):
    step("Pinging MongoDB cluster")
    client.admin.command("ping")
    print("    Connected successfully.")


def setup_databases(client):
    step("Setting up databases and collections")

    hosts_db = client["Hosts"]
    if "specifications" not in hosts_db.list_collection_names():
        hosts_db.create_collection("specifications")
        print("    Created Hosts.specifications")
    else:
        print("    Hosts.specifications already exists")

    metrics_db = client["Metrics"]
    ttl_collections = {
        "hardwareMin": 7 * 24 * 3600,   # 7 days
        "hardwareHour": 90 * 24 * 3600,  # 90 days
        "hardwareDay": 0,                # keep indefinitely (no TTL)
    }
    for coll_name, ttl_seconds in ttl_collections.items():
        if coll_name not in metrics_db.list_collection_names():
            metrics_db.create_collection(coll_name)
            print(f"    Created Metrics.{coll_name}")
        else:
            print(f"    Metrics.{coll_name} already exists")

        if ttl_seconds > 0:
            existing = metrics_db[coll_name].index_information()
            if not any("expireAfterSeconds" in v for v in existing.values()):
                metrics_db[coll_name].create_index(
                    "timestamp", expireAfterSeconds=ttl_seconds
                )
                print(f"      TTL index set ({ttl_seconds}s) on Metrics.{coll_name}")


def setup_triggers():
    step("Atlas Scheduled Triggers (hourlyRollup / dailyRollup)")
    print("    These are App Services triggers — deploy them manually in the Atlas UI")
    print("    or via the Atlas CLI using the JS files in mongoDB/")
    print("    mongoDB/hourlyRollup.js  -> runs every hour")
    print("    mongoDB/dailyRollup.js   -> runs every day")


def populate_specifications(client):
    step("Populating Hosts.specifications for this host")
    specs = client["Hosts"]["specifications"]
    doc = {
        "hostname": HOSTNAME,
        "ramCapacityGB": RAM_CAPACITY,
        "diskCapacityGB": DISK_CAPACITY,
        "cpuModel": CPU_MODEL,
        "gpuModel": GPU_MODEL,
    }
    specs.delete_many({"hostname": HOSTNAME})
    specs.insert_one(doc)
    print(f"    Upserted specification for '{HOSTNAME}'")


def install_systemd_service():
    step("Installing systemd service")

    if not os.path.exists(SYSTEMD_SERVICE_SRC):
        print(f"    Service file not found at {SYSTEMD_SERVICE_SRC}")
        sys.exit(1)

    try:
        subprocess.run(
            ["sudo", "cp", SYSTEMD_SERVICE_SRC, SYSTEMD_SERVICE_DEST],
            check=True,
        )
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
        subprocess.run(
            ["sudo", "systemctl", "enable", "--now", "vigilis-lector.service"],
            check=True,
        )
        print("    Service installed, enabled, and started.")
    except subprocess.CalledProcessError as e:
        print(f"    Failed to install service: {e}")
        sys.exit(1)


if __name__ == "__main__":
    client = MongoClient(MONGO_URI, server_api=ServerApi("1"))

    try:
        ping_cluster(client)
        setup_databases(client)
        setup_triggers()
        populate_specifications(client)
        install_systemd_service()
        print("\nOnboarding complete.")
    except Exception as e:
        print(f"\nOnboarding failed: {e}")
        sys.exit(1)
    finally:
        client.close()
