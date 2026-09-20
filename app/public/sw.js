/**
 * Minimal offline-shell service worker(移动端可用性提升方案.md · Phase 0)。
 *
 * 作用域:/app-ui/(由注册地址决定)— /api、/ws、/sanctions 等后端路径
 * 以及其它任何源外请求都不经过本 SW;带凭据的响应永远不被缓存。
 *
 * 策略(保守):
 *  - navigate 请求:network-first,离线时回退缓存的 index.html(SPA 壳)
 *  - /app-ui/assets/*:cache-first(构建产物文件名带 hash,不可变)
 *  - 其余 /app-ui/ GET(manifest / icons / favicon):stale-while-revalidate
 *
 * 版本管理:改动本文件内容 → 浏览器自动重装;activate 时清理旧版本缓存。
 */
const CACHE = "nn-app-shell-v1";
const BASE_PATH = new URL(self.registration.scope).pathname; // e.g. "/app-ui/"
const SHELL_URL = new URL("index.html", self.registration.scope).href;

self.addEventListener("install", (event) => {
  self.skipWaiting();
  // 预缓存离线壳;失败不阻塞安装(network 首次可用时会补上)
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.add(SHELL_URL))
      .catch(() => {}),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  // 只处理同源且位于 /app-ui/ 下的静态资源;API/WS/第三方一律放行
  if (url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith(BASE_PATH)) return;

  // SPA 导航:网络优先,离线回退壳页面
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches
            .open(CACHE)
            .then((cache) => cache.put(SHELL_URL, copy))
            .catch(() => {});
          return res;
        })
        .catch(async () => (await caches.match(SHELL_URL)) || Response.error()),
    );
    return;
  }

  // 带 hash 的构建产物:cache-first
  if (url.pathname.includes("/assets/")) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches
                .open(CACHE)
                .then((cache) => cache.put(req, copy))
                .catch(() => {});
            }
            return res;
          }),
      ),
    );
    return;
  }

  // manifest / icons / favicon:stale-while-revalidate
  event.respondWith(
    caches.match(req).then((hit) => {
      const network = fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches
              .open(CACHE)
              .then((cache) => cache.put(req, copy))
              .catch(() => {});
          }
          return res;
        })
        .catch(() => hit || Response.error());
      return hit || network;
    }),
  );
});
