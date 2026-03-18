import pool from "./dbClient.js";

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

function buildIncidentLog(type, serial, payload) {
    const lat = payload?.lat;
    const lng = payload?.lng;
    const source = payload?.source ?? "unknown";

    const hasLocation =
        typeof lat === "number" && typeof lng === "number";

    switch (type) {
        case "emergencyTriggered":
            return {
                activityType: "emergency",
                status: "triggered",
                message: hasLocation
                    ? `Emergency button activated. Source: ${source}. Location: ${lat}, ${lng}`
                    : `Emergency button activated. Source: ${source}. Location unavailable`
            };

        case "fallDetected":
            return {
                activityType: "fall",
                status: "triggered",
                message: hasLocation
                    ? `Possible fall detected. Source: ${source}. Location: ${lat}, ${lng}`
                    : `Possible fall detected. Source: ${source}. Location unavailable`
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

    const incident = buildIncidentLog(type, serial, payload);

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
                    event: type,
                    serial,
                    payload
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