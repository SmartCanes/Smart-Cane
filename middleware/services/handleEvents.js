export const subscriptions = new Map();   // serial -> Set<clientWs>
export const wsToSerial = new Map();      // clientWs -> serial
export const serialToPi = new Map();      // serial -> piWs

function safeSend(ws, msg) {
    if (!ws || ws.readyState !== 1) return;

    try {
        ws.send(JSON.stringify(msg));
    } catch (e) {
        console.error("safeSend failed:", e.message);
    }
}

export function handleEvent(ws, data) {
    const { event, serial, payload } = data;
    if (!serial) return;

    if (event === "register") {
        serialToPi.set(serial, ws);
        console.log(`[${new Date().toISOString()}] Pi registered: ${serial}`);
        return;
    }

    if (event === "subscribe") {
        const oldSerial = wsToSerial.get(ws);
        if (oldSerial && oldSerial !== serial) {
            const oldSet = subscriptions.get(oldSerial);
            if (oldSet) {
                oldSet.delete(ws);
                if (oldSet.size === 0) subscriptions.delete(oldSerial);
            }
            const clientIP = ws._socket?.remoteAddress || "unknown";
            console.log(
                `[${new Date().toISOString()}] [WS] Client ${clientIP} switched from serial "${oldSerial}" to "${serial}"`
            );
        }

        if (!subscriptions.has(serial)) subscriptions.set(serial, new Set());
        subscriptions.get(serial).add(ws);
        wsToSerial.set(ws, serial);

        const clientIP = ws._socket?.remoteAddress || "unknown";
        const count = subscriptions.get(serial).size;

        console.log(
            `[${new Date().toISOString()}] [WS] Client ${clientIP} subscribed to serial "${serial}" (total subscribers: ${count})`
        );

        safeSend(ws, { event: "subscribed", serial });
        return;
    }

    if (event === "requestStatus") {
        const piWs = serialToPi.get(serial);

        if (piWs && piWs.readyState === 1) {
            safeSend(piWs, { event: "requestStatus" });
            console.log(`Forwarding requestStatus to Pi ${serial}`);
        } else {
            const clients = subscriptions.get(serial);
            if (clients) {
                for (const client of clients) {
                    safeSend(client, {
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
                    });
                }
            }
        }
        return;
    }



    if (event === "status" || event === "location" || event === "piStatus") {
        const clients = subscriptions.get(serial);
        if (!clients) return;

        for (const c of clients)
            safeSend(c, { event, serial, payload });

        return;
    }


    // ---------- ROUTE REQUEST FROM FRONTEND ----------

    if (event === "requestRoute") {
        if (!payload?.from || !payload?.to) return;

        const piWs = serialToPi.get(serial);

        if (!piWs) {
            const clients = subscriptions.get(serial);
            if (clients)
                for (const c of clients)
                    safeSend(c, {
                        event: "routeError",
                        serial,
                        message: "Pi offline"
                    });

            return;
        }

        safeSend(piWs, {
            event: "requestRoute",
            serial,
            payload
        });

        console.log(`[Route] forwarded to Pi ${serial}`);
        return;
    }


    // ---------- ROUTE RESPONSE FROM PI ----------

    if (event === "routeResponse") {
        const clients = subscriptions.get(serial);
        if (!clients) return;

        for (const c of clients)
            safeSend(c, data);

        return;
    }
}

export function cleanup(ws) {

    const serial = wsToSerial.get(ws);
    if (serial) {
        const set = subscriptions.get(serial);
        if (set) {
            set.delete(ws);
            if (!set.size) subscriptions.delete(serial);
        }
        wsToSerial.delete(ws);
    }

    for (const [s, piWs] of serialToPi.entries()) {
        if (piWs === ws) {
            serialToPi.delete(s);
            console.log(`[WS] Pi disconnected: ${s}`);
        }
    }
}
