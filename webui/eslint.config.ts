import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

// To allow more languages other than `ts` in `.vue` files, uncomment the following lines:
// import { configureVueProject } from '@vue/eslint-config-typescript'
// configureVueProject({ scriptLangs: ['ts', 'tsx'] })
// More info at https://github.com/vuejs/eslint-config-typescript/#advanced-setup

const config: readonly unknown[] = defineConfigWithVueTs(
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
    ],
  },

  pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,
  skipFormatting,

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
)

export default config
