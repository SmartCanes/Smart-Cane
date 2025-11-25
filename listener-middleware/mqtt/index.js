// import mqtt from "mqtt";
// import { TOPIC_DEST, TOPIC_LOCATION } from "./topic.js";
// import { handleDestination, handleLocation } from "./handlers.js";

// export const client = mqtt.connect(process.env.MQTT_BROKER);

// client.on("connect", () => {
//     console.log("MQTT connected");
//     client.subscribe([TOPIC_LOCATION, TOPIC_DEST]);
// });

// client.on("message", (topic, message) => {
//     try {
//         const payload = JSON.parse(message.toString());
//         if (topic === TOPIC_DEST) handleDestination(payload);
//         if (topic === TOPIC_LOCATION) handleLocation(payload, client);
//     } catch (e) {
//         console.error("MQTT error", e);
//     }
// });


