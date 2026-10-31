exports = async function () {
  const serviceName = "MonitoringSystem";
  const db = context.services.get(serviceName).db("Metrics");
  const hardwareMin = db.collection("hardwareMin");
  const specifications = context.services
    .get(serviceName)
    .db("Hosts")
    .collection("specifications");
  const alertState = context.services
    .get(serviceName)
    .db("Hosts")
    .collection("alertState");

  const webhookUrl = context.values.get("DISCORD_WEBHOOK_URL");
  if (!webhookUrl) {
    console.log("DISCORD_WEBHOOK_URL value is not set, skipping silent host check.");
    return;
  }

  const silentAfterMs = 10 * 60 * 1000;
  const now = Date.now();

  try {
    const hosts = await specifications.find({}, { hostname: 1 }).toArray();

    const latest = await hardwareMin
      .aggregate([
        {
          $group: {
            _id: "$metadata.hostname",
            lastSeen: { $max: "$timestamp" }
          }
        }
      ])
      .toArray();
    const lastSeenByHost = {};
    for (const doc of latest) {
      lastSeenByHost[doc._id] = doc.lastSeen;
    }

    const alerted = await alertState.find({ alerted: true }, { hostname: 1 }).toArray();
    const alertedHosts = new Set(alerted.map((doc) => doc.hostname));

    for (const { hostname } of hosts) {
      const lastSeen = lastSeenByHost[hostname];
      const silent = !lastSeen || now - lastSeen.getTime() > silentAfterMs;

      if (!silent) {
        if (alertedHosts.has(hostname)) {
          await alertState.updateOne({ hostname }, { $set: { alerted: false } });
        }
        continue;
      }

      if (alertedHosts.has(hostname)) {
        continue;
      }

      const since = lastSeen
        ? `last sample ${Math.round((now - lastSeen.getTime()) / 60000)} minutes ago`
        : "no samples found in the last 7 days";
      const response = await context.http.post({
        url: webhookUrl,
        headers: { "Content-Type": ["application/json"] },
        body: JSON.stringify({
          content: `Host **${hostname}** has gone silent (${since}).`
        })
      });

      if (response.statusCode >= 200 && response.statusCode < 300) {
        await alertState.updateOne(
          { hostname },
          { $set: { alerted: true, alertedAt: new Date() } },
          { upsert: true }
        );
        console.log(`Alerted silent host ${hostname}.`);
      } else {
        console.log(`Webhook returned ${response.statusCode} for ${hostname}, will retry.`);
      }
    }
  } catch (err) {
    console.log("error performing silent host check: ", err.message);
  }
};
