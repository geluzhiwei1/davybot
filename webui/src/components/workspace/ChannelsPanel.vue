/* eslint-disable */
<template>
  <div class="channels-panel">
    <!-- Header -->
    <div class="panel-header">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            消息通道 (Channels) 将 DaweiBot 连接到各种聊天平台。每个通道独立注册，支持不同的消息格式和能力。
          </p>
        </template>
      </el-alert>

      <div class="header-actions">
        <el-button type="primary" @click="loadChannels" :loading="loading" :icon="Refresh">
          刷新
        </el-button>
        <el-button @click="checkHealth" :loading="checkingHealth" :icon="Monitor">
          健康检查
        </el-button>
      </div>
    </div>

    <!-- Channel List -->
    <el-table :data="channels" style="width: 100%" v-loading="loading"
      empty-text="暂无已注册的通道">
      <el-table-column prop="channel_type" label="通道类型" width="130">
        <template #default="{ row }">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-size: 16px;">{{ getChannelIcon(row.channel_type) }}</span>
            <code style="font-weight: 500;">{{ row.channel_type }}</code>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column label="格式" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.capabilities?.format_type || 'plain' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最大长度" width="100" align="center">
        <template #default="{ row }">
          <span style="font-size: 12px;">{{ formatLength(row.capabilities?.max_text_length) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="能力" min-width="240">
        <template #default="{ row }">
          <div class="capability-tags">
            <el-tag v-if="row.capabilities?.groups" size="small" type="success">群组</el-tag>
            <el-tag v-if="row.capabilities?.media_send" size="small" type="primary">发送媒体</el-tag>
            <el-tag v-if="row.capabilities?.media_receive" size="small" type="primary">接收媒体</el-tag>
            <el-tag v-if="row.capabilities?.mentions" size="small" type="warning">@提及</el-tag>
            <el-tag v-if="row.capabilities?.reactions" size="small" type="">表情</el-tag>
            <el-tag v-if="row.capabilities?.voice" size="small" type="danger">语音</el-tag>
            <el-tag v-if="row.capabilities?.streaming" size="small" type="success">流式</el-tag>
            <el-tag v-if="row.capabilities?.markdown" size="small" type="info">Markdown</el-tag>
            <el-tag v-if="row.capabilities?.html" size="small" type="info">HTML</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110" align="center">
        <template #default="{ row }">
          <el-tag
            :type="healthMap[row.channel_type]?.healthy ? 'success' : 'info'"
            size="small"
          >
            {{ healthMap[row.channel_type]?.healthy ? '运行中' : '已注册' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" size="small" text @click="showDetail(row)">
            详情
          </el-button>
          <el-button type="warning" size="small" text @click="openConfigDialog(row)">
            配置
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Channel Detail Dialog -->
    <el-dialog v-model="detailDialogVisible" :title="`${selectedChannel?.channel_type || ''} 通道详情`"
      width="600px">
      <template v-if="selectedChannel">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="通道类型">
            <code>{{ selectedChannel.channel_type }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="消息格式">
            {{ selectedChannel.capabilities?.format_type }}
          </el-descriptions-item>
          <el-descriptions-item label="最大消息长度">
            {{ formatLength(selectedChannel.capabilities?.max_text_length) }}
          </el-descriptions-item>
          <el-descriptions-item label="支持群组">
            {{ selectedChannel.capabilities?.groups ? '是' : '否' }}
          </el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">
            {{ selectedChannel.description }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- Capabilities Grid -->
        <h4 style="margin: 16px 0 8px;">能力矩阵</h4>
        <div class="capabilities-grid">
          <div v-for="cap in capabilityList" :key="cap.key" class="cap-item">
            <el-icon :color="cap.enabled ? '#67c23a' : '#c0c4cc'" :size="14">
              <Select v-if="cap.enabled" />
              <CloseBold v-else />
            </el-icon>
            <span>{{ cap.label }}</span>
          </div>
        </div>

        <!-- Config Fields -->
        <template v-if="Object.keys(selectedChannel.config_fields || {}).length > 0">
          <h4 style="margin: 16px 0 8px;">配置项</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item
              v-for="(value, key) in selectedChannel.config_fields"
              :key="key"
              :label="String(key)"
            >
              <code>{{ value === null ? '(必填)' : JSON.stringify(value) }}</code>
            </el-descriptions-item>
          </el-descriptions>
        </template>
      </template>
    </el-dialog>

    <!-- Channel Config Dialog -->
    <el-dialog v-model="configDialogVisible" :title="`配置 ${configChannel?.channel_type || ''} 通道`"
      width="560px" :close-on-click-modal="false">
      <el-form label-width="140px" label-position="right" v-if="configChannel">
        <el-form-item
          v-for="fieldKey in configFieldKeys"
          :key="fieldKey"
          :label="configFieldLabels[fieldKey] || fieldKey"
        >
          <template v-if="isSecretField(fieldKey)">
            <el-input v-model="configForm[fieldKey]" type="password" show-password
              :placeholder="`输入 ${fieldKey}`" />
          </template>
          <template v-else-if="typeof configForm[fieldKey] === 'boolean'">
            <el-switch v-model="configForm[fieldKey]" />
          </template>
          <template v-else-if="typeof configForm[fieldKey] === 'number'">
            <el-input-number v-model="configForm[fieldKey]" :min="1"
              controls-position="right" style="width: 200px;" />
          </template>
          <template v-else>
            <el-input v-model="configForm[fieldKey]" :placeholder="`输入 ${fieldKey}`" />
          </template>
        </el-form-item>
        <el-form-item v-if="configFieldKeys.length === 0">
          <el-text type="info">该通道无可配置项</el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveConfig" :loading="savingConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { Refresh, Monitor, Select, CloseBold } from '@element-plus/icons-vue';
import { channelsApi } from '@/services/api/services/channels';
import type { ChannelInfo, ChannelCapabilityInfo, ChannelsHealthResponse } from '@/services/api/services/channels';

const props = defineProps<{
  workspaceId: string;
}>();

const channels = ref<ChannelInfo[]>([]);
const loading = ref(false);
const checkingHealth = ref(false);
const healthMap = ref<Record<string, { healthy: boolean; message: string }>>({});
const detailDialogVisible = ref(false);
const selectedChannel = ref<ChannelInfo | null>(null);

// Config dialog state
const configDialogVisible = ref(false);
const configChannel = ref<ChannelInfo | null>(null);
const configForm = ref<Record<string, unknown>>({});
const savingConfig = ref(false);

// Channel icon map
const iconMap: Record<string, string> = {
  telegram: '📱',
  discord: '🎮',
  slack: '💬',
  wechat: '💚',
  feishu: '🐦',
  dingtalk: '🔷',
  qq: '🐧',
  signal: '🔒',
  imessage: '💬',
  email: '📧',
};

const getChannelIcon = (type: string): string => iconMap[type] || '📡';

const formatLength = (len: number | undefined): string => {
  if (!len) return '-';
  if (len >= 1000000) return '无限制';
  if (len >= 1000) return `${Math.round(len / 1000)}K`;
  return String(len);
};

const loadChannels = async () => {
  if (!props.workspaceId) return;
  loading.value = true;
  try {
    const response = await channelsApi.listChannels(props.workspaceId);
    channels.value = response.channels || [];
  } catch (error) {
    console.error('Failed to load channels:', error);
  } finally {
    loading.value = false;
  }
};

const checkHealth = async () => {
  if (!props.workspaceId) return;
  checkingHealth.value = true;
  try {
    const response = await channelsApi.healthCheck(props.workspaceId);
    const map: Record<string, { healthy: boolean; message: string }> = {};
    for (const [key, val] of Object.entries(response.health || {})) {
      map[key] = { healthy: val.healthy, message: val.message };
    }
    healthMap.value = map;
    const runningCount = Object.values(map).filter(v => v.healthy).length;
    ElMessage.success(`健康检查完成: ${runningCount} 个运行中, ${Object.keys(map).length} 个已注册`);
  } catch (error) {
    ElMessage.error('健康检查失败');
    console.error('Failed to check health:', error);
  } finally {
    checkingHealth.value = false;
  }
};

const showDetail = (channel: ChannelInfo) => {
  selectedChannel.value = channel;
  detailDialogVisible.value = true;
};

const capabilityList = computed(() => {
  if (!selectedChannel.value?.capabilities) return [];
  const caps = selectedChannel.value.capabilities as ChannelCapabilityInfo;
  return [
    { key: 'streaming', label: '流式输出', enabled: caps.streaming },
    { key: 'threading', label: '话题线程', enabled: caps.threading },
    { key: 'reactions', label: '表情回应', enabled: caps.reactions },
    { key: 'typing', label: '输入提示', enabled: caps.typing },
    { key: 'media_send', label: '发送媒体', enabled: caps.media_send },
    { key: 'media_receive', label: '接收媒体', enabled: caps.media_receive },
    { key: 'voice', label: '语音消息', enabled: caps.voice },
    { key: 'groups', label: '群组聊天', enabled: caps.groups },
    { key: 'mentions', label: '@提及', enabled: caps.mentions },
    { key: 'markdown', label: 'Markdown', enabled: caps.markdown },
    { key: 'html', label: 'HTML', enabled: caps.html },
  ];
});

// --- Config Dialog Helpers ---

// Secret field patterns (tokens, keys, passwords, secrets)
const secretPatterns = ['token', 'secret', 'key', 'password', 'aes'];

const isSecretField = (fieldKey: string): boolean => {
  return secretPatterns.some(p => fieldKey.toLowerCase().includes(p));
};

// Human-readable labels for common config fields
const configFieldLabels: Record<string, string> = {
  token: 'Token',
  bot_token: 'Bot Token',
  webhook_url: 'Webhook URL',
  app_key: 'App Key',
  app_secret: 'App Secret',
  app_id: 'App ID',
  agent_id: 'Agent ID',
  encoding_aes_key: 'Encoding AES Key',
  corp_id: '企业 ID',
  command_prefix: '命令前缀',
  allowed_guilds: '允许的 Guild',
  allowed_teams: '允许的团队',
  allowed_senders: '允许的发送者',
  allowed_channels: '允许的频道',
  allowed_departments: '允许的部门',
  allowed_chats: '允许的聊天',
  allowed_tenants: '允许的租户',
  text_chunk_limit: '文本块限制',
  proxy: '代理地址',
  include_attachments: '包含附件',
  rpc_port: 'RPC 端口',
  phone_number: '手机号码',
  cli_path: 'CLI 路径',
  config_dir: '配置目录',
  verification_token: '验证 Token',
  encrypt_key: '加密密钥',
};

const configFieldKeys = computed(() => {
  return Object.keys(configForm.value);
});

const openConfigDialog = (channel: ChannelInfo) => {
  configChannel.value = channel;
  // Deep copy config_fields to form
  configForm.value = { ...(channel.config_fields || {}) };
  configDialogVisible.value = true;
};

const saveConfig = async () => {
  if (!configChannel.value || !props.workspaceId) return;
  savingConfig.value = true;
  try {
    const response = await channelsApi.configureChannel(
      props.workspaceId,
      configChannel.value.channel_type,
      configForm.value
    );
    if (response.success) {
      ElMessage.success(response.message || '配置已保存');
      configDialogVisible.value = false;
      // Update local data
      const idx = channels.value.findIndex(
        c => c.channel_type === configChannel.value!.channel_type
      );
      if (idx >= 0) {
        channels.value[idx] = {
          ...channels.value[idx],
          config_fields: { ...configForm.value },
        };
      }
    }
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : '配置保存失败';
    ElMessage.error(msg);
    console.error('Failed to save channel config:', error);
  } finally {
    savingConfig.value = false;
  }
};

onMounted(() => {
  loadChannels();
});
</script>

<style scoped>
.channels-panel {
  padding: 16px;
}

.panel-header {
  margin-bottom: 16px;
}

.header-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.capability-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.capabilities-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.cap-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
</style>
