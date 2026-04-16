self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

const buildNotificationOptions = (payload = {}) => ({
  body: payload.body || payload.message || "Important iCane update received.",
  icon: payload.icon || "/icane.svg",
  badge: payload.badge || payload.icon || "/icane.svg",
  tag: payload.tag || "icane-alert",
  silent: payload.silent === true ? true : false,
  renotify: true,
  requireInteraction: Boolean(payload.requireInteraction),
  vibrate: payload.vibrate || [300, 150, 300],
  data: {
    path: payload.path || "/notifications"
  }
});

self.addEventListener("push", (event) => {
  let payload = {};

  try {
    payload = event.data ? event.data.json() : {};
  } catch (error) {
    payload = {
      title: "iCane Alert",
      message: event.data?.text() || "Important iCane update received."
    };
  }

  const title = payload.title || "iCane Alert";
  const options = buildNotificationOptions(payload);

  event.waitUntil(
    (async () => {
      // If any iCane client is already visible, skip showing a redundant push.
      try {
        const clientList = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
        const hasVisibleClient = clientList.some((client) => client.visibilityState === "visible");

        if (hasVisibleClient) {
          return;
        }
      } catch (err) {
        // If visibility check fails, fall through and show the notification.
        console.warn("SW visibility check failed:", err?.message || err);
      }

      return self.registration.showNotification(title, options);
    })()
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type !== "SHOW_NOTIFICATION") {
    return;
  }

  const payload = event.data.payload || {};
  const title = payload.title || "iCane Alert";
  const options = buildNotificationOptions(payload);

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const path = event.notification.data?.path || "/notifications";
  const targetUrl = new URL(path, self.location.origin).href;

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if ("focus" in client) {
            if ("navigate" in client) {
              client.navigate(targetUrl);
            }

            return client.focus();
          }
        }

        if (self.clients.openWindow) {
          return self.clients.openWindow(targetUrl);
        }

        return undefined;
      })
  );
});
