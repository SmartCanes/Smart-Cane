import webPush from "web-push";
import { getPushSubscriptionsByGuardianOrSerial } from "../db/database.js";


// webPush.setVapidDetails(
//     "mailto:admin@yourdomain.com",
//     process.env.VAPID_PUBLIC_KEY,
//     process.env.VAPID_PRIVATE_KEY
// );

const buildPushPayload = ({ event, serial, payload }) => {
    if (event === "emergencyTriggered") {
        return {
            title: "Emergency Alert",
            body: `Emergency triggered for device ${serial}. Check live location immediately.`,
            icon: "/icane.svg",
            badge: "/icane.svg",
            tag: `emergency-${serial}`,
            requireInteraction: true,
            vibrate: [500, 200, 500, 200, 500],
            data: {
                path: `/dashboard/live-location?serial=${encodeURIComponent(serial)}`
            }
        };
    }

    if (event === "fallDetected") {
        return {
            title: "Fall Detected",
            body: `Possible fall detected for device ${serial}. Please check the user's status.`,
            icon: "/icane.svg",
            badge: "/icane.svg",
            tag: `fall-${serial}`,
            requireInteraction: true,
            vibrate: [300, 100, 300],
            data: {
                path: `/dashboard/notifications?serial=${encodeURIComponent(serial)}`
            }
        };
    }

    return {
        title: "Smart Cane Alert",
        body: `New event received from device ${serial}.`,
        icon: "/icane.svg",
        badge: "/icane.svg",
        tag: `event-${serial}`,
        requireInteraction: false,
        vibrate: [200, 100, 200],
        data: {
            path: "/dashboard/notifications"
        }
    };
};

export const sendIncidentPushNotifications = async ({ event, serial, payload }) => {
    const subscriptions = await getPushSubscriptionsByGuardianOrSerial(serial);

    if (!subscriptions?.length) {
        return;
    }

    const pushPayload = JSON.stringify(buildPushPayload({ event, serial, payload }));

    const results = await Promise.allSettled(
        subscriptions.map(async (item) => {
            const subscription = {
                endpoint: item.endpoint,
                keys: {
                    p256dh: item.p256dh,
                    auth: item.auth
                }
            };

            try {
                await webPush.sendNotification(subscription, pushPayload);
            } catch (error) {
                console.error("Push send failed:", error?.statusCode || error);

                if (error?.statusCode === 404 || error?.statusCode === 410) {
                    await deletePushSubscriptionByEndpoint(item.endpoint);
                }
            }
        })
    );

    return results;
};