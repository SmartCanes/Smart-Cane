import mqtt from "mqtt";
import { TOPIC_LOCATION, TOPIC_STATUS } from "../mqtt/topic.js";
import { getIO } from "./socket.js";

export function initMqttWsBridge() {
    const io = getIO();

    const MQTT_URL = process.env.MQTT_BROKER || "mqtt://localhost:1883";
    const mqttClient = mqtt.connect(MQTT_URL);

    mqttClient.on("connect", () => {
        console.log("Connected to MQTT broker");
        mqttClient.subscribe(TOPIC_LOCATION, (err) => {
            if (err) console.error("Failed to subscribe:", err);
            else console.log("Subscribed to topic:", TOPIC_LOCATION);
        });
        mqttClient.subscribe(TOPIC_STATUS, (err) => {
            if (err) console.error("Failed to subscribe:", err);
            else console.log("Subscribed to topic:", TOPIC_STATUS);
        });
    });

    mqttClient.on("message", (topic, message) => {
        const msg = message.toString();
        if (topic === TOPIC_LOCATION) {
            try {
                const data = JSON.parse(msg);
                io.emit("location", data);
            } catch (e) {
                console.error("Invalid JSON received:", msg);
            }
        }
        if (topic === TOPIC_STATUS) {
            try {
                const data = JSON.parse(msg);
                io.emit("status", data);
            } catch (e) {
                console.error("Invalid JSON received:", msg);
            }
        }
    });

    io.on("connection", (socket) => {
        console.log("Socket.IO client connected:", socket.id);

        socket.on("disconnect", () => {
            console.log("Socket.IO client disconnected:", socket.id);
        });
    });

    console.log("Socket IO is ready running at https://localhost:4000");
}
