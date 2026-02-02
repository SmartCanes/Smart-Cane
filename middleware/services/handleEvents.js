import axios from "axios";

export const subscriptions = new Map();

export async function handleEvent(ws, data) {
    const { event, serial, payload } = data;

    if (!serial) return;

    if (event === "subscribe") {
        if (!subscriptions.has(serial))
            subscriptions.set(serial, new Set());

        subscriptions.get(serial).add(ws);

        ws.send(JSON.stringify({ event: "subscribed", serial }));
        return;
    }

    if (event === "location") {
        const clients = subscriptions.get(serial);

        if (!clients) return;

        for (const client of clients) {
            client.send(JSON.stringify({
                event: "location",
                serial,
                payload
            }));
        }
    }
}

export function cleanup(ws) {
    for (const set of subscriptions.values()) {
        set.delete(ws);
    }
}


// ================= GRAPHOPPER =================

async function getRoute(from, to) {

    const url =
        `http://localhost:8989/route?point=${from[0]},${from[1]}&point=${to[0]},${to[1]}&profile=foot&points_encoded=false`;

    const res = await axios.get(url);

    return res.data.paths[0].points.coordinates;
}
