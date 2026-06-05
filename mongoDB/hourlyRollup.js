exports = async function () {
  // A Scheduled Trigger will always call a function without arguments.
  // Documentation on Triggers: https://www.mongodb.com/docs/atlas/app-services/triggers/

  // Functions run by Triggers are run as System users and have full access to Services, Functions, and MongoDB Data.

  // Get the MongoDB service you want to use (see "Linked Data Sources" tab)
  const serviceName = "MonitoringSystem";
  const databaseName = "Metrics";
  const collectionName = "hardwareMin";
  const collection = context.services
    .get(serviceName)
    .db(databaseName)
    .collection(collectionName);

  const pipeline =
[
  {
    $group: {
      _id: {
        timestamp: {
          $dateTrunc: {
            date: "$timestamp",
            unit: "hour"
          }
        },
        hostname: "$metadata.hostname"
      },
      avgCpu: {
        $avg: "$fields.cpu_percent"
      },
      minCpu: {
        $min: "$fields.cpu_percent"
      },
      maxCpu: {
        $max: "$fields.cpu_percent"
      },
      avgRam: {
        $avg: "$fields.ram_percent"
      },
      minRam: {
        $min: "$fields.ram_percent"
      },
      maxRam: {
        $max: "$fields.ram_percent"
      },
      storageSpace: {
        $first: "$fields.disk_percent"
      },
      avgPing: {
        $avg: "$fields.ping_ms"
      },
      maxPing: {
        $max: "$fields.ping_ms"
      },
      count: {
        $sum: 1
      }
    }
  },
  {
    $project: {
      _id: {
        $concat: [
          {
            $toString: "$_id.timestamp"
          },
          "_",
          "$_id.hostname"
        ]
      },
      timestamp: "$_id.timestamp",
      metadata: {
        hostname: "$_id.hostname"
      },
      fields: {
        avgCpu: "$avgCpu",
        minCpu: "$minCpu",
        maxCpu: "$maxCpu",
        avgRam: "$avgRam",
        minRam: "$minRam",
        maxRam: "$maxRam",
        storageSpace: "$storageSpace",
        avgPing: "$avgPing",
        maxPing: "$maxPing",
        count: "$count"
      }
    }
  },
  {
    $merge: {
      into: "hardwareHour",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]



  
  try {
    await collection.aggregate(pipeline).toArray();
  } catch (err) {
    console.log("error performing aggregation pipeline: ", err.message);
  }
};
