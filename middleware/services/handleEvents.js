import { getDeviceConfig, updateDeviceConfig } from "../db/database.js";

export const subscriptions = new Map();   // serial -> Set<clientWs>
export const wsToSerial = new Map();      // clientWs -> serial
export const serialToPi = new Map();      // serial -> piWs

// const fallbackConfig = {
//     fallAngleThreshold: 10.0,
//     fallConfirmationDelay: 3000,
//     obstacleDistanceThreshold: 100.0,
//     pointDownAngle: 30.0,
//     edgeBeepMin: 400,
//     edgeBeepMax: 708,
//     edgeContinuous: 709,
//     volumeLevel: 0.3,
//     speechSpeed: 150,
//     speakingVoice: "f5",

//     enableFallDetection: true,
//     enableEdgeDetection: true,
//     enableObstacleDetection: true,
//     enableGPS: true
// };

const fallbackConfig = {
    FALL_DETECTION: {
        config: {
            enabled: true,
            fallAngleThreshold: 10.0,
            fallConfirmationDelay: 3000
        }
    },

    OBSTACLE_DETECTION: {
        config: {
            enabled: true,
            obstacleDistanceThreshold: 100.0,
            measurementInterval: 1000,
        }
    },

    EDGE_DETECTION: {
        config: {
            enabled: true,
            edgeBeepMin: 400,
            edgeBeepMax: 708,
            edgeContinuous: 709,
            pointDownAngle: 30.0
        }
    },

    VOICE_ENGINE: {
        config: {
            enabled: true,
            volume: 0.3,
            speechSpeed: 150,
            voiceType: "en-f5"
        }
    },

    VISUAL_RECOGNITION: {
        config: {
            enabled: true,
            alertType: "COMBINED",
            recognitionInterval: 3000,
        }
    },

    GPS_TRACKING: {
        config: {
            enabled: true
        }
    }
};

function safeSend(ws, msg) {
    if (!ws || ws.readyState !== 1) return;

    try {
        ws.send(JSON.stringify(msg));
    } catch (e) {
        console.error("safeSend failed:", e.message);
    }
}

export async function handleEvent(ws, data) {
    const { event, serial, payload } = data;

    if (!serial) return;

    if (event === "register") {

        serialToPi.set(serial, ws);

        console.log(`[${new Date().toISOString()}] Pi registered: ${serial}`);

        try {
            let configRecord = await getDeviceConfig(serial);

            const finalConfig =
                configRecord && configRecord.config_json
                    ? configRecord.config_json
                    : fallbackConfig;

            safeSend(ws, {
                event: "updateDeviceState",
                serial,
                payload: finalConfig
            });

        } catch (e) {
            console.error(`Failed to fetch config for ${serial}:`, e.message);
        }

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

    if (event === "requestDeviceConfig") {
        try {
            const devices = await getDeviceConfig(serial);

            if (!devices) {
                safeSend(ws, {
                    event: "deviceConfig",
                    payload: fallbackConfig
                });

                return;
            }

            console.log(devices.config_json);

            safeSend(ws, {
                event: "deviceConfig",
                payload: devices.config_json
            });

        } catch (e) {
            console.error("Failed to send device config:", e.message);

            safeSend(ws, {
                event: "deviceConfigError",
                message: "Failed to fetch device config"
            });
        }

        return;
    }

    if (event === "updateDeviceConfig") {

        if (!payload) return;

        try {
            // const result = await updateDeviceConfig(serial, payload);

            console.log(result)
            // console.log(`[CONFIG] updated in database for ${serial}`);

            const piWs = serialToPi.get(serial);

            if (piWs && piWs.readyState === 1) {
                safeSend(piWs, {
                    event: "updateDeviceConfig",
                    serial,
                    payload
                });
            }

            const clients = subscriptions.get(serial);

            if (clients) {
                for (const client of clients) {
                    safeSend(client, {
                        event: "deviceConfigUpdated",
                        serial,
                        payload
                    });
                }
            }

        } catch (e) {
            console.error(`Failed to update config for ${serial}:`, e.message);
        }

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
