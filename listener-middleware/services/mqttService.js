import mqtt from "mqtt";
import { MQTT_URL, MQTT_TOPICS } from "../config/mqtt.js";
import EventEmitter from "events";

export class MqttService extends EventEmitter {
    constructor() {
        super();
        this.client = null;
        this.topics = Object.values(MQTT_TOPICS);
        this.mqttUrl = MQTT_URL;
        this.reconnectInterval = 5000;
    }

    connect() {
        this.client = mqtt.connect(this.mqttUrl);

        this.client.on("connect", () => {
            console.log("Connected to MQTT broker:", this.mqttUrl);
            this.subscribeTopics();
        });

        this.client.on("message", (topic, message) => this.handleMessage(topic, message));

        this.client.on("error", (err) => console.error("MQTT Error:", err));

        this.client.on("close", () => {
            console.warn("MQTT connection closed. Reconnecting in 5s...");
            setTimeout(() => this.connect(), this.reconnectInterval);
        });
    }

    subscribeTopics() {
        this.topics.forEach((topic) => {
            this.client.subscribe(topic, (err) => {
                if (err) console.error(`❌ Failed to subscribe ${topic}:`, err);
                else console.log(`📌 Subscribed to topic: ${topic}`);
            });
        });
    }

    handleMessage(topic, message) {
        let data;
        try {
            data = JSON.parse(message.toString());
        } catch (err) {
            return console.error("❌ Invalid JSON received on topic", topic, ":", message.toString());
        }

        this.emit(topic, data);
    }
}
