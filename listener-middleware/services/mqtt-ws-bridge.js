import { MQTT_TOPICS } from "../config/mqtt.js";
import { getIO } from "./socket.js";
import { MqttService } from "./mqttService.js";

export function initMqttWsBridge() {
    const io = getIO();

    const mqttService = new MqttService();
    mqttService.connect();

    Object.entries(MQTT_TOPICS).forEach(([key, topic]) => {
        const socketEvent = key.replace("TOPIC_", "").toLowerCase();

        mqttService.on(topic, (data) => {
            io.emit(socketEvent, data);
            console.log(`Emitted ${socketEvent} event via Socket.IO`, data);
        });
    });

    io.on("connection", (socket) => {
        console.log("Socket.IO client connected:", socket.id);
        socket.on("disconnect", () => {
            console.log("Socket.IO client disconnected:", socket.id);
        });
    });

    console.log("✅ MQTT → WebSocket bridge is ready");
}
