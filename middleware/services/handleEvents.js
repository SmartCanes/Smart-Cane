import axios from "axios";
export const subscriptions = new Map(); // Map<serial, Set<ws>>
export const wsToSerial = new Map(); // Map<ws, serial>
export const serialToEsp = new Map(); // Map<serial, espWs>

export async function handleEvent(ws, data) {
    const { event, serial, payload } = data;

    if (!serial) return;

    if (event === "register") {
        serialToEsp.set(serial, ws);
        console.log(`ESP32 registered: ${serial}`);
        return;
    }

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

    if (event === "requestStatus") {
        const espWs = serialToEsp.get(serial);
        if (espWs && espWs.readyState === 1) {
            espWs.send(JSON.stringify({ event: "requestStatus" }));
            console.log(`Forwarding requestStatus to ESP32 ${serial}`);
        } else {
            const clients = subscriptions.get(serial);
            if (clients) {
                for (const client of clients) {
                    client.send(
                        JSON.stringify({
                            event: "status",
                            serial,
                            payload: {
                                status: "offline",
                                emergency: false,
                                gpsStatus: 0,
                                ultrasonicStatus: false,
                                infraredStatus: false,
                                mpuStatus: false
                            }
                        })
                    );
                }
            }
        }
        return;
    }

    if (event === "status" || event === "location") {
        const clients = subscriptions.get(serial);
        if (!clients) return;

        for (const client of clients) {
            client.send(JSON.stringify({ event, serial, payload }));
        }
    }
}

export function cleanup(ws) {
    const serial = wsToSerial.get(ws);
    if (serial) {
        const set = subscriptions.get(serial);
        if (set) {
            set.delete(ws);
            if (set.size === 0) subscriptions.delete(serial);
        }
        wsToSerial.delete(ws);
    }

    for (const [serial, espWs] of serialToEsp.entries()) {
        if (espWs === ws) {
            serialToEsp.delete(serial);
            console.log(`[${new Date().toISOString()}] ESP32 disconnected: ${serial}`);
        }
    }
}

async function getRoute(from, to) {

    const url =
        `http://localhost:8989/route?point=${from[0]},${from[1]}&point=${to[0]},${to[1]}&profile=foot&points_encoded=false`;

    const res = await axios.get(url);

    return res.data.paths[0].points.coordinates;
}
