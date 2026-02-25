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


    const FORWARDED_EVENTS = new Set([
        "status",
        "location",
        "piStatus",
        "routeResponse",
        "destinationReached",
        "destinationCleared",
        "bluetoothDevices",
        "pairStatus",
        "unpairStatus",
        "connectStatus",
        "disconnectStatus",
        "noteDelivered"
    ]);

    console.log(`Received event "${event}" for serial "${serial}" with payload:`, payload);


    if (FORWARDED_EVENTS.has(event)) {
        const clients = subscriptions.get(serial);
        if (!clients) return;

        for (const c of clients)
            safeSend(c, { event, serial, payload });

        return;
    }


    if (event === "requestRoute") {
        if (!payload?.to) return;

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

    if (event === "scanBluetooth") {

        const piWs = serialToPi.get(serial);

        if (!piWs || piWs.readyState !== 1) {
            const clients = subscriptions.get(serial);
            if (clients)
                for (const c of clients)
                    safeSend(c, {
                        event: "bluetoothError",
                        serial,
                        payload: "Pi offline"
                    });

            return;
        }

        safeSend(piWs, {
            event: "scanBluetooth",
            serial,
            payload: payload || {}
        });

        console.log(`[BT] scanBluetooth forwarded to Pi ${serial}`);
        return;
    }

    if (event === "pairBluetooth") {
        if (!payload?.mac) return;

        const piWs = serialToPi.get(serial);

        if (!piWs || piWs.readyState !== 1) {
            const clients = subscriptions.get(serial);
            if (clients)
                for (const c of clients)
                    safeSend(c, {
                        event: "bluetoothPairError",
                        serial,
                        payload: "Pi offline"
                    });

            return;
        }

        safeSend(piWs, {
            event: "pairBluetooth",
            serial,
            payload: { mac: payload.mac }
        });

        console.log(`[BT] pairBluetooth forwarded to Pi ${serial} for ${payload.mac}`);
        return;
    }

    if (event === "unpairBluetooth") {
        if (!payload?.mac) return;

        const piWs = serialToPi.get(serial);

        if (!piWs || piWs.readyState !== 1) {
            const clients = subscriptions.get(serial);
            if (clients)
                for (const c of clients)
                    safeSend(c, {
                        event: "bluetoothUnpairError",
                        serial,
                        payload: "Pi offline"
                    });

            return;
        }

        safeSend(piWs, {
            event: "unpairBluetooth",
            serial,
            payload: { mac: payload.mac }
        });

        console.log(`[BT] unpairBluetooth forwarded to Pi ${serial} for ${payload.mac}`);
        return;
    }

    if (event === "connectBluetooth") {
        if (!payload?.mac) return;

        const piWs = serialToPi.get(serial);

        if (!piWs || piWs.readyState !== 1) {
            const clients = subscriptions.get(serial);
            if (clients)
                for (const c of clients)
                    safeSend(c, {
                        event: "bluetoothConnectError",
                        serial,
                        payload: "Pi offline"
                    });

            return;
        }

        safeSend(piWs, {
            event: "connectBluetooth",
            serial,
            payload: { mac: payload.mac }
        });

        console.log(`[BT] connectBluetooth forwarded to Pi ${serial} for ${payload.mac}`);
        return;
    }

    if (event === "disconnectBluetooth") {
        if (!payload?.mac) return;

        const piWs = serialToPi.get(serial);

        if (!piWs || piWs.readyState !== 1) {
            const clients = subscriptions.get(serial);
            if (clients)
                for (const c of clients)
                    safeSend(c, {
                        event: "bluetoothDisconnectError",
                        serial,
                        payload: "Pi offline"
                    });

            return;
        }

        safeSend(piWs, {
            event: "disconnectBluetooth",
            serial,
            payload: { mac: payload.mac }
        });

        console.log(`[BT] disconnectBluetooth forwarded to Pi ${serial} for ${payload.mac}`);
        return;
    }

    if (event === "clearDestination") {
        const piWs = serialToPi.get(serial);

        if (!piWs) {
            const clients = subscriptions.get(serial);
            if (clients)
                for (const c of clients)
                    safeSend(c, {
                        event: "routeError",
                        serial,
                        payload: "Pi offline"
                    });

            return;
        }

        safeSend(piWs, {
            event: "clearDestination",
            serial
        });

        console.log(`[NAV] clearDestination forwarded to Pi ${serial}`);
        return;
    }

    if (event === "note") {
        if (!payload?.message || !payload.message.trim()) {
            safeSend(ws, {
                event: "noteError",
                serial,
                payload: "Message cannot be empty"
            });
            return;
        }

        const piWs = serialToPi.get(serial);

        if (!piWs || piWs.readyState !== 1) {
            safeSend(ws, {
                event: "noteError",
                serial,
                payload: "Pi offline"
            });
            return;
        }

        safeSend(piWs, {
            event: "note",
            serial,
            payload: {
                message: payload.message.trim(),
                timestamp: Date.now()
            }
        });

        console.log(`[NOTE] forwarded to Pi ${serial}`);

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
