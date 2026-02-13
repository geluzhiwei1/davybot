import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E测试配置
 * 用于自动化测试通用Agent平台的用户操作
 */
export default defineConfig({
  // 测试目录
  testDir: './e2e',

  // 并行运行测试
  fullyParallel: true,

  // 失败时重试次数
  retries: process.env.CI ? 2 : 1,

  // 超时时间（Agent任务可能需要较长时间）
  timeout: 60000,

  // 每个测试的超时
  expect: {
    timeout: 10000
  },

  // 测试文件匹配模式
  testMatch: '**/*.spec.ts',

  // 忽略的文件
  testIgnore: '**/*.spec.ts.skip',

  use: {
    // 基础URL
    baseURL: 'http://localhost:8460',

    // 失败时截图
    screenshot: 'only-on-failure',

    // 失败时录制视频
    video: 'retain-on-failure',

    // 追踪
    trace: 'retain-on-failure',

    // 操作超时
    actionTimeout: 10000,

    // 导航超时
    navigationTimeout: 30000,
  },

  // 测试项目（浏览器配置）
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Chrome浏览器的上下文配置
        viewport: { width: 1280, height: 720 },
        channel: 'chrome', // 使用系统安装的 Chrome 浏览器
        launchOptions: {
          args: [
            '--disable-web-security', // 开发环境允许跨域
            '--disable-setuid-sandbox',
            '--no-sandbox'
          ]
        }
      },
    },

    // 可以添加更多浏览器
    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] }
    // },
  ],

  // 开发服务器配置
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:8460',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
    stdout: 'pipe',
    stderr: 'pipe',
  },

  // 输出目录
  outputDir: 'test-results',

  // 报告器配置
  reporter: [
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/test-results.json' }],
    ['junit', { outputFile: 'test-results/junit-results.xml' }],
    ['list']
  ],

  // 全局设置 (暂未配置)
  // globalSetup: './e2e/global-setup.ts',
  // globalTeardown: './e2e/global-teardown.ts',
})
