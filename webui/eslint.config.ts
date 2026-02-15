import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

// To allow more languages other than `ts` in `.vue` files, uncomment the following lines:
// import { configureVueProject } from '@vue/eslint-config-typescript'
// configureVueProject({ scriptLangs: ['ts', 'tsx'] })
// More info at https://github.com/vuejs/eslint-config-typescript/#advanced-setup

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },

  {
    name: 'app/ignores',
    ignores: [
      '**/dist/**',
      '**/dist-ssr/**',
      '**/coverage/**',
      '**/playwright-report/**',
      '**/node_modules/**',
      '**/src-tauri/target/**',
      '**/src-tauri/resources/**',
      'src/components/layout/WorkspaceSettingsDrawer.vue',
      'console-error-capture.js', // 忽略调试脚本
    ],
  },

  pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,
  skipFormatting,

  // 自定义规则 - 必须在最后
  {
    name: 'app/custom-rules',
    files: ['**/*.{ts,mts,tsx,vue,js}'],
    rules: {
      // 允许以下划线开头的未使用变量
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      'no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      // console-error-capture.js 特殊处理
      '@typescript-eslint/no-require-imports': 'off',
    },
  },

  {
    name: 'app/overrides',
    files: [
      'src/components/chat/Message.vue',
      'src/components/layout/WorkspaceSettingsDrawer.vue',
      'src/components/layout/SidePanel.vue',
    ],
    rules: {
      'vue/multi-word-component-names': 'off',
    },
  },

  // 禁止直接使用 fetch API（应使用统一 httpClient）
  {
    name: 'app/no-fetch',
    files: [
      '**/*.{ts,mts,tsx,vue}',
      '!src/services/api/http.ts', // HTTP 客户端可以创建 fetch 实例
    ],
    rules: {
      'no-restricted-globals': [
        'error',
        {
          name: 'fetch',
          message: 'Direct use of fetch is not allowed. Use httpClient from @/services/api/http instead. See: webui/src/services/api/http.ts',
        },
      ],
    },
  },

  // 禁止直接导入 axios（应使用统一 httpClient）
  {
    name: 'app/no-axios-import',
    files: ['**/*.{ts,mts,tsx,vue}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['axios'],
              message: 'Direct import of axios is not allowed. Use httpClient from @/services/api/http instead. See: webui/src/services/api/http.ts',
            },
          ],
        },
      ],
    },
  },

  // 允许特定文件导入 axios
  {
    name: 'app/allow-axios-for-specific-files',
    files: [
      'src/services/api/http.ts',
      'console-error-capture.js',
    ],
    rules: {
      'no-restricted-imports': 'off',
    },
  },
)

