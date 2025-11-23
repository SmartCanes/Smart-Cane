import mqtt from "mqtt";
import { TOPIC_LOCATION } from "../mqtt/topic.js";
import { getIO } from "./socket.js";

export function initMqttWsBridge() {
    const io = getIO();

    const MQTT_URL = process.env.MQTT_BROKER || "mqtt://localhost:1883";
    const mqttClient = mqtt.connect(MQTT_URL);

    mqttClient.on("connect", () => {
        console.log("Connected to MQTT broker");
        mqttClient.subscribe(TOPIC_LOCATION);
    });

    mqttClient.on("message", (topic, message) => {
        const data = message.toString();
        if (topic === TOPIC_LOCATION) {
            io.emit("location", data);
        }
    });

    io.on("connection", (socket) => {
        console.log("Socket.IO client connected:", socket.id);

        socket.on("disconnect", () => {
            console.log("Socket.IO client disconnected:", socket.id);
        });
    });

    console.log("Socket IO is ready running at ws://localhost:4000");
}
