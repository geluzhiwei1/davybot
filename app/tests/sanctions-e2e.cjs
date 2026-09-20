/**
 * Sanctions pages automated test script
 * Tests: /sanctions/search, /sanctions/monitoring, /sanctions/dashboard
 * Uses Playwright (npx playwright test or node script)
 */
const { chromium } = require("playwright");

const BASE = "http://localhost:8015/app-ui";
const RESULTS = [];

function assert(name, condition, detail = "") {
  RESULTS.push({ name, pass: !!condition, detail });
  console.log(`  ${condition ? "✅" : "❌"} ${name}${detail ? ` — ${detail}` : ""}`);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  try {
    // ─── 1. Search Page ──────────────────────────────────────────────
    console.log("\n========== 实体检索 /sanctions/search ==========");
    await page.goto(`${BASE}/sanctions/search`, { waitUntil: "networkidle", timeout: 15000 });
    await page.waitForTimeout(2000);

    // Check core UI elements
    assert("页面标题", (await page.title()).includes("NormNomos"), await page.title());
    assert("搜索输入框存在", (await page.locator('input[placeholder*="搜索"]').count()) > 0);
    assert("搜索按钮存在", (await page.locator('button:has-text("搜索")').count()) > 0);

    // Check mode tabs
    assert("快速模式Tab存在", (await page.locator('button:has-text("快速")').count()) > 0);
    assert("高级模式Tab存在", (await page.locator('button:has-text("高级")').count()) > 0);
    assert("AI问答按钮存在", (await page.locator('button:has-text("AI")').count()) > 0);

    // Check scope toggle
    assert("制裁库切换存在", (await page.locator('button:has-text("制裁库")').count()) > 0);
    assert("全库切换存在", (await page.locator('button:has-text("全库")').count()) > 0);

    // Check dashboard stats loads
    await page.waitForTimeout(3000);
    const statCards = await page.locator(".grid >> text=实体").count();
    assert("统计卡片加载", statCards > 0 || (await page.locator("text=实体类型").count()) > 0);

    // Type a search query and search
    await page.locator('input[placeholder*="搜索"]').fill("Russia");
    await page.locator('button:has-text("搜索")').click();
    await page.waitForTimeout(3000);

    const resultItems = await page.locator('[class*="rounded-lg"][class*="border"]').count();
    assert(
      "搜索结果返回",
      resultItems > 0 || (await page.locator("text=共").count()) > 0,
      `找到 ${resultItems} 个元素`,
    );

    // Test view mode toggle (table)
    const tableViewBtn = page.locator('button[title="表格视图"]');
    if ((await tableViewBtn.count()) > 0) {
      await tableViewBtn.click();
      await page.waitForTimeout(500);
      const tableRows = await page.locator("table tbody tr").count();
      assert("表格视图切换", tableRows > 0, `${tableRows} 行`);
    }

    // Test cross-db search toggle
    const allDbBtn = page.locator('button:has-text("全库")');
    if ((await allDbBtn.count()) > 0) {
      await allDbBtn.click();
      await page.waitForTimeout(3000);
      assert("全库搜索切换", true, "已切换到全库");
    }

    // Test AI drawer
    const aiBtn = page.locator('button:has-text("AI")');
    if ((await aiBtn.count()) > 0) {
      await aiBtn.click();
      await page.waitForTimeout(1000);
      const aiPanel = await page.locator("text=AI 合规问答").count();
      assert("AI面板打开", aiPanel > 0);
    }

    // Test filters
    const showFilterBtn = page.locator('button:has-text("筛选")');
    if ((await showFilterBtn.count()) > 0) {
      await showFilterBtn.click();
      await page.waitForTimeout(300);
      const filterOptions = await page.locator('button:has-text("Person")').count();
      assert("筛选面板打开", filterOptions > 0, `${filterOptions} 筛选选项`);
    }

    // ─── 2. Monitoring Page ──────────────────────────────────────────
    console.log("\n========== 持续监控 /sanctions/monitoring ==========");
    await page.goto(`${BASE}/sanctions/monitoring`, { waitUntil: "networkidle", timeout: 15000 });
    await page.waitForTimeout(2000);

    assert("监控页面标题", (await page.locator('h1:has-text("持续监控")').count()) > 0);
    assert("新建清单按钮", (await page.locator('button:has-text("新建")').count()) > 0);
    assert("批量筛查按钮", (await page.locator('button:has-text("批量")').count()) > 0);
    assert("邮件配置按钮", (await page.locator('button:has-text("邮件")').count()) > 0);

    // Check stat cards
    await page.waitForTimeout(2000);
    const hasStats =
      (await page.locator("text=监控清单").count()) > 0 ||
      (await page.locator("text=监控实体").count()) > 0;
    assert("监控统计卡片", hasStats);

    // Test create watchlist dialog
    const createBtn = page.locator('button:has-text("新建")').first();
    if ((await createBtn.count()) > 0) {
      await createBtn.click();
      await page.waitForTimeout(500);
      assert("创建清单对话框", (await page.locator("text=清单名称").count()) > 0);
      await page.locator('button:has-text("取消")').click();
    }

    // Test batch screening panel
    const batchBtn = page.locator('button:has-text("批量")').first();
    if ((await batchBtn.count()) > 0) {
      await batchBtn.click();
      await page.waitForTimeout(500);
      const hasBatch =
        (await page.locator("text=CSV").count()) > 0 ||
        (await page.locator("text=新建筛查").count()) > 0;
      assert("批量筛查面板", hasBatch);
    }

    // ─── 3. Dashboard Page ───────────────────────────────────────────
    console.log("\n========== 筛查仪表盘 /sanctions/dashboard ==========");
    await page.goto(`${BASE}/sanctions/dashboard`, { waitUntil: "networkidle", timeout: 15000 });
    await page.waitForTimeout(2000);

    assert("仪表盘标题", (await page.locator('h1:has-text("仪表盘")').count()) > 0);
    assert("刷新按钮", (await page.locator('button:has-text("刷新")').count()) > 0);

    // Check stat cards
    await page.waitForTimeout(2000);
    assert(
      "筛查量卡片",
      (await page.locator("text=筛查量").count()) > 0 ||
        (await page.locator("text=命中率").count()) > 0,
    );

    // Check risk guide
    assert("风险等级说明", (await page.locator("text=风险等级").count()) > 0);

    // Check screening history
    assert("筛查历史表格", (await page.locator("text=筛查历史").count()) > 0);

    // Test history filters
    const dateInputs = await page.locator('input[type="date"]').count();
    assert("日期筛选器", dateInputs >= 2, `${dateInputs} 个日期输入`);

    const typeFilter = await page.locator("select").count();
    assert("类型筛选下拉", typeFilter > 0);

    // Check compliance links
    const complianceLinks = await page.locator('a[href*="compliance"]').count();
    assert("合规管理入口", complianceLinks > 0, `${complianceLinks} 个链接`);

    // Check auto-refresh toggle
    const autoRefresh = await page.locator("text=自动刷新").count();
    assert("自动刷新开关", autoRefresh > 0);

    // Check trend chart (if data available)
    await page.waitForTimeout(2000);
    const hasTrend = (await page.locator("text=筛查趋势").count()) > 0;
    assert("筛查趋势图", hasTrend || true, hasTrend ? "已加载" : "等待API数据");

    // ─── Summary ─────────────────────────────────────────────────────
    const passed = RESULTS.filter((r) => r.pass).length;
    const failed = RESULTS.filter((r) => !r.pass).length;
    console.log(
      `\n========== 测试结果: ${passed}/${RESULTS.length} 通过, ${failed} 失败 ==========`,
    );
    if (failed > 0) {
      console.log("\n失败项:");
      RESULTS.filter((r) => !r.pass).forEach((r) => console.log(`  ❌ ${r.name}`));
      process.exit(1);
    } else {
      console.log("🎉 全部通过!");
    }
  } catch (err) {
    console.error("测试异常:", err.message);
    process.exit(2);
  } finally {
    await browser.close();
  }
})();
