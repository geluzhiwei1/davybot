import { defineConfig } from "vitest/config";
import tsConfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  // 与 vite.config.ts 的 web 构建对齐:platform.ts 的 __APP_TARGET__ 编译期
  // 常量在测试环境同样需要(缺失会在导入 platform.ts 的测试里抛
  // ReferenceError,如 api-client.test.ts)。
  define: {
    __APP_TARGET__: JSON.stringify("web"),
  },
  plugins: [tsConfigPaths()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
