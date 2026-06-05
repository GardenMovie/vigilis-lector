# vigilis-lector

A lightweight hardware metrics collector that runs on Linux hosts and ships data to MongoDB Atlas. Metrics are collected every minute and rolled up to hourly and daily aggregates via Atlas Scheduled Triggers.

## How it works

- `collection.py` gathers CPU, RAM, disk, ping, and temperature readings once per minute and inserts them into `Metrics.hardwareMin`.
- A systemd service (`vigilis-lector.service`) keeps the collector running on boot.
- Two Atlas Scheduled Triggers (`hourlyRollup`, `dailyRollup`) aggregate the minute-level data into `Metrics.hardwareHour` and `Metrics.hardwareDay`.

## Collections

| Collection | Retention | Description |
|---|---|---|
| `Metrics.hardwareMin` | 7 days | Raw per-minute readings |
| `Metrics.hardwareHour` | 90 days | Hourly averages/min/max |
| `Metrics.hardwareDay` | Indefinite | Daily aggregates |
| `Hosts.specifications` | Indefinite | Host hardware specs |

## Setup

### Prerequisites

- Python 3 with `psutil`, `pymongo`, and `python-dotenv` installed
- A MongoDB Atlas cluster
- `sudo` access (for installing the systemd service)

### .env

Create a `.env` file in the project root:

```env
MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/
HOSTNAME=my-hostname
RAMCAPACITY=32
DISKCAPACITY=500
CPUMODEL=Intel Core i7-12700K
GPUMODEL=NVIDIA RTX 3080
```

`RAMCAPACITY` and `DISKCAPACITY` are integers (GB). `HOSTNAME` identifies this machine in the database.

### Automated onboarding

Run the onboarding script to set everything up in one step:

```bash
python3 onboarding.py
```

This will:
1. Verify the MongoDB connection
2. Create the `Hosts` and `Metrics` databases and collections with TTL indexes
3. Print instructions for deploying the Atlas Scheduled Triggers
4. Insert this host's hardware specification into `Hosts.specifications`
5. Install, enable, and start the systemd service

### Manual onboarding

If you prefer to set up each step yourself:

#### 1. Verify MongoDB connection

```bash
python3 pingMongoDB.py
```

#### 2. Create collections and TTL indexes

In the Atlas UI (or mongosh), create these collections:

- `Hosts.specifications` — no TTL
- `Metrics.hardwareMin` — TTL index on `timestamp`, expireAfterSeconds: `604800` (7 days)
- `Metrics.hardwareHour` — TTL index on `timestamp`, expireAfterSeconds: `7776000` (90 days)
- `Metrics.hardwareDay` — no TTL

#### 3. Deploy Atlas Scheduled Triggers

Deploy both JS files as App Services Scheduled Triggers in the Atlas UI or via the Atlas CLI. Link them to your cluster's data source named `MonitoringSystem`.

| File | Schedule | Writes to |
|---|---|---|
| `mongoDB/hourlyRollup.js` | Every hour | `Metrics.hardwareHour` |
| `mongoDB/dailyRollup.js` | Every day | `Metrics.hardwareDay` |

#### 4. Insert host specifications

Add a document to `Hosts.specifications` for this machine:

```json
{
  "hostname": "<HOSTNAME>",
  "ramCapacityGB": <RAMCAPACITY>,
  "diskCapacityGB": <DISKCAPACITY>,
  "cpuModel": "<CPUMODEL>",
  "gpuModel": "<GPUMODEL>"
}
```

If a document with the same `hostname` already exists, replace it.

#### 5. Install the systemd service

```bash
sudo cp systemd/vigilis-lector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vigilis-lector.service
```

Verify it's running:

```bash
systemctl status vigilis-lector.service
```

The service runs `collection.py` and restarts automatically every 60 seconds on failure.
