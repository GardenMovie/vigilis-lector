exports = async function () {
  // A Scheduled Trigger will always call a function without arguments.
  // Documentation on Triggers: https://www.mongodb.com/docs/atlas/app-services/triggers/

  // Functions run by Triggers are run as System users and have full access to Services, Functions, and MongoDB Data.

  // Get the MongoDB service you want to use (see "Linked Data Sources" tab)
  const serviceName = "MonitoringSystem";
  const databaseName = "Metrics";
  const collectionName = "hardwareHour";
  const collection = context.services
    .get(serviceName)
    .db(databaseName)
    .collection(collectionName);

  const pipeline =
[
  {
    $sort: {
      timestamp: 1
    }
  },
  {
    $group: {
      _id: {
        timestamp: {
          $dateTrunc: {
            date: "$timestamp",
            unit: "day"
          }
        },
        hostname: "$metadata.hostname"
      },
      avgCpu: {
        $avg: "$fields.avgCpu"
      },
      minCpu: {
        $min: "$fields.minCpu"
      },
      maxCpu: {
        $max: "$fields.maxCpu"
      },
      avgRam: {
        $avg: "$fields.avgRam"
      },
      minRam: {
        $min: "$fields.minRam"
      },
      maxRam: {
        $max: "$fields.maxRam"
      },
      storageSpace: {
        $first: "$fields.storageSpace"
      },
      avgPing: {
        $avg: "$fields.avgPing"
      },
      maxPing: {
        $max: "$fields.maxPing"
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
      into: "hardwareDay",
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
