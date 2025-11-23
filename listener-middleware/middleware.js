require('dotenv').config();
const mqtt = require("mqtt");
const axios = require("axios");
const WebSocket = require("ws");
const express = require("express");

const MQTT_BROKER = process.env.MQTT_BROKER || "mqtt://mosquitto:1883";
const GH_URL = process.env.GH_URL || "http://graphhopper:8989/route";

const TOPIC_LOCATION = "cane/location";
const TOPIC_DEST = "guardian/destination";
const TOPIC_INSTR = "cane/instructions";

let destination = null;
let viaPoints = []; // optional intermediate points

// ------------------ MQTT SETUP ------------------
const client = mqtt.connect(MQTT_BROKER);

client.on("connect", () => {
    console.log("✅ Connected to MQTT broker");
    client.subscribe([TOPIC_LOCATION, TOPIC_DEST], { qos: 1 }, (err) => {
        if (err) console.error("❌ MQTT subscription error:", err);
    });
});

client.on("error", (err) => console.error("❌ MQTT error:", err));

client.on("message", async (topic, message) => {
    try {
        const payload = JSON.parse(message.toString());
        if (topic === TOPIC_DEST) return handleDestination(payload);
        if (topic === TOPIC_LOCATION && destination) return handleLocation(payload);
    } catch (err) {
        console.error("❌ MQTT message error:", err.message);
    }
});

// ------------------ WEBSOCKET SETUP ------------------
const wss = new WebSocket.Server({ port: 4001 });
function broadcast(data) {
    wss.clients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify(data));
        }
    });
}

// ------------------ HTTP API SETUP ------------------
const app = express();
app.use(express.json());

/**
 * GET /route?fromLat=&fromLon=&toLat=&toLon=&via=lat1,lon1;lat2,lon2
 */
app.get("/route", async (req, res) => {
    const { fromLat, fromLon, toLat, toLon, via } = req.query;
    if (!fromLat || !fromLon || !toLat || !toLon) {
        return res.status(400).json({ error: "Missing coordinates" });
    }

    const parsedVia = via ? parseViaPoints(via) : [];

    try {
        const instructions = await getFullInstructions(
            { lat: parseFloat(fromLat), lon: parseFloat(fromLon) },
            { lat: parseFloat(toLat), lon: parseFloat(toLon) },
            parsedVia
        );
        res.json(instructions);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.listen(4000, () => console.log("🌐 HTTP API running on port 4000"));

// ------------------ HANDLERS ------------------
function handleDestination(payload) {
    destination = payload.location || payload; // support optional structure
    viaPoints = payload.via || []; // optional via points array
    console.log("📍 Destination set:", destination, "Via points:", viaPoints);
}

async function handleLocation(current) {
    console.log("📡 Current location:", current);

    try {
        const instructions = await getFullInstructions(current, destination, viaPoints);
        if (!instructions?.length) return;

        // Take the **first step** for cane device
        const instr = instructions[0];

        // Publish to MQTT
        client.publish(TOPIC_INSTR, JSON.stringify(instr));

        // Broadcast all instructions via WebSocket
        broadcast({ type: "navigation", instructions, rawLocation: current });

        console.log("➡️ Step sent:", instr);
    } catch (err) {
        console.error("❌ Routing error:", err.message);
    }
}

// ------------------ HELPER FUNCTIONS ------------------

/**
 * Parse via points from query string format: "lat1,lon1;lat2,lon2"
 * @param {string} via
 * @returns {Array<{lat:number,lon:number}>}
 */
function parseViaPoints(via) {
    return via.split(";").map(p => {
        const [lat, lon] = p.split(",").map(Number);
        return { lat, lon };
    });
}

/**
 * Convert GraphHopper instructions to cane-friendly steps
 * @param {Object} from { lat, lon }
 * @param {Object} to { lat, lon }
 * @param {Array} via array of {lat, lon}
 * @returns {Promise<Array>} step-by-step instructions
 */
async function getFullInstructions(from, to, via = []) {
    const points = [from, ...via, to].map(p => `${p.lat},${p.lon}`);

    const res = await axios.get(GH_URL, {
        params: {
            point: points,
            vehicle: "foot",
            locale: "en",
            calc_points: true
        },
        timeout: 5000
    });

    const path = res.data.paths?.[0];
    if (!path || !path.instructions?.length) return [];

    // Map each GraphHopper instruction to cane-friendly format
    return path.instructions.map(instr => {
        const steps = Math.round(instr.distance / 0.75); // assuming 0.75m per step
        return {
            action: instr.sign === 0 ? "forward" : "turn",
            steps,
            turn: instr.sign === -2 ? "left" : instr.sign === 2 ? "right" : null,
            text: instr.text,
            distance: instr.distance,
            time: instr.time // milliseconds
        };
    });
}
