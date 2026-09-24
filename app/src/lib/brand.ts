/**
 * Brand — 品牌词单一出处。
 *
 * server 自包含构建(build:server / vite dev --mode server)品牌词为 davybot;
 * 其他形态(SaaS / demo / 桌面版)保持 NormNomos 不变。
 */
import { SERVER_BUILD } from "./env";

/** 品牌词(登录页/侧栏/关于等可见文案) */
export const BRAND_NAME = SERVER_BUILD ? "davybot" : "NormNomos";

/** 页面 <title> 后缀之外的完整标题(index.html 由 vite 插件注入,locale metaTitle 由 i18n 后处理器替换) */
export const BRAND_TITLE = SERVER_BUILD
  ? "davybot — AI 智能体平台"
  : "NormNomos — AI 法律智能体平台";
