const VAPID_PUBLIC_KEY =
  "BPj0XvDQY5jPkWttJcyA-HghDx5gndbFWrB4-ILF9gaNgg0zL0j7OqXIZ99073jOoON5YnjOhXEhgmW7ryYJXuI";

let registrationPromise;

export async function registerNotifications() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    throw new Error("Push notifications are not supported by this browser.");
  }

  if (!window.isSecureContext) {
    throw new Error("Notifications require HTTPS or localhost.");
  }

  if (Notification.permission === "denied") {
    throw new Error("Allow notifications in your browser site settings.");
  }

  if (Notification.permission === "default") {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      throw new Error("Please allow notifications.");
    }
  }

  registrationPromise ??= navigator.serviceWorker.register("/sw.js");
  const registration = await registrationPromise;

  await navigator.serviceWorker.ready;

  let subscription = await registration.pushManager.getSubscription();

  if (!subscription) {
    const keyBytes = Uint8Array.from(
      atob(VAPID_PUBLIC_KEY.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(VAPID_PUBLIC_KEY.length / 4) * 4, "=")),
      (char) => char.charCodeAt(0)
    );

    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: keyBytes,
    });
  }

  return { registration, subscription };
}

export async function showSOSNotification(alert) {
  const { registration } = await registerNotifications();

  await registration.showNotification("🚨 ConvoyConnect SOS", {
    body: `${alert.rider_name}: ${alert.message}`,
    tag: `convoyconnect-sos-${alert.id}`,
    icon: "/favicon.ico",
    data: { url: window.location.href },
    requireInteraction: true,
  });
}
