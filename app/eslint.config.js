import js from "@eslint/js";
import eslintPluginPrettier from "eslint-plugin-prettier/recommended";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  // .assemble = assemble.mjs 构建暂存(跨仓形态含闭源 biz 副本)——lint/audit 不得扫入
  { ignores: ["dist", ".output", ".vinxi", ".assemble", "src-tauri/target"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // 方案 Phase 4 ④:业务代码禁止内联 @media 视口/交互查询,统一走 Tailwind
      // 断点前缀(sm:/md:/lg:)或全局 styles.css。只匹配带括号的查询;print 媒体
      // (无括号,如导出 HTML 的打印样式)天然豁免。裸 px 宽度由
      // npm run audit:responsive 的 ratchet 基线把关(ESLint 无基线机制)。
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value=/@media\\s*\\(/]",
          message:
            "业务代码禁止内联 @media 视口/交互查询 —— 用 Tailwind 断点前缀(sm:/md:/lg:)或全局 styles.css;print 媒体查询除外",
        },
        {
          selector: "TemplateElement[value.raw=/@media\\s*\\(/]",
          message:
            "业务代码禁止内联 @media 视口/交互查询 —— 用 Tailwind 断点前缀(sm:/md:/lg:)或全局 styles.css;print 媒体查询除外",
        },
      ],
    },
  },
  eslintPluginPrettier,
);
