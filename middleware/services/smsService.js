import axios from "axios";
import { getLastDeviceLocation, getEmergencyContactsBySerial } from "../db/database.js";

const semaphoreApiKey = process.env.SEMAPHORE_API_KEY;
const semaphoreSender = "iCane";
const semaphoreEndpoint =
    process.env.SEMAPHORE_ENDPOINT || "https://api.semaphore.co/api/v4/messages";

function normalizeSemaphorePhoneNumber(value) {
    if (!value) return null;

    const digits = String(value).replace(/\D/g, "");

    if (/^09\d{9}$/.test(digits)) return digits;
    if (/^9\d{9}$/.test(digits)) return `0${digits}`;
    if (/^63\d{10}$/.test(digits)) return `0${digits.slice(2)}`;

    return null;
}

const toNumbers = (process.env.SEMAPHORE_TO || "")
    .split(",")
    .map((n) => normalizeSemaphorePhoneNumber(n))
    .filter(Boolean);

const hasSemaphoreConfig = Boolean(semaphoreApiKey);

function toNumber(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
}

function buildCoordsText(payload = {}) {
    const label = payload?.location?.label || payload?.label || null;
    const lat = toNumber(payload?.lat ?? payload?.location?.lat);
    const lng = toNumber(payload?.lng ?? payload?.location?.lng);

    if (label) return label;
    if (lat !== null && lng !== null) return `${lat.toFixed(5)},${lng.toFixed(5)}`;
    return null;
}

async function withLastLocation(serial, payload = {}) {
    const coordsText = buildCoordsText(payload);
    if (coordsText) return { payload, coordsText };

    try {
        const last = await getLastDeviceLocation(serial);
        const lat = toNumber(last?.lat);
        const lng = toNumber(last?.lng);

        if (lat === null || lng === null) {
            return { payload, coordsText: null };
        }

        const location = payload?.location || {
            lat,
            lng,
            label: payload?.label || null
        };

        return {
            payload: {
                ...payload,
                lat: payload?.lat ?? lat,
                lng: payload?.lng ?? lng,
                location,
                lastLocationRecordedAt: last?.recorded_at || null
            },
            coordsText: buildCoordsText({ lat, lng, location })
        };
    } catch (error) {
        console.error("[Semaphore] Failed to fetch last location:", error?.message || error);
        return { payload, coordsText: null };
    }
}

function buildSmsBody(event, serial, coordsText) {
    const prefix = event === "fallDetected" ? "FALL" : "SOS";
    return coordsText ? `${prefix} ${serial} ${coordsText}` : `${prefix} ${serial} location unknown`;
}

export async function sendIncidentSms({ event, serial, payload = {} }) {
    if (!hasSemaphoreConfig) {
        console.warn("[Semaphore] Missing API key; SMS not sent.");
        return [];
    }

    const { coordsText } = await withLastLocation(serial, payload);
    const body = buildSmsBody(event, serial, coordsText);

    const emergencyRows = await getEmergencyContactsBySerial(serial);
    const emergencyNumbers = emergencyRows
        .map((row) => normalizeSemaphorePhoneNumber(row?.contactNumber))
        .filter(Boolean);

    const targets = [...new Set([...emergencyNumbers, ...toNumbers])];

    if (!targets.length) {
        console.warn("[Semaphore] No target numbers found for SMS.");
        return [];
    }

    const results = await Promise.allSettled(
        targets.map((number) => {
            const form = new URLSearchParams({
                apikey: semaphoreApiKey,
                number,
                message: body
            });

            // if (semaphoreSender) {
            //     form.append("sendername", semaphoreSender);
            // }

            return axios.post(semaphoreEndpoint, form.toString(), {
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            });
        })
    );

    results.forEach((result, idx) => {
        const to = targets[idx];

        if (result.status === "fulfilled") {
            console.log(`[Semaphore] SMS sent to ${to}`, result.value.data);
        } else {
            console.error(
                `[Semaphore] SMS failed to ${to}:`,
                result.reason?.response?.data || result.reason?.message || result.reason
            );
        }
    });

    return results;
}