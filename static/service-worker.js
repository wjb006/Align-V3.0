const BUILD = 156;
const ASSET_VERSION = `${BUILD}-v41`;

const SHELL_CACHE = `align-v13-shell-${ASSET_VERSION}`;
const API_CACHE = `align-v13-api-${ASSET_VERSION}`;

const SHELL_ASSETS = [
  '/',

  '/index.html',

  `/styles.css?v=${ASSET_VERSION}`,
  `/owner-builder.css?v=${ASSET_VERSION}`,

  `/dates.js?v=${ASSET_VERSION}`,
  `/offline-store.js?v=${ASSET_VERSION}`,
  `/icloud.js?v=${ASSET_VERSION}`,
  `/builder-fields.js?v=${ASSET_VERSION}`,
  `/builder-runtime.js?v=${ASSET_VERSION}`,
  `/journey-breakdown.js?v=${ASSET_VERSION}`,
  `/personal-planner.js?v=${ASSET_VERSION}`,
  `/travel-assets.js?v=${ASSET_VERSION}`,
  `/app.js?v=${ASSET_VERSION}`,
  `/build152.js?v=${ASSET_VERSION}`,
  `/post-event-travel.js?v=${ASSET_VERSION}`,

  `/manifest.json?v=${ASSET_VERSION}`,

  '/icon.svg',

  '/icons/align-180.png',
  '/icons/align-192.png',
  '/icons/align-512.png',
  '/icons/align-maskable-512.png',

  '/journey-icons/arrival.png',
  '/journey-icons/walking.png',
  '/journey-icons/bus.png',
  '/journey-icons/train.png',

];

async function fetchWithTimeout(request, timeoutMs = 3500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(request, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function precacheShell() {
  const cache = await caches.open(SHELL_CACHE);
  const failures = [];

  // A failed optional asset does NOT fail the whole worker installation because
  // one optional file failed to cache. An installed worker can then report the
  // exact missing file in Offline diagnostics instead of Safari silently leaving
  // the page uncontrolled forever.
  for (const asset of SHELL_ASSETS) {
    try {
      const request = new Request(asset, { cache: 'reload' });
      const response = await fetchWithTimeout(request, 5000);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await cache.put(request, response.clone());
      if (asset === '/index.html') await cache.put('/', response.clone());
    } catch (error) {
      failures.push({ asset, error: String(error?.message || error) });
    }
  }

  // Persist install failures in the cache so diagnostics can expose them after
  // activation. This tiny response is local-only and never leaves the device.
  await cache.put('/__align_sw_install_report__', new Response(JSON.stringify({ build: BUILD, failures }), {
    headers: { 'Content-Type': 'application/json' },
  }));
}

self.addEventListener('install', event => {
  event.waitUntil(precacheShell().then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keep = new Set([SHELL_CACHE, API_CACHE]);
    const keys = await caches.keys();
    await Promise.all(keys
      .filter(key => key.startsWith('align-') && !keep.has(key))
      .map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});

function markOfflineResponse(response) {
  const headers = new Headers(response.headers);
  headers.set('X-Align-Offline-Cache', '1');
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function networkFirstApi(request) {
  const cache = await caches.open(API_CACHE);
  try {
    const response = await fetchWithTimeout(request, 12000);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return markOfflineResponse(cached);
    throw error;
  }
}

async function navigationResponse(request, event) {
  const cache = await caches.open(SHELL_CACHE);
  const url = new URL(request.url);
  const isBetaGate = ['/beta-login','/beta-login.html','/beta-invite','/beta-invite.html','/beta-forgot','/beta-forgot.html','/beta-reset','/beta-reset.html','/beta-terms','/beta-terms.html','/beta-welcome','/beta-welcome.html'].includes(url.pathname);
  const isRoot = url.pathname === '/' || url.pathname === '/index.html';
  const cached = (await cache.match(request)) || (isRoot ? ((await cache.match('/')) || (await cache.match('/index.html'))) : null);

  // Current Build 151: onboarding/auth pages are never allowed to overwrite the cached
  // app root. This prevents a transient tunnel delay from visually sending a
  // signed-in user back through Login -> Terms -> Welcome again.
  try {
    const networkRequest = new Request(request, { cache: 'no-store' });
    const response = await fetchWithTimeout(networkRequest, isBetaGate ? 8000 : 5000);
    if (response.ok) {
      await cache.put(request, response.clone());
      if (isRoot) {
        await cache.put('/', response.clone());
        await cache.put('/index.html', response.clone());
      }
    }
    return response;
  } catch (_) {
    if (cached) return cached;
    return Response.error();
  }
}

async function cacheFirstAsset(request) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetchWithTimeout(request, 3000);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

async function liveAsset(request) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const response = await fetchWithTimeout(new Request(request, { cache: 'no-store' }), 5000);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (_) {
    const cached = await cache.match(request);
    if (cached) return cached;
    return Response.error();
  }
}

async function diagnostics() {
  const shell = await caches.open(SHELL_CACHE);
  const api = await caches.open(API_CACHE);
  const shellMissing = [];
  for (const asset of SHELL_ASSETS) {
    if (!(await shell.match(asset))) shellMissing.push(asset);
  }
  let installFailures = [];
  try {
    const report = await shell.match('/__align_sw_install_report__');
    if (report) installFailures = (await report.json()).failures || [];
  } catch (_) {}
  const apiRequests = await api.keys();
  return {
    build: BUILD,
    shellCache: SHELL_CACHE,
    apiCache: API_CACHE,
    shellReady: shellMissing.length === 0,
    shellMissing,
    installFailures,
    apiUrls: apiRequests.map(request => request.url),
  };
}

self.addEventListener('message', event => {
  if (event.data?.type === 'ALIGN_SHOW_NOTIFICATION') {
    const title = String(event.data.title || 'Align').slice(0, 120);
    const body = String(event.data.body || '').slice(0, 500);
    const tag = String(event.data.tag || 'align-update').slice(0, 120);
    event.waitUntil(self.registration.showNotification(title, {
      body, tag, icon: ['/journey-icons/walking.png', '/journey-icons/bus.png', '/journey-icons/train.png'].includes(event.data.icon) ? event.data.icon : '/icon.svg', badge: '/icon.svg',
      data: { url: event.data.url === '/transport' ? '/transport' : '/' },
    }));
    return;
  }
  if (event.data?.type === 'ALIGN_SKIP_WAITING') {
    self.skipWaiting();
    return;
  }
  if (event.data?.type === 'ALIGN_CLEAR_PRIVATE') {
    event.waitUntil(caches.delete(API_CACHE));
    return;
  }
  if (event.data?.type !== 'ALIGN_DIAGNOSTICS') return;
  event.waitUntil((async () => {
    const result = await diagnostics().catch(error => ({
      build: BUILD,
      shellReady: false,
      shellMissing: [],
      installFailures: [],
      apiUrls: [],
      error: String(error?.message || error),
    }));
    if (event.ports?.[0]) event.ports[0].postMessage(result);
    else if (event.source) event.source.postMessage({ type: 'ALIGN_DIAGNOSTICS_RESULT', result });
  })());
});

self.addEventListener('push', event => {
  let data = {};
  try { data = event.data?.json() || {}; } catch (_) { /* Always display a safe fallback. */ }
  event.waitUntil(self.registration.showNotification('Align', {
    body: data.tag === 'align-test' ? 'Phone notifications are connected.' : 'You have a reminder. Open Align to see the details.',
    tag: String(data.tag || 'align-reminder').slice(0, 100),
    icon: '/icons/align-192.png', badge: '/icons/align-192.png',
    data: { url: '/#home' },
  }));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const candidate = new URL(event.notification.data?.url || '/', self.location.origin);
  const target = candidate.origin === self.location.origin ? candidate.href : self.location.origin + '/';
  event.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windows => {
    const existing = windows.find(window => window.url.startsWith(self.location.origin));
    if (existing) return existing.focus().then(() => existing.navigate(target));
    return clients.openWindow(target);
  }));
});

self.addEventListener('fetch', event => {
  const request = event.request;
    if (request.method !== 'GET') {
      if(new URL(request.url).origin===self.location.origin && new URL(request.url).pathname.startsWith('/api/') && (['PUT','DELETE'].includes(request.method)||/^\/api\/(?:shifts|sections|annual-leave|personal\/refresh-travel)(?:\/|$)/.test(new URL(request.url).pathname))) {
        event.respondWith((async()=>{const response=await fetch(request);if(response.ok)await caches.delete(API_CACHE);return response;})());
      }
      return;
    }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith('/api/')) {
    const offlineSafe = url.pathname === '/api/bootstrap' || url.pathname === '/api/week' || url.pathname === '/api/month' || /^\/api\/sections\/\d+$/.test(url.pathname);
    if (offlineSafe) event.respondWith(networkFirstApi(request));
    else event.respondWith(fetch(request, { cache: 'no-store' }));
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith(navigationResponse(request, event));
    return;
  }

  // JavaScript and CSS are network-first so a beta refresh picks up files
  // changed on the running server without requiring a port restart.
  if (/\.(?:js|css)$/i.test(url.pathname)) {
    event.respondWith(liveAsset(request));
    return;
  }
  event.respondWith(cacheFirstAsset(request));
});
