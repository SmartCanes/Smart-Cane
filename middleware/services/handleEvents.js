import { getDeviceConfig, updateDeviceConfig } from "../db/database.js";

export const subscriptions = new Map();   // serial -> Set<clientWs>
export const wsToSerial = new Map();      // clientWs -> serial
export const serialToPi = new Map();      // serial -> piWs

export const guardianSockets = new Map();
export const wsToGuardian = new Map();

const fallbackConfig = {
    FALL_DETECTION: {
        enabled: true,
        config: {
            fallConfirmationDelay: 3000
        }
    },

    OBSTACLE_DETECTION: {
        enabled: true,
        config: {
            obstacleDistanceThreshold: 300.0,
            obstacleFeedbackPattern: 0
        }
    },

    EDGE_DETECTION: {
        enabled: true,
        config: {
            stairSafetyDistance: 300
        }
    },

    VOICE_ENGINE: {
        enabled: true,
        config: {
            volume: 0.3,
            speechSpeed: 150
        }
    },

    VISUAL_RECOGNITION: {
        enabled: true,
        config: {
            recognitionInterval: 3000
        }
    },

    EMERGENCY_SYSTEM: {
        enabled: true,
        config: {
            emergencyTrigger: 3000,
            emergencyBuzzerDuration: 60000,
            emergencyBuzzerPattern: 100
        }
    },

    GPS_TRACKING: {
        enabled: true,
        config: {
        }
    }
};

function mergeDeviceConfig(existing = {}, partial = {}) {
    const result = { ...existing };

    for (const [key, value] of Object.entries(partial)) {
        if (
            value &&
            typeof value === "object" &&
            !Array.isArray(value) &&
            result[key] &&
            typeof result[key] === "object" &&
            !Array.isArray(result[key])
        ) {
            result[key] = mergeDeviceConfig(result[key], value);
        } else {
            result[key] = value;
        }
    }

    return result;
}

function mapSnapshotArrayToStoredConfig(payload) {
    const components = payload?.components || [];
    const mapped = {};

    for (const component of components) {
        const codeName = component?.codeName;
        if (!codeName) continue;

        mapped[codeName] = {
            enabled: component?.enabled ?? true,
            config: {
                ...(component?.config || {})
            }
        };
    }

    return mapped;
}

function broadcastToAllSubscribers(message) {
    for (const clients of subscriptions.values()) {
        for (const ws of clients) {
            safeSend(ws, message);
        }
    }
}

function broadcastGuardianPresence(guardianId, status) {
    broadcastToAllSubscribers({
        event: "guardianPresence",
        payload: {
            guardianId,
            status
        }
    });
}

function removeGuardianSocket(ws) {
    const guardianId = wsToGuardian.get(ws);
    if (!guardianId) return;

    const sockets = guardianSockets.get(guardianId);
    if (sockets) {
        sockets.delete(ws);

        if (sockets.size === 0) {
            guardianSockets.delete(guardianId);
            broadcastGuardianPresence(guardianId, false);
            console.log(`[Presence] Guardian ${guardianId} offline`);
        }
    }

    wsToGuardian.delete(ws);
}

async function sendDeviceConfig(ws, serial) {
    try {
        const configRecord = await getDeviceConfig(serial);
        const finalConfig = configRecord?.config_json || fallbackConfig;

        safeSend(ws, {
            event: "deviceConfig",
            serial,
            payload: finalConfig
        });
    } catch (e) {
        console.error(`Failed to fetch config for ${serial}:`, e.message);

        safeSend(ws, {
            event: "deviceConfig",
            serial,
            payload: fallbackConfig
        });
    }
}

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

    if (event === "guardian:join") {
        const { guardianId } = payload || {};

        if (!guardianId) return;

        if (!guardianSockets.has(guardianId)) {
            guardianSockets.set(guardianId, new Set());
        }

        const sockets = guardianSockets.get(guardianId);
        const wasOffline = sockets.size === 0;

        sockets.add(ws);
        wsToGuardian.set(ws, guardianId);

        if (wasOffline) {
            broadcastGuardianPresence(guardianId, true);
            console.log(`[Presence] Guardian ${guardianId} online`);
        }

        return;
    }

    if (event === "requestGuardianPresence") {
        safeSend(ws, {
            event: "guardianPresenceSnapshot",
            payload: {
                onlineGuardianIds: [...guardianSockets.keys()].map(Number)
            }
        });
        return;
    }

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
                event: "updateDeviceConfig",
                serial,
                payload: finalConfig
            });

            safeSend(ws, {
                event: "requestStatus",
                serial
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

        if (!subscriptions.has(serial)) {
            subscriptions.set(serial, new Set());
        }

        subscriptions.get(serial).add(ws);
        wsToSerial.set(ws, serial);

        const clientIP = ws._socket?.remoteAddress || "unknown";
        const count = subscriptions.get(serial).size;

        console.log(
            `[${new Date().toISOString()}] [WS] Client ${clientIP} subscribed to serial "${serial}" (total subscribers: ${count})`
        );

        safeSend(ws, { event: "subscribed", serial });
        await sendDeviceConfig(ws, serial);

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
                            raspberryPiStatus: "offline",
                            esp32Status: "offline",
                            emergency: false,
                            gpsStatus: 0,
                            obstacleDetectionStatus: false,
                            edgeDetectionStatus: false,
                            accelerometerStatus: false
                        }
                    });
                }
            }
        }
        return;
    }


    const FORWARDED_EVENTS = new Set([
        "status",
        "gps",
        "piStatus",
        "routeResponse",
        "destinationReached",
        "destinationCleared",
        "bluetoothDevices",
        "pairStatus",
        "unpairStatus",
        "connectStatus",
        "disconnectStatus",
        "noteDelivered",
        "demoModeUpdated",
        "scanStatus",
        "configSaved",
        "piConfigUpdated"
    ]);

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

    if (event === "getBluetoothState") {
        const piWs = serialToPi.get(serial);

        if (!piWs || piWs.readyState !== 1) {
            const clients = subscriptions.get(serial);
            if (clients) {
                for (const c of clients) {
                    safeSend(c, {
                        event: "bluetoothDevices",
                        serial,
                        payload: {
                            devices: [],
                            status: "error",
                            error: "Pi offline"
                        }
                    });
                }
            }

            return;
        }

        safeSend(piWs, {
            event: "getBluetoothState",
            serial,
            payload: payload || {}
        });

        console.log(`[BT] getBluetoothState forwarded to Pi ${serial}`);
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
        await sendDeviceConfig(ws, serial);
        return;
    }

    if (event === "updateDeviceConfig") {
        if (!payload?.components || !Array.isArray(payload.components)) return;

        try {
            const configRecord = await getDeviceConfig(serial);
            const currentConfig = configRecord?.config_json || fallbackConfig;

            const incomingDeviceConfig = mapSnapshotArrayToStoredConfig(payload);
            const mergedConfig = mergeDeviceConfig(currentConfig, incomingDeviceConfig);

            await updateDeviceConfig(serial, mergedConfig);
            console.log(payload);

            const piWs = serialToPi.get(serial);

            if (piWs && piWs.readyState === 1) {
                safeSend(piWs, {
                    event: "updateDeviceConfig",
                    serial,
                    payload
                });
            } else {
                safeSend(ws, {
                    event: "configError",
                    serial,
                    payload: "Pi offline"
                });
            }
        } catch (e) {
            console.error(`Failed to update device config for ${serial}:`, e.message);

            safeSend(ws, {
                event: "configError",
                serial,
                payload: "Failed to update device config"
            });
        }

        return;
    }

    if (event === "updatePiConfig") {
        if (!payload?.components || !Array.isArray(payload.components)) return;

        try {
            const configRecord = await getDeviceConfig(serial);
            const currentConfig = configRecord?.config_json || fallbackConfig;

            const incomingPiConfig = mapSnapshotArrayToStoredConfig(payload);
            const mergedConfig = mergeDeviceConfig(currentConfig, incomingPiConfig);

            await updateDeviceConfig(serial, mergedConfig);

            const piWs = serialToPi.get(serial);

            if (!piWs || piWs.readyState !== 1) {
                safeSend(ws, {
                    event: "piConfigError",
                    serial,
                    payload: "Pi offline"
                });
                return;
            }

            safeSend(piWs, {
                event: "updatePiConfig",
                serial,
                payload
            });
        } catch (e) {
            console.error(`Failed to update Pi config for ${serial}:`, e.message);

            safeSend(ws, {
                event: "piConfigError",
                serial,
                payload: "Failed to update Pi config"
            });
        }

        return;
    }

    if (event === "updateDemoMode") {
        const piWs = serialToPi.get(serial);

        if (!piWs || piWs.readyState !== 1) {
            const clients = subscriptions.get(serial);
            if (clients) {
                for (const c of clients) {
                    safeSend(c, {
                        event: "demoModeError",
                        serial,
                        payload: "Pi offline"
                    });
                }
            }
            return;
        }

        const enabled = payload?.enabled === true;

        console.log("[DEMO] incoming payload =", payload);
        console.log("[DEMO] parsed enabled =", enabled);

        safeSend(piWs, {
            event: "updateDemoMode",
            serial,
            payload: {
                enabled
            }
        });

        console.log(
            `[DEMO] updateDemoMode forwarded to Pi ${serial}: ${enabled}`
        );
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

    removeGuardianSocket(ws);

    for (const [s, piWs] of serialToPi.entries()) {
        if (piWs === ws) {
            serialToPi.delete(s);
            console.log(`[WS] Pi disconnected: ${s}`);

            const clients = subscriptions.get(s);
            if (clients) {
                for (const client of clients) {
                    safeSend(client, {
                        event: "status",
                        serial: s,
                        payload: {
                            esp32Status: "offline",
                            emergency: false,
                            fall: false,
                            obstacleDetectionStatus: false,
                            edgeDetectionStatus: false,
                            accelerometerStatus: false
                        }
                    });

                    safeSend(client, {
                        event: "piStatus",
                        serial: s,
                        payload: {
                            status: "offline"
                        }
                    });

                    safeSend(client, {
                        event: "gps",
                        serial: s,
                        payload: {
                            status: 0,
                            sats: 0,
                            fix: false,
                            hdop: null,
                            ready: false,
                            lat: null,
                            lng: null
                        }
                    });
                }
            }
        }
    }
}
