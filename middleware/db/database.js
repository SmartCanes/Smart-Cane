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