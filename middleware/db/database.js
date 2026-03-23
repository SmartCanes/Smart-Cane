import axios from "axios";
import pool from "./dbClient.js";

const REVERSE_GEOCODE_URL = "https://reverse.icane.org/reverse";

const DEFAULT_GUARDIAN_SETTINGS = {
    allow_location: 1,
    push_notifications: 1,
    email_notifications: 1,
    sms_alerts: 1,
    two_factor_enabled: 0
};

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

// ---GPS--------
const GPS_SAVE_INTERVAL_MS = 15000;
const GPS_MIN_DISTANCE_METERS = 15;

const lastGpsCache = new Map();

function toRadians(value) {
    return (value * Math.PI) / 180;
}

function distanceMeters(lat1, lng1, lat2, lng2) {
    const R = 6371000;

    const dLat = toRadians(lat2 - lat1);
    const dLng = toRadians(lng2 - lng1);

    const a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRadians(lat1)) *
        Math.cos(toRadians(lat2)) *
        Math.sin(dLng / 2) *
        Math.sin(dLng / 2);

    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

function shouldSaveGps(serial, lat, lng, timestamp) {
    const previous = lastGpsCache.get(serial);

    if (!previous) {
        return true;
    }

    const elapsed = timestamp - previous.timestamp;
    if (elapsed >= GPS_SAVE_INTERVAL_MS) {
        return true;
    }

    const moved = distanceMeters(previous.lat, previous.lng, lat, lng);
    return moved >= GPS_MIN_DISTANCE_METERS;
}

export async function upsertLastLocationIfNeeded(serial, gps) {
    if (!pool || !serial || !gps) {
        return null;
    }

    const lat = toNumber(gps.lat);
    const lng = toNumber(gps.lng);
    const sats = toNumber(gps.sats);
    const hdop = toNumber(gps.hdop);
    const gpsStatus = toNumber(gps.status) ?? 0;
    const fix = gps.fix === true;

    if (!fix || lat === null || lng === null) {
        return null;
    }

    const now = Date.now();

    if (!shouldSaveGps(serial, lat, lng, now)) {
        return { skipped: true };
    }

    const [result] = await pool.execute(
        `
        INSERT INTO device_last_location_tbl
        (
            device_id,
            lat,
            lng,
            sats,
            fix_status,
            hdop,
            gps_status,
            recorded_at,
            updated_at
        )
        SELECT
            d.device_id,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            NOW(),
            NOW()
        FROM device_tbl d
        WHERE d.device_serial_number = ?
        ON DUPLICATE KEY UPDATE
            lat = VALUES(lat),
            lng = VALUES(lng),
            sats = VALUES(sats),
            fix_status = VALUES(fix_status),
            hdop = VALUES(hdop),
            gps_status = VALUES(gps_status),
            recorded_at = VALUES(recorded_at),
            updated_at = VALUES(updated_at)
        `,
        [lat, lng, sats, fix ? 1 : 0, hdop, gpsStatus, serial]
    );

    lastGpsCache.set(serial, {
        lat,
        lng,
        timestamp: now
    });

    return result;
}

export async function getLastDeviceLocation(serial) {
    if (!pool || !serial) {
        return null;
    }

    const [rows] = await pool.execute(
        `
        SELECT
            dl.lat,
            dl.lng,
            dl.sats,
            dl.fix_status,
            dl.hdop,
            dl.gps_status,
            dl.recorded_at
        FROM device_last_location_tbl dl
        JOIN device_tbl d ON d.device_id = dl.device_id
        WHERE d.device_serial_number = ?
        LIMIT 1
        `,
        [serial]
    );

    return rows.length ? rows[0] : null;
}


// ---Routes---
const ROUTE_STATUSES = new Set(["pending", "active", "completed", "cleared", "failed"]);

function normalizeCoordinate(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
}

function extractDestinationFromRoute(routePayload) {
    const path = Array.isArray(routePayload?.paths) ? routePayload.paths[0] : null;
    const coords = path?.points?.coordinates;

    if (Array.isArray(coords) && coords.length > 0) {
        const last = coords[coords.length - 1];
        if (Array.isArray(last) && last.length >= 2) {
            return {
                lat: normalizeCoordinate(last[1]),
                lng: normalizeCoordinate(last[0])
            };
        }
    }

    return { lat: null, lng: null };
}

export async function saveRouteRequest(serial, payload = {}) {
    if (!pool || !serial) {
        return null;
    }

    const destination = Array.isArray(payload?.to) ? payload.to : [];
    const lat = normalizeCoordinate(destination[0]);
    const lng = normalizeCoordinate(destination[1]);

    if (lat === null || lng === null) {
        return null;
    }

    const guardianId = payload?.guardianId ?? null;
    const destinationLabel = payload?.label ?? null;

    const sql = `
        INSERT INTO device_route_tbl (
            device_id,
            guardian_id,
            destination_lat,
            destination_lng,
            destination_label,
            status,
            requested_at,
            completed_at,
            cleared_at,
            route_geojson,
            provider_payload,
            distance_meters,
            duration_ms,
            updated_at
        )
        SELECT
            d.device_id,
            ?,
            ?,
            ?,
            ?,
            'pending',
            NOW(),
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            NOW()
        FROM device_tbl d
        WHERE d.device_serial_number = ?
        ON DUPLICATE KEY UPDATE
            guardian_id = VALUES(guardian_id),
            destination_lat = VALUES(destination_lat),
            destination_lng = VALUES(destination_lng),
            destination_label = VALUES(destination_label),
            status = 'pending',
            requested_at = NOW(),
            completed_at = NULL,
            cleared_at = NULL,
            route_geojson = NULL,
            provider_payload = NULL,
            distance_meters = NULL,
            duration_ms = NULL,
            updated_at = NOW();
    `;

    return pool.execute(sql, [guardianId, lat, lng, destinationLabel, serial]);
}

export async function saveRouteResponse(serial, payload = {}) {
    if (!pool || !serial) {
        return null;
    }

    const routePayload = payload?.route;
    if (!routePayload) {
        return null;
    }

    const path = Array.isArray(routePayload?.paths) ? routePayload.paths[0] : null;
    const geoJson = path?.points || null;
    const destination = extractDestinationFromRoute(routePayload);

    const distanceMeters = normalizeCoordinate(path?.distance ?? routePayload?.distance);
    const durationMs = normalizeCoordinate(path?.time ?? routePayload?.time);

    const sql = `
        INSERT INTO device_route_tbl (
            device_id,
            guardian_id,
            destination_lat,
            destination_lng,
            destination_label,
            route_geojson,
            provider_payload,
            status,
            distance_meters,
            duration_ms,
            requested_at,
            completed_at,
            cleared_at,
            updated_at
        )
        SELECT
            d.device_id,
            dr.guardian_id,
            ?,
            ?,
            ?,
            ?,
            ?,
            'active',
            ?,
            ?,
            COALESCE(dr.requested_at, NOW()),
            NULL,
            NULL,
            NOW()
        FROM device_tbl d
        LEFT JOIN device_route_tbl dr ON dr.device_id = d.device_id
        WHERE d.device_serial_number = ?
        ON DUPLICATE KEY UPDATE
            destination_lat = VALUES(destination_lat),
            destination_lng = VALUES(destination_lng),
            destination_label = VALUES(destination_label),
            route_geojson = VALUES(route_geojson),
            provider_payload = VALUES(provider_payload),
            status = 'active',
            distance_meters = VALUES(distance_meters),
            duration_ms = VALUES(duration_ms),
            completed_at = NULL,
            cleared_at = NULL,
            updated_at = NOW();
    `;

    const routeGeoJsonString = geoJson ? JSON.stringify(geoJson) : null;
    const providerPayloadString = routePayload ? JSON.stringify(routePayload) : null;

    return pool.execute(sql, [
        destination.lat,
        destination.lng,
        payload?.destinationLabel ?? null,
        routeGeoJsonString,
        providerPayloadString,
        distanceMeters,
        durationMs,
        serial
    ]);
}

export async function updateRouteStatus(serial, status, guardianId = null) {
    if (!pool || !serial || !ROUTE_STATUSES.has(status)) {
        return null;
    }

    const sql = `
        UPDATE device_route_tbl dr
        JOIN device_tbl d ON d.device_id = dr.device_id
        SET
            dr.guardian_id = COALESCE(?, dr.guardian_id),
            dr.status = ?,
            dr.updated_at = NOW(),
            dr.completed_at = CASE WHEN ? = 'completed' THEN NOW() ELSE NULL END,
            dr.cleared_at = CASE WHEN ? = 'cleared' THEN NOW() ELSE NULL END
        WHERE d.device_serial_number = ?;
    `;

    return pool.execute(sql, [guardianId, status, status, status, serial]);
}

export async function getRouteBySerial(serial) {
    if (!pool || !serial) {
        return null;
    }

    const [rows] = await pool.execute(
        `
      SELECT
        dr.route_id,
        dr.device_id,
        dr.guardian_id,
        dr.destination_label,
        dr.destination_lat,
        dr.destination_lng,
        dr.route_geojson,
        dr.provider_payload,
        dr.status,
        dr.distance_meters,
        dr.duration_ms,
        dr.requested_at,
        dr.completed_at,
        dr.cleared_at,
        dr.updated_at,
        d.device_serial_number
      FROM device_route_tbl dr
      INNER JOIN device_tbl d
        ON d.device_id = dr.device_id
      WHERE d.device_serial_number = ?
      LIMIT 1
    `,
        [serial]
    );

    return rows.length ? rows[0] : null;
}

// ---Emergency contacts---
export async function getEmergencyContactsBySerial(serial) {
    if (!pool || !serial) {
        return [];
    }

    const [rows] = await pool.execute(
        `
        SELECT
            g.contact_number AS contactNumber,
            g.guardian_id AS guardianId,
            dg.assigned_at AS assignedAt
        FROM device_guardian_tbl dg
        JOIN device_tbl d ON d.device_id = dg.device_id
        JOIN guardian_tbl g ON g.guardian_id = dg.guardian_id
        WHERE d.device_serial_number = ?
          AND dg.is_emergency_contact = 1
          AND g.contact_number IS NOT NULL
          AND g.contact_number != ''
        ORDER BY dg.assigned_at DESC
        `,
        [serial]
    );

    return rows || [];
}

function buildRouteSnapshot(routeRow) {
    if (!routeRow) return null;

    return {
        routeId: routeRow.route_id,
        deviceId: routeRow.device_id,
        guardianId: routeRow.guardian_id,
        serial: routeRow.device_serial_number,
        destination: {
            label: routeRow.destination_label ?? null,
            lat:
                routeRow.destination_lat != null
                    ? Number(routeRow.destination_lat)
                    : null,
            lng:
                routeRow.destination_lng != null
                    ? Number(routeRow.destination_lng)
                    : null
        },
        status: routeRow.status ?? null,
        distanceMeters:
            routeRow.distance_meters != null
                ? Number(routeRow.distance_meters)
                : null,
        durationMs:
            routeRow.duration_ms != null
                ? Number(routeRow.duration_ms)
                : null,
        requestedAt: routeRow.requested_at ?? null,
        completedAt: routeRow.completed_at ?? null,
        clearedAt: routeRow.cleared_at ?? null,
        updatedAt: routeRow.updated_at ?? null,
        routeGeoJson: routeRow.route_geojson ?? null,
        providerPayload: routeRow.provider_payload ?? null
    };
}

export async function saveRouteHistoryLog(serial, options = {}) {
    if (!pool || !serial) {
        return null;
    }

    try {
        const routeRow = await getRouteBySerial(serial);

        if (!routeRow) {
            console.warn(`[RouteHistory] No route found for serial: ${serial}`);
            return null;
        }

        const {
            status = routeRow.status ?? "active",
            message = null,
            guardianId = routeRow.guardian_id ?? null
        } = options;

        const finalMessage =
            message ||
            (status === "active"
                ? `Route started to ${routeRow.destination_label || "selected destination"}`
                : status === "completed"
                    ? "Device reached the destination"
                    : status === "cleared"
                        ? "Route was cleared"
                        : status === "failed"
                            ? "Route failed"
                            : `Route updated to ${status}`);

        const metadataJson = buildRouteSnapshot({
            ...routeRow,
            status
        });

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
        VALUES (?, ?, ?, ?, ?, ?, NOW())
      `,
            [
                routeRow.device_id,
                guardianId,
                "route",
                status,
                finalMessage,
                JSON.stringify(metadataJson)
            ]
        );

        return result;
    } catch (err) {
        console.error(
            `[RouteHistory] Failed to save route history for ${serial}:`,
            err.message
        );
        return null;
    }
}

export async function deleteRouteBySerial(serial) {
    if (!pool || !serial) {
        return null;
    }

    try {
        const [result] = await pool.execute(
            `
        DELETE dr
        FROM device_route_tbl dr
        INNER JOIN device_tbl d
          ON d.device_id = dr.device_id
        WHERE d.device_serial_number = ?
      `,
            [serial]
        );

        return result;
    } catch (err) {
        console.error(`[Route] Failed to delete route for ${serial}:`, err.message);
        return null;
    }
}

// ---Guardian settings---
const toBoolInt = (value, fallback = 0) => {
    if (value === null || value === undefined) return fallback;
    if (typeof value === "boolean") return value ? 1 : 0;
    if (typeof value === "number") return value ? 1 : 0;
    if (typeof value === "string") {
        const lowered = value.trim().toLowerCase();
        if (["1", "true", "yes", "on"].includes(lowered)) return 1;
        if (["0", "false", "no", "off"].includes(lowered)) return 0;
    }
    return fallback;
};

export async function getGuardianSettings(guardianId) {
    if (!pool || !guardianId) {
        return { ...DEFAULT_GUARDIAN_SETTINGS };
    }

    try {
        const [rows] = await pool.execute(
            `
            SELECT
                allow_location,
                push_notifications,
                email_notifications,
                sms_alerts,
                two_factor_enabled,
                updated_at
            FROM guardian_settings_tbl
            WHERE guardian_id = ?
            LIMIT 1
            `,
            [guardianId]
        );

        if (!rows || !rows.length) {
            return { ...DEFAULT_GUARDIAN_SETTINGS };
        }

        const row = rows[0];
        return {
            allow_location: toBoolInt(row.allow_location, 1),
            push_notifications: toBoolInt(row.push_notifications, 1),
            email_notifications: toBoolInt(row.email_notifications, 1),
            sms_alerts: toBoolInt(row.sms_alerts, 1),
            two_factor_enabled: toBoolInt(row.two_factor_enabled, 0),
            updated_at: row.updated_at || null
        };
    } catch (error) {
        console.error(`[DB] Failed to fetch guardian settings for ${guardianId}:`, error?.message || error);
        return { ...DEFAULT_GUARDIAN_SETTINGS };
    }
}

export async function upsertGuardianSettings(guardianId, settings = {}) {
    if (!pool || !guardianId) {
        return null;
    }

    const allowLocation = toBoolInt(settings.allow_location ?? settings.allowLocation, DEFAULT_GUARDIAN_SETTINGS.allow_location);
    const pushNotifications = toBoolInt(settings.push_notifications ?? settings.pushNotifications, DEFAULT_GUARDIAN_SETTINGS.push_notifications);
    const emailNotifications = toBoolInt(settings.email_notifications ?? settings.emailNotifications, DEFAULT_GUARDIAN_SETTINGS.email_notifications);
    const smsAlerts = toBoolInt(settings.sms_alerts ?? settings.smsAlerts, DEFAULT_GUARDIAN_SETTINGS.sms_alerts);
    const twoFactor = toBoolInt(settings.two_factor_enabled ?? settings.twoFactorEnabled, DEFAULT_GUARDIAN_SETTINGS.two_factor_enabled);

    const sql = `
        INSERT INTO guardian_settings_tbl (
            guardian_id,
            allow_location,
            push_notifications,
            email_notifications,
            sms_alerts,
            two_factor_enabled,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, NOW())
        ON DUPLICATE KEY UPDATE
            allow_location = VALUES(allow_location),
            push_notifications = VALUES(push_notifications),
            email_notifications = VALUES(email_notifications),
            sms_alerts = VALUES(sms_alerts),
            two_factor_enabled = VALUES(two_factor_enabled),
            updated_at = NOW();
    `;

    try {
        const [result] = await pool.execute(sql, [
            guardianId,
            allowLocation,
            pushNotifications,
            emailNotifications,
            smsAlerts,
            twoFactor
        ]);

        return result;
    } catch (error) {
        console.error(`[DB] Failed to upsert guardian settings for ${guardianId}:`, error?.message || error);
        return null;
    }
}



// PUSH SUBSCRIPTIONS
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