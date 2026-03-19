import axios from "axios";
import pool from "./dbClient.js";

const REVERSE_GEOCODE_URL = "https://reverse.icane.org/reverse";

const cleanPart = (text) => (typeof text === "string" ? text.trim() : "");

const formatLocationLabel = (feature) => {
    const geocoding = feature?.properties?.geocoding;

    const candidates = [
        cleanPart(geocoding?.name),
        cleanPart(geocoding?.locality),
        cleanPart(geocoding?.admin?.level10),
        cleanPart(geocoding?.city)
    ];

    const parts = candidates.filter(
        (part, index, array) => part && array.indexOf(part) === index
    );

    return parts.length > 0 ? parts.join(", ") : null;
};

const toNumber = (value) => {
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
};

export const getLocationByCoords = async (lat, lon) => {
    return axios.get(REVERSE_GEOCODE_URL, {
        params: {
            lat,
            lon,
            format: "geocodejson",
            addressdetails: 1,
            zoom: 17
        },
        timeout: 5000
    });
};

async function resolveLocationDetails(latValue, lngValue) {
    const lat = toNumber(latValue);
    const lng = toNumber(lngValue);

    if (lat === null || lng === null) {
        return { label: null, coords: null };
    }

    try {
        const response = await getLocationByCoords(lat, lng);

        const feature = response?.data?.features?.[0];
        const label = formatLocationLabel(feature);

        return {
            label,
            coords: { lat, lng }
        };
    } catch (error) {
        console.warn(`[Location] Failed to resolve ${lat},${lng}:`, error.message);

        return {
            label: null,
            coords: { lat, lng }
        };
    }
}

export async function updateDeviceConfig(serial, configJson) {
    if (!pool) {
        console.warn("Database is not initialized");
        return null;
    }

    const [rows] = await pool.execute(
        `INSERT INTO device_config_tbl (device_id, config_json, updated_at)
         SELECT device_id, ?, NOW()
         FROM device_tbl
         WHERE device_serial_number = ?
         ON DUPLICATE KEY UPDATE
             config_json = VALUES(config_json),
             updated_at = NOW()`,
        [JSON.stringify(configJson), serial]
    );

    return rows;
}
export async function getDeviceConfig(serial) {
    if (!pool) {
        console.warn("Database is not initialized");
        return null;
    }

    const [rows] = await pool.execute(
        `SELECT dc.config_json
         FROM device_config_tbl dc
         JOIN device_tbl d ON d.device_id = dc.device_id
         WHERE d.device_serial_number = ?
         LIMIT 1`,
        [serial]
    );

    return rows.length ? rows[0] : null;
}

const formatIncidentMessage = ({
    type,
    locationLabel,
    coords,
    timestamp
}) => {
    const hasCoords =
        coords && typeof coords.lat === "number" && typeof coords.lng === "number";

    const locationText = locationLabel
        ? locationLabel
        : hasCoords
            ? `${coords.lat}, ${coords.lng}`
            : "Location unavailable";

    const time = timestamp ? new Date(timestamp) : null;
    const timeText =
        time && !Number.isNaN(time.getTime())
            ? new Intl.DateTimeFormat("en-US", {
                dateStyle: "medium",
                timeStyle: "short"
            }).format(time)
            : null;

    const title =
        type === "emergencyTriggered"
            ? "Emergency alert"
            : "Possible fall detected";

    return timeText
        ? `Last location: ${locationText}\n ${timeText}`
        : `Last location: ${locationText}`;
};

async function buildIncidentLog(type, serial, payload) {
    const location = await resolveLocationDetails(payload?.lat, payload?.lng);
    const recordedAt = new Date().toISOString();

    switch (type) {
        case "emergencyTriggered":
            return {
                activityType: "emergency",
                status: "triggered",
                message: formatIncidentMessage({
                    type,
                    locationLabel: location.label,
                    coords: location.coords,
                    timestamp: recordedAt
                }),
                location,
                recordedAt
            };

        case "fallDetected":
            return {
                activityType: "fall",
                status: "triggered",
                message: formatIncidentMessage({
                    type,
                    locationLabel: location.label,
                    coords: location.coords,
                    timestamp: recordedAt
                }),
                location,
                recordedAt
            };

        default:
            return null;
    }
}

export async function saveIncidentLog(type, serial, payload) {
    if (!pool) {
        console.warn("Database is not initialized");
        return null;
    }

    const incident = await buildIncidentLog(type, serial, payload);

    if (!incident) {
        return null;
    }

    if (!serial) {
        console.warn(`[DB] Missing serial for incident type: ${type}`);
        return null;
    }

    try {
        const guardianId = payload?.guardian_id ?? null;

        const [result] = await pool.execute(
            `
            INSERT INTO device_logs_tbl
            (
                device_id,
                guardian_id,
                activity_type,
                status,
                message,
                metadata_json,
                created_at
            )
            SELECT
                d.device_id,
                ?,
                ?,
                ?,
                ?,
                ?,
                NOW()
            FROM device_tbl d
            WHERE d.device_serial_number = ?
            `,
            [
                guardianId,
                incident.activityType,
                incident.status,
                incident.message,
                JSON.stringify({
                    location: {
                        label: incident.location?.label ?? null,
                        lat: incident.location?.coords?.lat ?? null,
                        lng: incident.location?.coords?.lng ?? null
                    },
                    timestamp: payload?.timestamp ?? null,
                    source: payload?.source ?? null
                }),
                serial
            ]
        );

        if (result.affectedRows === 0) {
            console.warn(`[DB] No device found for serial: ${serial}`);
            return null;
        }

        return result;
    } catch (err) {
        console.error(`[DB] Failed to save incident log for ${type} ${serial}:`, err.message);
        return null;
    }
}

const toRows = (result) => {
    if (Array.isArray(result)) return result[0] || [];
    if (result?.rows) return result.rows;
    return result || [];
};

export const getPushSubscriptionsByGuardianOrSerial = async (guardianOrSerial) => {
    if (!guardianOrSerial) return [];

    const sql = `
        SELECT endpoint, p256dh, auth, guardian_id AS guardianId, serial
        FROM push_subscriptions
        WHERE serial = ? OR guardian_id = ?
    `;

    const result = await db.query(sql, [guardianOrSerial, guardianOrSerial]);
    return toRows(result);
};

export const deletePushSubscriptionByEndpoint = async (endpoint) => {
    if (!endpoint) return;

    const sql = `
        DELETE FROM push_subscriptions
        WHERE endpoint = ?
    `;

    await db.query(sql, [endpoint]);
};

export const upsertPushSubscription = async ({
    endpoint,
    p256dh,
    auth,
    guardianId = null,
    serial = null
}) => {
    if (!endpoint || !p256dh || !auth) {
        throw new Error("endpoint, p256dh and auth are required");
    }

    const sql = `
        INSERT INTO push_subscriptions (endpoint, p256dh, auth, guardian_id, serial)
        VALUES (?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
            p256dh = VALUES(p256dh),
            auth = VALUES(auth),
            guardian_id = VALUES(guardian_id),
            serial = VALUES(serial)
    `;

    await db.query(sql, [endpoint, p256dh, auth, guardianId, serial]);
};