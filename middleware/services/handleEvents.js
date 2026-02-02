import axios from "axios";
export const subscriptions = new Map(); // Map<serial, Set<ws>>
export const wsToSerial = new Map(); // Map<ws, serial>

export async function handleEvent(ws, data) {
    const { event, serial, payload } = data;

    if (!serial) return;

    if (event === "subscribe") {
        // --- Remove previous subscription if exists ---
        const oldSerial = wsToSerial.get(ws);
        if (oldSerial && oldSerial !== serial) {
            const oldSet = subscriptions.get(oldSerial);
            if (oldSet) {
                oldSet.delete(ws);
                if (oldSet.size === 0) subscriptions.delete(oldSerial);
            }
            const clientIP = ws._socket?.remoteAddress || "unknown"; // get IP
            console.log(
                `[${new Date().toISOString()}] [WS] Client ${clientIP} switched from serial "${oldSerial}" to "${serial}"`
            );
        }

        // --- Add new subscription ---
        if (!subscriptions.has(serial)) subscriptions.set(serial, new Set());
        subscriptions.get(serial).add(ws);
        wsToSerial.set(ws, serial);

        const clientIP = ws._socket?.remoteAddress || "unknown";
        const count = subscriptions.get(serial).size;

        console.log(
            `[${new Date().toISOString()}] [WS] Client ${clientIP} subscribed to serial "${serial}" (total subscribers: ${count})`
        );

        ws.send(JSON.stringify({ event: "subscribed", serial }));
        return;
    }

    if (event === "location") {
        const clients = subscriptions.get(serial);
        if (!clients) return;

        for (const client of clients) {
            client.send(JSON.stringify({ event: "location", serial, payload }));
        }
    }
}

export function cleanup(ws) {
    // Remove ws from subscriptions map
    const serial = wsToSerial.get(ws);
    if (serial) {
        const set = subscriptions.get(serial);
        if (set) {
            set.delete(ws);
            if (set.size === 0) subscriptions.delete(serial);
        }
        wsToSerial.delete(ws);
    }
}

async function getRoute(from, to) {

    const url =
        `http://localhost:8989/route?point=${from[0]},${from[1]}&point=${to[0]},${to[1]}&profile=foot&points_encoded=false`;

    const res = await axios.get(url);

    return res.data.paths[0].points.coordinates;
}
