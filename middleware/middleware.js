const mqtt = require("mqtt");
const axios = require("axios");

const MQTT_BROKER = process.env.MQTT_BROKER || "mqtt://mosquitto:1883";
const GH_URL = process.env.GH_URL || "http://graphhopper:8989/route";

const TOPIC_LOCATION = "cane/location";
const TOPIC_DEST = "guardian/destination";
const TOPIC_INSTR = "cane/instructions";

let destination = null;
const client = mqtt.connect(MQTT_BROKER);

client.on("connect", () => {
    console.log("✅ Middleware connected to MQTT");
    client.subscribe([TOPIC_LOCATION, TOPIC_DEST]);
});

client.on("message", async (topic, message) => {
    try {
        const payload = JSON.parse(message.toString());

        if (topic === TOPIC_DEST) {
            destination = payload;
            console.log("📍 Destination set:", destination);
        }

        if (topic === TOPIC_LOCATION && destination) {
            const current = payload;
            console.log("📡 Location:", current);

            const res = await axios.get(GH_URL, {
                params: {
                    point: `${current.lat},${current.lon}`,
                    point: `${destination.lat},${destination.lon}`,
                    vehicle: "foot",
                    locale: "en"
                }
            });

            const instr = res.data.paths[0].instructions[0];
            const steps = Math.round(instr.distance / 0.75);

            const navMsg = {
                action: instr.sign === 0 ? "forward" : "turn",
                steps,
                turn:
                    instr.sign === -2 ? "left" :
                        instr.sign === 2 ? "right" : null,
                text: instr.text
            };

            client.publish(TOPIC_INSTR, JSON.stringify(navMsg));
            console.log("➡️ Instruction sent:", navMsg);
        }
    } catch (err) {
        console.error("❌ Error:", err.message);
    }
});
