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

  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  try {
    const result = await collection.deleteMany({
      timestamp: { $lt: thirtyDaysAgo }
    });
    console.log(`Deleted ${result.deletedCount} documents older than 30 days.`);
  } catch (err) {
    console.log("error performing purge: ", err.message);
  }
};
