import axios from "axios";
import { getLastDeviceLocation, getEmergencyContactsBySerial } from "../db/database.js";

const iprogEndpoint =
    process.env.IPROG_SMS_ENDPOINT || "https://www.iprogsms.com/api/v1/sms_messages";
const iprogToken = process.env.IPROG_SMS_API_TOKEN || process.env.IPROG_SMS_TOKEN;

function normalizePhoneNumber(value) {
    if (!value) return null;

    const digits = String(value).replace(/\D+/g, "").trim();

    if (/^63\d{10}$/.test(digits)) return digits;
    if (/^09\d{9}$/.test(digits)) return `63${digits.slice(1)}`;
    if (/^9\d{9}$/.test(digits)) return `63${digits}`;

    return null;
}

const toNumbers = (process.env.IPROG_SMS_TO || "")
    .split(",")
    .map((n) => normalizePhoneNumber(n))
    .filter(Boolean);

const hasIprogConfig = Boolean(iprogToken && iprogEndpoint);

function toNumber(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
}

async function withLastLocation(serial, payload = {}) {
    const lat = toNumber(payload?.lat ?? payload?.location?.lat);
    const lng = toNumber(payload?.lng ?? payload?.location?.lng);
    const label = payload?.location?.label || payload?.label || null;

    if (lat !== null || lng !== null || label) {
        return { payload };
    }

    try {
        const last = await getLastDeviceLocation(serial);
        const lastLat = toNumber(last?.lat);
        const lastLng = toNumber(last?.lng);

        if (lastLat === null || lastLng === null) {
            return { payload };
        }

        const location = payload?.location || {
            lat: lastLat,
            lng: lastLng,
            label: payload?.label || null
        };

        return {
            payload: {
                ...payload,
                lat: payload?.lat ?? lastLat,
                lng: payload?.lng ?? lastLng,
                location,
                lastLocationRecordedAt: last?.recorded_at || null
            }
        };
    } catch (error) {
        console.error("[IprogSMS] Failed to fetch last location:", error?.message || error);
        return { payload };
    }
}

function buildSmsBody(event, serial, payload = {}) {
    const lat = toNumber(payload?.lat ?? payload?.location?.lat);
    const lng = toNumber(payload?.lng ?? payload?.location?.lng);
    const label = payload?.location?.label || payload?.label || null;

    const hasCoords = lat !== null && lng !== null;
    const mapLink = hasCoords
        ? `https://maps.google.com/?q=${lat.toFixed(5)},${lng.toFixed(5)}`
        : null;

    const website = "https://icane.org";

    if (event === "fallDetected") {
        if (label) {
            return `iCane Alert: A fall was detected for device ${serial}. Please check on the user immediately. Reported location: ${label}. More info: ${website}`;
        }

        if (mapLink) {
            return `iCane Alert: A fall was detected for device ${serial}. Please check on the user immediately. Last known location: ${mapLink}. More info: ${website}`;
        }

        return `iCane Alert: A fall was detected for device ${serial}. Please check on the user immediately. Location is currently unavailable. More info: ${website}`;
    }

    if (label) {
        return `iCane SOS Alert: The user triggered an SOS from device ${serial}. Immediate assistance may be needed. Reported location: ${label}. More info: ${website}`;
    }

    if (mapLink) {
        return `iCane SOS Alert: The user triggered an SOS from device ${serial}. Immediate assistance may be needed. Last known location: ${mapLink}. More info: ${website}`;
    }

    return `iCane SOS Alert: The user triggered an SOS from device ${serial}. Immediate assistance may be needed. Location is currently unavailable. More info: ${website}`;
}

export async function sendIncidentSms({ event, serial, payload = {} }) {
    if (!hasIprogConfig) {
        console.warn("[IprogSMS] Missing endpoint or API token; SMS not sent.");
        return [];
    }

    const { payload: enrichedPayload } = await withLastLocation(serial, payload);
    const body = buildSmsBody(event, serial, enrichedPayload);

    console.log(`[IprogSMS] Prepared SMS for ${serial}:`, body);

    const emergencyRows = await getEmergencyContactsBySerial(serial);
    const emergencyNumbers = emergencyRows
        .map((row) => normalizePhoneNumber(row?.contactNumber))
        .filter(Boolean);


    const targets = [...new Set([...emergencyNumbers, ...toNumbers])];

    if (!targets.length) {
        console.warn("[IprogSMS] No target numbers found for SMS.");
        return [];
    }

    const results = await Promise.allSettled(
        targets.map((phone_number) =>
            axios.post(
                iprogEndpoint,
                {
                    api_token: iprogToken,
                    phone_number,
                    message: body
                },
                {
                    headers: {
                        "Content-Type": "application/json"
                    }
                }
            )
        )
    );

    results.forEach((result, idx) => {
        const to = targets[idx];

        if (result.status === "fulfilled") {
            console.log(`[IprogSMS] SMS sent to ${to}`, result.value?.data);
        } else {
            console.error(
                `[IprogSMS] SMS failed to ${to}:`,
                result.reason?.response?.data || result.reason?.message || result.reason
            );
        }
    });

    return results;
}