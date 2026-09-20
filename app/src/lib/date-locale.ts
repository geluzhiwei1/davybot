/**
 * Locale-aware date formatting helper.
 * Returns the BCP47 tag matching the current i18n language so that
 * toLocaleDateString/toLocaleTimeString follow the UI language.
 */
import i18n from "@/lib/i18n";

export function dateLocale(): "zh-CN" | "en-US" {
  return i18n.language?.startsWith("en") ? "en-US" : "zh-CN";
}
