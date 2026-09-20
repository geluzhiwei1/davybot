/**
 * Sanctions pages automated test (no dependencies — pure Node.js)
 * Tests: API endpoints + frontend page serving
 */
const http = require("http");

// Env overrides for remote/tunnel runs (default = prod LAN address):
//   SANC_BASE_API=http://127.0.0.1:18012 SANC_ADMIN_API_KEY=... node tests/sanctions-api-test.cjs
const BASE_API = process.env.SANC_BASE_API || "http://10.168.1.105:8012";
const BASE_UI = process.env.SANC_UI_BASE || "http://127.0.0.1:8015";
const ADMIN_KEY = process.env.SANC_ADMIN_API_KEY || "";
const RESULTS = [];

function authHeaders(extra = {}) {
  return ADMIN_KEY ? { "X-Admin-API-Key": ADMIN_KEY, ...extra } : extra;
}

function assert(name, pass, detail = "") {
  RESULTS.push({ name, pass, detail });
  const icon = pass ? "PASS" : "FAIL";
  const d = detail ? ` (${detail})` : "";
  console.log(`  ${icon}  ${name}${d}`);
}

function fetch(url, opts = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const options = {
      hostname: u.hostname,
      port: u.port,
      path: u.pathname + u.search,
      method: opts.method || "GET",
      headers: { ...opts.headers, Connection: "close" },
      timeout: 8000,
    };
    const timer = setTimeout(() => {
      req.destroy();
      reject(new Error("timeout"));
    }, 8000);
    const req = http.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        clearTimeout(timer);
        let json = null;
        try {
          json = JSON.parse(data || "{}");
        } catch {}
        resolve({ status: res.statusCode, body: data, json });
      });
    });
    req.on("error", (e) => {
      clearTimeout(timer);
      reject(e);
    });
    if (opts.body) req.write(JSON.stringify(opts.body));
    req.end();
  });
}

(async () => {
  console.log("========== 制裁合规前端 — 自动化测试 ==========\n");

  // ── 1. API Backend Health ──────────────────────────────────────────
  console.log("--- API 后端健康检查 ---");
  try {
    const health = await fetch(`${BASE_API}/api/v1/health`);
    assert("API /health 返回 200", health.status === 200, `status=${health.status}`);
    assert("API 返回 status:ok", health.json?.status === "ok", health.json?.status);
  } catch (e) {
    assert("API 可连接", false, e.message);
  }

  // ── 2. Key API Endpoints ───────────────────────────────────────────
  console.log("\n--- API 端点可用性 ---");
  const endpoints = [
    ["GET /entities/search", `${BASE_API}/api/v1/entities/search?q=test&pageSize=1`],
    ["GET /filters", `${BASE_API}/api/v1/filters`],
    ["GET /dashboard/stats", `${BASE_API}/api/v1/dashboard/stats`],
    ["GET /graph/search", `${BASE_API}/api/v1/graph/search?q=test`],
    [
      "POST /entities/search/advanced",
      `${BASE_API}/api/v1/entities/search/advanced`,
      "POST",
      { q: "test", pageSize: 1 },
    ],
    ["POST /screen", `${BASE_API}/api/v1/screen`, "POST", { query: "test" }],
    ["GET /monitoring/watchlists", `${BASE_API}/api/v1/monitoring/watchlists`],
    ["GET /compliance/dashboard", `${BASE_API}/api/v1/compliance/dashboard`],
    ["GET /compliance/screening-history", `${BASE_API}/api/v1/compliance/screening-history`],
    ["GET /search/all", `${BASE_API}/api/v1/search/all?q=test`],
    ["GET /scraped/search", `${BASE_API}/api/v1/scraped/search?q=test`],
    ["POST /qa/ask", `${BASE_API}/api/v1/qa/ask`, "POST", { question: "test" }],
    ["GET /user/saved-searches", `${BASE_API}/api/v1/user/saved-searches`],
    ["GET /screen/batch/jobs", `${BASE_API}/api/v1/screen/batch/jobs`],
    [
      "POST /search/facets",
      `${BASE_API}/api/v1/search/facets`,
      "POST",
      { query: "test", facet_fields: ["jurisdiction"], filters: {} },
    ],
  ];
  for (const [name, url, method, body] of endpoints) {
    try {
      const res = await fetch(url, {
        method: method || "GET",
        body,
        headers: authHeaders(body ? { "Content-Type": "application/json" } : {}),
      });
      // 401 is OK (auth required), 200 is OK, 404 is missing
      assert(name, res.status !== 404, `HTTP ${res.status}`);
    } catch (e) {
      assert(name, false, e.message);
    }
  }

  // ── 2b. /search/facets contract（公告文书分面检索）────────────────
  // 契约对齐 legal-ext 的 POST /search/facets：
  //   请求 {query, facet_fields, filters} → 响应 {facets: {field: {value: count}}, total}
  // 计数按“排除自身维度过滤”的语义计算（同维度内可切换取值）。
  console.log("\n--- /search/facets 契约 ---");
  try {
    const res = await fetch(`${BASE_API}/api/v1/search/facets`, {
      method: "POST",
      body: {
        query: "",
        facet_fields: ["jurisdiction", "source_issuer", "source_type", "dataset"],
        filters: {},
      },
      headers: authHeaders({ "Content-Type": "application/json" }),
    });
    assert("POST /search/facets 返回 200", res.status === 200, `HTTP ${res.status}`);
    const facets = res.json?.facets;
    assert(
      "响应包含 facets 对象",
      !!facets && typeof facets === "object",
      facets ? Object.keys(facets).join(",") : "missing",
    );
    if (facets) {
      for (const f of ["jurisdiction", "source_issuer", "source_type", "dataset"]) {
        const v = facets[f];
        assert(
          `facets.${f} 为 {value: count} 映射`,
          v === undefined ||
            (typeof v === "object" && Object.values(v).every((c) => typeof c === "number")),
          v ? `${Object.keys(v).length} values` : "absent",
        );
      }
    }
  } catch (e) {
    assert("POST /search/facets 可调用", false, e.message);
  }

  // ── 3. Frontend Pages ──────────────────────────────────────────────
  console.log("\n--- 前端页面 ---");
  const pages = [
    ["实体检索 /sanctions/search", `${BASE_UI}/app-ui/sanctions/search`],
    ["持续监控 /sanctions/monitoring", `${BASE_UI}/app-ui/sanctions/monitoring`],
    ["筛查仪表盘 /sanctions/dashboard", `${BASE_UI}/app-ui/sanctions/dashboard`],
  ];
  for (const [name, url] of pages) {
    try {
      const res = await fetch(url);
      const hasNormNomos = res.body.includes("NormNomos");
      assert(
        `${name} 可访问`,
        res.status === 200 && hasNormNomos,
        `HTTP ${res.status}, has title: ${hasNormNomos}`,
      );
    } catch (e) {
      assert(name, false, e.message);
    }
  }

  // ── 4. Vite Module Serving ─────────────────────────────────────────
  console.log("\n--- Vite 模块服务 ---");
  const modules = [
    `${BASE_UI}/app-ui/src/routes/sanctions.search.tsx`,
    `${BASE_UI}/app-ui/src/routes/sanctions.monitoring.tsx`,
    `${BASE_UI}/app-ui/src/routes/sanctions.dashboard.tsx`,
    `${BASE_UI}/app-ui/src/lib/sanctions-service.ts`,
    `${BASE_UI}/app-ui/src/lib/sanctions-risk.ts`,
    `${BASE_UI}/app-ui/src/components/sanctions/ai-qa-panel.tsx`,
    `${BASE_UI}/app-ui/src/components/sanctions/export-dialog.tsx`,
    `${BASE_UI}/app-ui/src/components/sanctions/advanced-search-builder.tsx`,
    `${BASE_UI}/app-ui/src/components/sanctions/add-to-monitoring-dialog.tsx`,
  ];
  for (const url of modules) {
    const name = url.split("/app-ui/")[1];
    try {
      const res = await fetch(url);
      assert(`模块: ${name}`, res.status === 200, `HTTP ${res.status}`);
    } catch (e) {
      assert(`模块: ${name}`, false, e.message);
    }
  }

  // ── 5. API Response Schema Validation ───────────────────────────────
  console.log("\n--- API 响应结构验证 ---");
  // Filter endpoint: returns { countries, datasets, schema_types }. 401=ok (auth needed), check 404.
  try {
    const filters = await fetch(`${BASE_API}/api/v1/filters`);
    assert("Filters 端点可用", filters.status !== 404, `HTTP ${filters.status}`);
  } catch (e) {
    assert("Filters 端点", false, e.message);
  }

  // Dashboard stats
  try {
    const stats = await fetch(`${BASE_API}/api/v1/dashboard/stats`);
    assert("Stats 端点可用", stats.status !== 404, `HTTP ${stats.status}`);
  } catch (e) {
    assert("Stats 端点", false, e.message);
  }

  // Graph search
  try {
    const graph = await fetch(`${BASE_API}/api/v1/graph/search?q=test&limit=1`);
    assert("Graph 端点可用", graph.status !== 404, `HTTP ${graph.status}`);
  } catch (e) {
    assert("Graph 端点", false, e.message);
  }

  // Search/all
  try {
    const all = await fetch(`${BASE_API}/api/v1/search/all?q=test`);
    assert("Search/all 端点可用", all.status !== 404, `HTTP ${all.status}`);
  } catch (e) {
    assert("Search/all 端点", false, e.message);
  }

  // Monitoring stats (v0.2+)
  try {
    const ms = await fetch(`${BASE_API}/api/v1/monitoring/stats`);
    assert("Monitoring/stats 端点可用", ms.status !== 404, `HTTP ${ms.status}`);
  } catch (e) {
    assert("Monitoring/stats 端点", false, e.message);
  }

  // Dashboard trends (v0.2+)
  try {
    const dt = await fetch(`${BASE_API}/api/v1/compliance/dashboard/trends?days=7`);
    assert("Dashboard/trends 端点可用", dt.status !== 404, `HTTP ${dt.status}`);
  } catch (e) {
    assert("Dashboard/trends 端点", false, e.message);
  }

  // ── Summary ────────────────────────────────────────────────────────
  const passed = RESULTS.filter((r) => r.pass).length;
  const failed = RESULTS.filter((r) => !r.pass).length;
  console.log(`\n========== 测试结果: ${passed}/${RESULTS.length} 通过, ${failed} 失败 ==========`);
  if (failed > 0) {
    console.log("\n失败项:");
    RESULTS.filter((r) => !r.pass).forEach((r) => console.log(`  ❌ ${r.name} — ${r.detail}`));
    process.exit(1);
  }
  console.log("全部通过 🎉");
})().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(2);
});
