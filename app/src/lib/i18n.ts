/**
 * i18n — i18next initialization.
 * Imported by __root.tsx to bootstrap translations before first render.
 *
 * 2026-08-27: 放弃懒加载 glob + top-level await 方案 —— TLA 与 chunk 执行顺序
 * 互斥,server 构建三连崩(TDZ ×2 + addResourceBundle undefined),且该重构
 * 从未在浏览器验证过。回到 eager 同步 init(与线上可用版本同构),双语言
 * 全量加载,demo 场景可接受。
 */
import i18n, { type Resource } from "i18next";
import { initReactI18next } from "react-i18next";
import { SERVER_BUILD } from "./env";
import zh from "./i18n/zh";
import en from "./i18n/en";

const STORAGE_KEY = "legent-language";

function getInitialLanguage(): "zh" | "en" {
  // 1. saved preference
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "zh" || saved === "en") return saved;
  } catch {
    // ignore
  }
  // 2. browser language
  const nav = typeof navigator !== "undefined" ? navigator.language : "zh";
  if (nav?.toLowerCase().startsWith("en")) return "en";
  return "zh";
}

/** Eager locale bundles: "./locales/<lang>/<ns>.ts" (inlined at build time) */
const localeGlob = import.meta.glob<{ default: Record<string, unknown> }>("./locales/*/*.ts", {
  eager: true,
});

const resources: Resource = { zh: {}, en: {} };
for (const [path, mod] of Object.entries(localeGlob)) {
  const lang = path.includes("en-US") ? "en" : "zh";
  const ns = path.split("/").pop()!.replace(/\.ts$/, "");
  resources[lang][ns] = mod.default;
}
resources.zh.translation = zh;
resources.en.translation = en;

/**
 * server 自包含构建品牌词替换:译文(metaTitle/文案)中的 NormNomos → davybot。
 * 组件内硬编码品牌词走 src/lib/brand.ts;此处覆盖全部 i18n 字符串。
 */
const brandPostProcessor = {
  type: "postProcessor" as const,
  name: "davybot-brand",
  process: (value: string) => (SERVER_BUILD ? value.replace(/NormNomos/g, "davybot") : value),
};

i18n
  .use(brandPostProcessor)
  .use(initReactI18next)
  .init({
    resources,
    lng: getInitialLanguage(),
    fallbackLng: "zh",
    defaultNS: "translation",
    interpolation: { escapeValue: false },
    postProcess: ["davybot-brand"],
  });

/** Switch language and persist the choice. Called by LanguageSelector. */
export async function setLanguage(lang: string) {
  const target = lang?.startsWith("en") ? "en" : "zh";
  await i18n.changeLanguage(target);
  try {
    localStorage.setItem(STORAGE_KEY, target);
  } catch {
    // ignore
  }
}

export function getCurrentLanguage(): string {
  return i18n.language?.startsWith("en") ? "en" : "zh";
}

export default i18n;
