# vigilis-lector

A lightweight hardware metrics collector that runs on Linux hosts and ships data to MongoDB Atlas. Metrics are collected every minute and rolled up to hourly and daily aggregates via Atlas Scheduled Triggers.

![Architecture diagram](images/diagram.png)

## How it works

- `collection.py` gathers CPU, RAM, disk, and ping readings once per minute and inserts them into `Metrics.hardwareMin`.
- A systemd service (`vigilis-lector.service`) keeps the collector running on boot.
- Two Atlas Scheduled Triggers (`hourlyRollup`, `dailyRollup`) aggregate the minute-level data into `Metrics.hardwareHour` and `Metrics.hardwareDay`.
- An Atlas Scheduled Trigger (`silentHostAlert`) posts a Discord alert when a host stops reporting.

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
python3 utilities/ping_mongoDB.py
```

#### 2. Create collections and TTL indexes

In the Atlas UI (or mongosh), create these collections:

- `Hosts.specifications` — no TTL
- `Hosts.alertState` — no TTL; used by `mongoDB/silentHostAlert.js` to avoid repeat alerts
- `Metrics.hardwareMin` — timeseries collection with a native TTL index on `timestamp`, expireAfterSeconds: `604800` (7 days)
- `Metrics.hardwareHour` — plain collection, no native TTL support; retention (90 days) is enforced by `mongoDB/purgeOldEntriesHourly.js`
- `Metrics.hardwareDay` — no TTL, indefinite retention

#### 3. Deploy Atlas Scheduled Triggers

Deploy all JS files as App Services Scheduled Triggers in the Atlas UI or via the Atlas CLI. Link them to your cluster's data source named `MonitoringSystem`.

| File | Schedule | Writes to |
|---|---|---|
| `mongoDB/hourlyRollup.js` | Every hour | `Metrics.hardwareHour` |
| `mongoDB/dailyRollup.js` | Every day | `Metrics.hardwareDay` |
| `mongoDB/purgeOldEntriesHourly.js` | Every day | Deletes `Metrics.hardwareHour` docs older than 90 days |
| `mongoDB/silentHostAlert.js` | Every 5 minutes | Posts to Discord when a host stops reporting; tracks state in `Hosts.alertState` |

`silentHostAlert.js` reads the webhook URL from an App Services Value (create it as a Secret) named `DISCORD_WEBHOOK_URL`. A host counts as silent when its newest `hardwareMin` sample is more than 10 minutes old. It alerts once per silence and resets quietly when the host returns.

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

The unit file is a template (`{{USER}}` / `{{WORKDIR}}` placeholders); substitute in your user and this repo's absolute path before installing:

```bash
sed -e "s#{{USER}}#$USER#g" -e "s#{{WORKDIR}}#$(pwd)#g" systemd/vigilis-lector.service | sudo tee /etc/systemd/system/vigilis-lector.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now vigilis-lector.service
```

Verify it's running:

```bash
systemctl status vigilis-lector.service
```

The service runs `collection.py` and restarts automatically every 60 seconds on failure.
