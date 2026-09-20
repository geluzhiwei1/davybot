/**
 * Mobile CSS downlevel — post-processes built CSS for old Android WebViews.
 *
 * Tailwind v4 targets Chrome 111+ (@layer / oklch() / color-mix() / nesting).
 * Many Chinese Android devices (Huawei/Honor WebView 12.x = Chromium 92,
 * older Xiaomi = Chromium 8x) never receive WebView updates, so the mobile
 * build must ship CSS that parses there:
 *
 *   Pass 1  flatten `@layer` blocks (postcss AST) — Chromium < 99 drops every
 *           rule inside an unparseable @layer, which is what produced the
 *           totally-unstyled black-screen symptom. Flattening preserves
 *           source order (theme → base → utilities), which is the same
 *           cascade for our non-layered stylesheet.
 *   Pass 2  lightningcss with targets=chrome(92) — oklch()/lab colors → rgb,
 *           CSS nesting → flat selectors, vendor prefixes.
 *
 * What is NOT fixable statically (rules are dropped on old engines, accepted):
 *   - color-mix() with var()/currentColor operands (runtime blending)
 *   - :has() selectors (Chromium 105+)
 *
 * Used by vite.config.tauri.ts (mobile mode closeBundle) and runnable
 * directly:  node scripts/mobile-css-downlevel.mjs <css-file-or-dir>
 */
import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { extname, join } from "node:path";
import postcss from "postcss";
import { transform } from "lightningcss";

/** Oldest engine we downlevel for (Huawei WebView 12.x = Chromium 92). */
export const MOBILE_CSS_TARGET = { chrome: 92 << 16 };

/**
 * Pass 1 — recursively lift `@layer <name> { ... }` contents to the parent.
 * Bare ordering statements (`@layer a, b;`) are removed: with layers gone
 * they have no meaning. Nested @layer blocks are flattened bottom-up so a
 * lifted block never still contains an @layer.
 */
export function flattenLayers(css, filename = "<css>") {
  const root = postcss.parse(css, { from: filename });
  const walk = (container) => {
    container.each((node) => {
      if (node.type !== "atrule") return;
      if (node.name === "layer") {
        if (!node.nodes) {
          // `@layer a, b;` — ordering-only statement, meaningless once flat.
          node.remove();
          return;
        }
        walk(node); // flatten any inner @layer first
        node.replaceWith(...node.nodes);
      } else if (node.nodes) {
        walk(node); // recurse into @media / @supports / …
      }
    });
  };
  walk(root);
  return root.toString();
}

/** Pass 1 + Pass 2 over one CSS source string. Returns downleveled CSS. */
export function downlevelCss(css, filename = "<css>") {
  const flat = flattenLayers(css, filename);
  const out = transform({
    filename,
    code: Buffer.from(flat),
    targets: MOBILE_CSS_TARGET,
    errorRecovery: true, // keep going past single unsupported constructs
  });
  return out.code.toString();
}

/** In-place downlevel of one .css file. Returns bytes written. */
export function downlevelCssFile(file) {
  const src = readFileSync(file, "utf8");
  // Flatten is idempotent; skip work when no @layer present AND lightningcss
  // already ran (no oklch either) — cheap guard for repeat runs.
  if (!src.includes("@layer") && !src.includes("oklch(")) return 0;
  const out = downlevelCss(src, file);
  writeFileSync(file, out);
  return Buffer.byteLength(out);
}

/** Downlevel every *.css in a directory (non-recursive). */
export function downlevelCssDir(dir) {
  const files = readdirSync(dir).filter((f) => extname(f) === ".css");
  const results = [];
  for (const f of files) {
    const n = downlevelCssFile(join(dir, f));
    results.push({ file: f, bytes: n });
  }
  return results;
}

// ── CLI entry (only when executed directly, not when imported by vite) ─
import { pathToFileURL } from "node:url";
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const arg = process.argv[2];
  if (arg) {
    const st = statSync(arg);
    const results = st.isDirectory()
      ? downlevelCssDir(arg)
      : [{ file: arg, bytes: downlevelCssFile(arg) }];
    for (const r of results) console.log(`${r.bytes ? "downleveled" : "skipped     "} ${r.file} (${r.bytes} bytes)`);
  }
}
