import webpush from "web-push";

webpush.setVapidDetails(
    process.env.VAPID_SUBJECT,
    process.env.VAPID_PUBLIC_KEY,
    process.env.VAPID_PRIVATE_KEY
);

const DEFAULT_ICON = "/icane.svg";
const subscriptionsByGuardian = new Map();

function normalizeSubscription(subscription) {
    if (
        !subscription ||
        !subscription.endpoint ||
        !subscription.keys?.p256dh ||
        !subscription.keys?.auth
    ) {
        return null;
    }

    return {
        endpoint: subscription.endpoint,
        keys: {
            p256dh: subscription.keys.p256dh,
            auth: subscription.keys.auth
        }
    };
}

function isSameSubscription(a, b) {
    return a?.endpoint === b?.endpoint;
}

function getAllGuardianIds() {
    return Array.from(subscriptionsByGuardian.keys());
}

function buildLocationText(payload = {}) {
    const lat = payload?.lat ?? payload?.location?.lat;
    const lng = payload?.lng ?? payload?.location?.lng;
    const label = payload?.location?.label;

    if (label) return label;
    if (typeof lat === "number" && typeof lng === "number") {
        return `${lat}, ${lng}`;
    }

    return "Location unavailable";
}

function buildIncidentNotification(event, serial, payload = {}) {
    const isFall = event === "fallDetected";
    const title = isFall ? "Fall detected" : "Emergency alert";
    const locationText = buildLocationText(payload);
    const source = payload?.source || "device";

    return {
        title,
        body: `${serial}: ${isFall ? "Possible fall" : "SOS triggered"}. ${locationText}. Source: ${source}.`,
        icon: DEFAULT_ICON,
        tag: `${event}-${serial}`,
        path: `/devices/${serial}?tab=alerts`,
        requireInteraction: true
    };
}

function buildRouteNotification(type, serial, payload = {}) {
    const destinationLabel =
        payload?.destination?.label || payload?.label || payload?.destinationLabel;
    const destinationCoords = payload?.destination || {};
    const destinationText = destinationLabel
        ? destinationLabel
        : buildLocationText({
            location: {
                label: null,
                lat: destinationCoords.lat,
                lng: destinationCoords.lng
            }
        });

    const metaByType = {
        active: {
            title: "Route started",
            message: `Navigation started for ${serial} to ${destinationText}.`
        },
        completed: {
            title: "Destination reached",
            message: `${serial} reached ${destinationText}.`
        },
        cleared: {
            title: "Route cleared",
            message: `${serial} route was cleared.`
        }
    };

    const meta = metaByType[type];
    if (!meta) return null;

    return {
        title: meta.title,
        body: meta.message,
        icon: DEFAULT_ICON,
        tag: `route-${serial}`,
        path: `/devices/${serial}?tab=routes`
    };
}

async function sendPayloadToGuardians(targetGuardianIds, payload) {
    const guardianIds = [...new Set(targetGuardianIds)].filter(Boolean);
    if (!guardianIds.length) return;

    await Promise.allSettled(
        guardianIds.map((guardianId) => sendPushToGuardian(guardianId, payload))
    );
}

export async function savePushSubscription(guardianId, subscription) {
    const normalized = normalizeSubscription(subscription);
    if (!guardianId || !normalized) {
        throw new Error("Invalid guardianId or subscription");
    }

    const current = subscriptionsByGuardian.get(guardianId) || [];
    const exists = current.some((item) => isSameSubscription(item, normalized));

    if (!exists) {
        current.push(normalized);
        subscriptionsByGuardian.set(guardianId, current);
    }

    return { success: true };
}

export async function removePushSubscription(guardianId, endpoint) {
    if (!guardianId || !endpoint) return { success: false };

    const current = subscriptionsByGuardian.get(guardianId) || [];
    const filtered = current.filter((item) => item.endpoint !== endpoint);

    subscriptionsByGuardian.set(guardianId, filtered);
    return { success: true };
}

export async function sendPushToGuardian(guardianId, payload) {
    const subscriptions = subscriptionsByGuardian.get(guardianId) || [];
    if (!subscriptions.length) return;

    const message = JSON.stringify(payload);
    const expiredEndpoints = [];

    await Promise.allSettled(
        subscriptions.map(async (subscription) => {
            try {
                await webpush.sendNotification(subscription, message);
            } catch (error) {
                if (error?.statusCode === 404 || error?.statusCode === 410) {
                    expiredEndpoints.push(subscription.endpoint);
                } else {
                    console.error("Push send failed:", error.message);
                }
            }
        })
    );

    if (expiredEndpoints.length) {
        const filtered = subscriptions.filter(
            (sub) => !expiredEndpoints.includes(sub.endpoint)
        );
        subscriptionsByGuardian.set(guardianId, filtered);
    }
}

export async function sendPushToManyGuardians(guardianIds, payload) {
    await sendPayloadToGuardians(guardianIds, payload);
}

export async function sendIncidentPushNotifications({ event, serial, payload }) {
    const notification = buildIncidentNotification(event, serial, payload);
    if (!notification) return;

    const explicitGuardianId = payload?.guardian_id ?? payload?.guardianId;
    const targets = explicitGuardianId ? [explicitGuardianId] : getAllGuardianIds();

    await sendPayloadToGuardians(targets, notification);
}

export async function sendRoutePushNotifications({ type, serial, payload }) {
    const notification = buildRouteNotification(type, serial, payload);
    if (!notification) return;

    const explicitGuardianId = payload?.guardian_id ?? payload?.guardianId;
    const targets = explicitGuardianId ? [explicitGuardianId] : getAllGuardianIds();

    await sendPayloadToGuardians(targets, notification);
}