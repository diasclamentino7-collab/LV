const CACHE = "lv-wedding-v9";
const ASSETS = [
  "/static/css/app.css",
  "/static/css/motion.css",
  "/static/css/communication-drawer.css",
  "/static/css/moodboard-motion.css",
  "/static/css/budget.css",
  "/static/css/deletion.css",
  "/static/css/command-palette.css",
  "/static/css/guests.css",
  "/static/css/module-workspace.css",
  "/static/css/form-workspace.css",
  "/static/css/utility-workspaces.css",
  "/static/js/motion.js",
  "/static/js/app.js",
  "/static/js/dashboard.js",
  "/static/js/communication-drawer.js",
  "/static/js/moodboard.js",
  "/static/js/budget.js",
  "/static/js/command-palette.js",
  "/static/js/guests.js",
  "/static/js/module-workspace.js",
  "/static/js/form-workspace.js",
  "/static/js/utility-workspaces.js",
  "/manifest.webmanifest",
  "/static/icons/icon.svg"
];
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS))));
self.addEventListener("activate", event => event.waitUntil(
  caches.keys()
    .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
    .then(() => self.clients.claim())
));
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
