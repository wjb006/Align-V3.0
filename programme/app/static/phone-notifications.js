(() => {
  'use strict';
  const el = id => document.getElementById(id);
  let registration, config, subscription;
  async function api(path, body) {
    const response = await fetch('/api/phone-push/' + path, {
      method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
      headers: body ? {'Content-Type': 'application/json'} : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(response.status === 401 ? 'Sign in to Align first, then return to this page.' : data.error || 'Please try again.');
    return data;
  }
  function buttons(busy = false) {
    el('enable').disabled = busy || !config?.configured || !registration;
    el('test').disabled = busy || !subscription;
    el('disable').disabled = busy || !subscription;
  }
  async function action(fn) {
    buttons(true);
    try { await fn(); } catch (error) { el('status').textContent = error.message; }
    finally { buttons(); }
  }
  el('enable').onclick = () => action(async () => {
    // Ask directly in the click handler, before network or service worker awaits.
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') throw new Error('Notifications are blocked. Allow them in your phone or browser settings, then try again.');
    const bytes = Uint8Array.from(atob(config.public_key.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
    subscription = await registration.pushManager.getSubscription();
    subscription ||= await registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: bytes});
    await api('subscribe', {subscription: subscription.toJSON()});
    el('status').textContent = 'This device is registered. Send a test to check delivery.';
  });
  el('test').onclick = () => action(async () => {
    await api('test', {endpoint: subscription.endpoint});
    el('status').textContent = 'The push provider accepted the test. Check your phone’s notifications; acceptance alone does not confirm delivery.';
  });
  el('disable').onclick = () => action(async () => {
    await api('unsubscribe', {endpoint: subscription.endpoint});
    await subscription.unsubscribe();
    subscription = null;
    el('status').textContent = 'Notifications disabled on this device.';
  });
  async function start() {
    config = await api('status');
    el('check').textContent = config.last_check ? 'Last scheduler check: ' + formatDisplayDateTime(config.last_check) : 'The scheduler has not checked this account yet.';
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) throw new Error('On iPhone, open the installed Align Home Screen app to enable notifications. This browser does not currently support push notifications.');
    const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    if (ios && !navigator.standalone && !matchMedia('(display-mode: standalone)').matches) throw new Error('Open Align from your Home Screen icon, then tap the bell. Notifications cannot be enabled from an ordinary iPhone browser tab.');
    registration = await navigator.serviceWorker.register('/service-worker.js');
    await registration.update();
    registration = await navigator.serviceWorker.ready;
    subscription = await registration.pushManager.getSubscription();
    el('status').textContent = !config.configured ? 'The server setup is not finished yet. Nothing has been enabled.' : subscription ? 'This browser has a subscription. Tap Enable to register it with your signed-in Align account, then send a test.' : 'Ready to enable phone notifications.';
    buttons();
  }
  start().catch(error => { el('status').textContent = error.message; });
})();
