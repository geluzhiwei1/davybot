/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="plugin-settings-panel">
    <!-- Plugin Statistics -->
    <div v-if="statistics" class="plugin-statistics">
      <el-card>
        <template #header>
          <span>Plugin Statistics</span>
        </template>
        <el-row :gutter="20">
          <el-col :span="8">
            <el-statistic title="Total Plugins" :value="statistics.total_plugins" />
          </el-col>
          <el-col :span="8">
            <el-statistic title="Activated" :value="statistics.activated_plugins" />
          </el-col>
          <el-col :span="8">
            <el-statistic
              title="By Type"
              :value="Object.keys(statistics.by_type || {}).length"
            />
          </el-col>
        </el-row>
      </el-card>
    </div>

    <!-- Plugin Type Filter -->
    <div class="plugin-filter">
      <el-radio-group v-model="filterType" @change="handleFilterChange">
        <el-radio-button label="">All</el-radio-button>
        <el-radio-button label="channel">Channels</el-radio-button>
        <el-radio-button label="tool">Tools</el-radio-button>
        <el-radio-button label="service">Services</el-radio-button>
        <el-radio-button label="memory">Memory</el-radio-button>
      </el-radio-group>

      <el-switch
        v-model="showActivatedOnly"
        active-text="Activated Only"
        @change="handleFilterChange"
      />
    </div>

    <!-- Plugin List -->
    <div v-loading="loading" class="plugin-list">
      <el-empty v-if="!loading && plugins.length === 0" description="No plugins found" />

      <el-card
        v-for="plugin in plugins"
        :key="plugin.id"
        class="plugin-card"
        :class="{ 'plugin-enabled': plugin.enabled }"
      >
        <template #header>
          <div class="plugin-header">
            <div class="plugin-info">
              <span class="plugin-name">{{ plugin.name }}</span>
              <el-tag size="small" type="info">{{ plugin.version }}</el-tag>
              <el-tag size="small" :type="getTypeColor(plugin.type)">
                {{ plugin.type }}
              </el-tag>
            </div>

            <div class="plugin-actions">
              <el-switch
                v-model="plugin.enabled"
                @change="handleToggleEnable(plugin)"
                :loading="plugin._loading"
                active-text="已启用"
                inactive-text="已禁用"
              />
              <el-button
                size="small"
                :type="plugin.activated ? 'warning' : 'primary'"
                :disabled="!plugin.enabled"
                :loading="plugin._activating"
                style="margin-left: 8px;"
                @click="handleToggleActivated(plugin)"
              >
                {{ plugin.activated ? '停用' : '激活' }}
              </el-button>
            </div>
          </div>
        </template>

        <div class="plugin-description">
          {{ plugin.description }}
        </div>

        <div class="plugin-meta">
          <span><strong>Author:</strong> {{ plugin.author }}</span>
        </div>

        <template #footer>
          <div class="plugin-footer">
            <div class="plugin-actions">
              <el-button-group>
                <el-button
                  size="small"
                  @click="handleReload(plugin)"
                >
                  Reload
                </el-button>

                <el-button
                  size="small"
                  @click="handleConfigure(plugin)"
                >
                  Configure
                </el-button>
              </el-button-group>
            </div>
          </div>
        </template>
      </el-card>
    </div>

    <!-- Plugin Configuration Dialog -->
    <el-dialog
      v-model="configDialogVisible"
      :title="`Configure ${currentPlugin?.name}`"
      width="600px"
    >
      <el-form v-if="currentPluginSettings" label-width="150px">
        <el-form-item label="Plugin Settings">
          <div v-if="Object.keys(currentPluginSettings.settings || {}).length > 0">
            <el-form
              :model="currentPluginSettings.settings"
              label-position="top"
            >
              <el-form-item
                v-for="(value, key) in currentPluginSettings.settings"
                :key="key"
                :label="key"
              >
                <el-input
                  v-if="typeof value === 'string'"
                  v-model="currentPluginSettings.settings[key]"
                  :placeholder="key"
                />

                <el-input-number
                  v-else-if="typeof value === 'number'"
                  v-model="currentPluginSettings.settings[key]"
                />

                <el-switch
                  v-else-if="typeof value === 'boolean'"
                  v-model="currentPluginSettings.settings[key]"
                />

                <el-input
                  v-else
                  v-model="currentPluginSettings.settings[key]"
                  type="textarea"
                  :rows="3"
                />
              </el-form-item>
            </el-form>
          </div>

          <el-empty v-else description="No custom settings" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="configDialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="handleSaveConfig" :loading="loading">
          Save
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { usePluginsStore } from '@/stores/plugins'
import { ElMessage } from 'element-plus'
import type { PluginInfo } from '@/types/plugins'

interface Props {
  workspaceId: string
}

const props = defineProps<Props>()

const pluginsStore = usePluginsStore()

// State
const filterType = ref('')
const showActivatedOnly = ref(false)
const configDialogVisible = ref(false)
const currentPlugin = ref<PluginInfo | null>(null)

// Computed
const plugins = computed(() => pluginsStore.plugins)
const loading = computed(() => pluginsStore.loading)
const statistics = computed(() => pluginsStore.statistics)

// Methods
const getTypeColor = (type: string) => {
  const colors: Record<string, string> = {
    channel: 'primary',
    tool: 'success',
    service: 'warning',
    memory: 'info'
  }
  return colors[type] || 'info'
}

const handleFilterChange = () => {
  pluginsStore.fetchPlugins(props.workspaceId, {
    plugin_type: filterType.value || undefined,
    activated_only: showActivatedOnly.value
  })
}

const handleToggleEnable = async (plugin: PluginInfo) => {
  try {
    plugin._loading = true

    if (plugin.enabled) {
      await pluginsStore.enablePlugin(props.workspaceId, plugin.id)
      ElMessage.success(`插件 '${plugin.name}' 已启用`)
    } else {
      await pluginsStore.disablePlugin(props.workspaceId, plugin.id)
      ElMessage.success(`插件 '${plugin.name}' 已禁用`)
    }
  } catch (error: unknown) {
    ElMessage.error(`切换插件失败: ${error.message}`)
    // Revert UI state
    plugin.enabled = !plugin.enabled
  } finally {
    plugin._loading = false
  }
}

const handleToggleActivated = async (plugin: PluginInfo) => {
  try {
    plugin._activating = true

    if (plugin.activated) {
      await pluginsStore.deactivatePlugin(props.workspaceId, plugin.id)
      ElMessage.success(`插件 '${plugin.name}' 已停用`)
    } else {
      await pluginsStore.activatePlugin(props.workspaceId, plugin.id)
      ElMessage.success(`插件 '${plugin.name}' 已激活`)
    }
    // Toggle the state
    plugin.activated = !plugin.activated
  } catch (error: unknown) {
    ElMessage.error(`切换激活状态失败: ${error.message}`)
  } finally {
    plugin._activating = false
  }
}

const handleReload = async (plugin: PluginInfo) => {
  try {
    await pluginsStore.reloadPlugin(props.workspaceId, plugin.id)
    ElMessage.success(`Plugin '${plugin.name}' reloaded`)
  } catch (error: unknown) {
    ElMessage.error(`Failed to reload plugin: ${error.message}`)
  }
}

const handleConfigure = async (plugin: PluginInfo) => {
  currentPlugin.value = plugin

  try {
    await pluginsStore.fetchPluginSettings(props.workspaceId, plugin.id)
    configDialogVisible.value = true
  } catch (error: unknown) {
    ElMessage.error(`Failed to load plugin settings: ${error.message}`)
  }
}

const handleSaveConfig = async () => {
  if (!currentPlugin.value) return

  try {
    await pluginsStore.updatePluginSettings(
      props.workspaceId,
      currentPlugin.value.id,
      pluginsStore.currentPluginSettings!
    )

    ElMessage.success('Plugin settings saved')
    configDialogVisible.value = false
  } catch (error: unknown) {
    ElMessage.error(`Failed to save settings: ${error.message}`)
  }
}

// Lifecycle
onMounted(async () => {
  await pluginsStore.fetchPlugins(props.workspaceId)
  await pluginsStore.fetchStatistics(props.workspaceId)
})
</script>

<style scoped>
.plugin-settings-panel {
  padding: 20px;
}

.plugin-statistics {
  margin-bottom: 20px;
}

.plugin-filter {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.plugin-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.plugin-card {
  transition: all 0.3s;
}

.plugin-card.plugin-activated {
  border-left: 4px solid var(--el-color-success);
}

.plugin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.plugin-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plugin-name {
  font-weight: bold;
  font-size: 16px;
}

.plugin-description {
  margin: 12px 0;
  color: var(--el-text-color-secondary);
}

.plugin-meta {
  margin-bottom: 12px;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.plugin-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
