<template>
  <div class="evolution-drawer">
    <div class="drawer-content" v-loading="loading">
      <!-- Header -->
      <el-alert
        :title="$t('evolution.title')"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px;"
      >
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            {{ $t('evolution.description') }}
          </p>
        </template>
      </el-alert>

      <!-- Enable/Disable Switch -->
      <div style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
        <div>
          <div style="font-weight: 500; margin-bottom: 4px;">
            {{ $t('evolution.enableEvolution') }}
          </div>
          <div style="font-size: 12px; color: var(--el-text-color-secondary);">
            {{ $t('evolution.enableDescription') }}
          </div>
        </div>
        <el-switch
          v-model="evolutionEnabled"
          :loading="savingConfig"
          @change="handleEnableChange"
          :disabled="isRunning"
        />
      </div>

      <!-- Evolution Control Panel (when enabled) -->
      <div v-if="evolutionEnabled">
        <!-- Config Panel -->
        <el-card shadow="never" style="margin-bottom: 16px;">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>{{ $t('evolution.config') }}</span>
              <el-button
                v-if="!isRunning"
                type="primary"
                size="small"
                @click="showConfigDialog = true"
              >
                <el-icon><Setting /></el-icon>
                {{ $t('evolution.editConfig') }}
              </el-button>
            </div>
          </template>

          <div v-if="evolutionStatus?.config">
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item :label="$t('evolution.schedule')">
                <el-tag size="small">{{ formatSchedule(evolutionStatus.config.schedule) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('evolution.phaseDuration')">
                {{ evolutionStatus.config.phase_duration }}
              </el-descriptions-item>
              <el-descriptions-item :label="$t('evolution.maxCycles')" :span="2">
                {{ evolutionStatus.config.max_cycles }}
              </el-descriptions-item>
              <el-descriptions-item :label="$t('evolution.goals')" :span="2">
                <el-tag
                  v-for="(goal, index) in evolutionStatus.config.goals"
                  :key="index"
                  size="small"
                  style="margin-right: 4px; margin-bottom: 4px;"
                >
                  {{ goal }}
                </el-tag>
                <span v-if="!evolutionStatus.config.goals.length" style="color: var(--el-text-color-secondary);">
                  {{ $t('evolution.noGoals') }}
                </span>
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </el-card>

        <!-- Current Cycle Status -->
        <el-card shadow="never" style="margin-bottom: 16px;" v-if="evolutionStatus?.current_cycle">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>{{ $t('evolution.currentCycle') }}: {{ evolutionStatus.current_cycle.cycle_id }}</span>
              <el-tag :type="getStatusType(evolutionStatus.current_cycle.status)">
                {{ getStatusLabel(evolutionStatus.current_cycle.status) }}
              </el-tag>
            </div>
          </template>

          <!-- Phase Progress -->
          <div style="margin-bottom: 16px;">
            <div style="font-weight: 500; margin-bottom: 8px;">{{ $t('evolution.phases') }}</div>
            <el-steps :active="getPhaseIndex(evolutionStatus.current_cycle.current_phase)" finish-status="success" align-center>
              <el-step title="PLAN" :description="getPhaseStatus('plan')" />
              <el-step title="DO" :description="getPhaseStatus('do')" />
              <el-step title="CHECK" :description="getPhaseStatus('check')" />
              <el-step title="ACT" :description="getPhaseStatus('act')" />
            </el-steps>
          </div>

          <!-- Action Buttons -->
          <div style="display: flex; gap: 8px;">
            <el-button
              v-if="isRunning && !isPaused"
              type="warning"
              size="small"
              @click="handlePause"
              :loading="actionLoading"
            >
              <el-icon><VideoPause /></el-icon>
              {{ $t('evolution.pause') }}
            </el-button>
            <el-button
              v-if="isPaused"
              type="success"
              size="small"
              @click="handleResume"
              :loading="actionLoading"
            >
              <el-icon><VideoPlay /></el-icon>
              {{ $t('evolution.resume') }}
            </el-button>
            <el-button
              v-if="isRunning || isPaused"
              type="danger"
              size="small"
              @click="handleAbort"
              :loading="actionLoading"
            >
              <el-icon><CloseBold /></el-icon>
              {{ $t('evolution.abort') }}
            </el-button>
            <el-button
              size="small"
              @click="handleViewCycle"
            >
              <el-icon><View /></el-icon>
              {{ $t('evolution.viewDetails') }}
            </el-button>
          </div>
        </el-card>

        <!-- Manual Trigger -->
        <el-card shadow="never" style="margin-bottom: 16px;" v-if="!isRunning">
          <template #header>
            <span>{{ $t('evolution.manualTrigger') }}</span>
          </template>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 13px; color: var(--el-text-color-secondary);">
              {{ $t('evolution.manualTriggerDescription') }}
            </span>
            <el-button
              type="primary"
              size="small"
              @click="handleTrigger"
              :loading="triggerLoading"
            >
              <el-icon><CaretRight /></el-icon>
              {{ $t('evolution.triggerNow') }}
            </el-button>
          </div>
        </el-card>

        <!-- Cycle History -->
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>{{ $t('evolution.cycleHistory') }}</span>
              <el-button
                size="small"
                @click="loadStatus"
                :loading="loading"
              >
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </template>

          <el-table :data="cycleHistory" stripe style="width: 100%;" max-height="400">
            <el-table-column prop="cycle_id" :label="$t('evolution.cycleId')" width="100" />
            <el-table-column prop="status" :label="$t('evolution.status')" width="120">
              <template #default="scope">
                <el-tag :type="getStatusType(scope.row.status)" size="small">
                  {{ getStatusLabel(scope.row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="current_phase" :label="$t('evolution.currentPhase')" width="100">
              <template #default="scope">
                {{ scope.row.current_phase?.toUpperCase() || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="started_at" :label="$t('evolution.startedAt')" width="180">
              <template #default="scope">
                {{ formatDate(scope.row.started_at) }}
              </template>
            </el-table-column>
            <el-table-column :label="$t('evolution.actions')" width="150" align="right">
              <template #default="scope">
                <el-button
                  size="small"
                  @click="handleViewCycleDetail(scope.row.cycle_id)"
                >
                  {{ $t('evolution.view') }}
                </el-button>
                <el-popconfirm
                  :title="$t('evolution.deleteConfirm')"
                  :confirm-button-text="$t('common.confirm')"
                  :cancel-button-text="$t('common.cancel')"
                  @confirm="handleDeleteCycle(scope.row.cycle_id)"
                >
                  <template #reference>
                    <el-button
                      size="small"
                      type="danger"
                      :disabled="scope.row.status === 'running'"
                    >
                      {{ $t('common.delete') }}
                    </el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
    </div>

    <!-- Config Dialog -->
    <el-dialog
      v-model="showConfigDialog"
      :title="$t('evolution.editConfig')"
      width="600px"
    >
      <el-form :model="configForm" label-width="120px">
        <el-form-item :label="$t('evolution.schedule')">
          <el-select v-model="configForm.schedule" style="width: 100%;">
            <el-option label="每小时" value="0 * * * *" />
            <el-option label="每天" value="0 0 * * *" />
            <el-option label="每周" value="0 0 * * 0" />
            <el-option label="每月" value="0 0 1 * *" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('evolution.phaseDuration')">
          <el-input v-model="configForm.phase_duration" placeholder="15m" />
        </el-form-item>
        <el-form-item :label="$t('evolution.maxCycles')">
          <el-input-number v-model="configForm.max_cycles" :min="1" :max="9999" />
        </el-form-item>
        <el-form-item :label="$t('evolution.goals')">
          <el-input
            v-model="goalsInput"
            type="textarea"
            :rows="3"
            :placeholder="$t('evolution.goalsPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showConfigDialog = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="handleSaveConfig" :loading="savingConfig">
          {{ $t('common.save') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Cycle Detail Dialog -->
    <el-dialog
      v-model="showCycleDetailDialog"
      :title="`${$t('evolution.cycleDetails')}: ${currentCycleId}`"
      width="80%"
      top="5vh"
    >
      <el-tabs v-model="activeTab" v-loading="loadingCycleDetail">
        <el-tab-pane :label="$t('evolution.overview')" name="overview">
          <div v-if="cycleDetail">
            <el-descriptions :column="2" border>
              <el-descriptions-item :label="$t('evolution.cycleId')">
                {{ cycleDetail.metadata.cycle_id }}
              </el-descriptions-item>
              <el-descriptions-item :label="$t('evolution.status')">
                <el-tag :type="getStatusType(cycleDetail.metadata.status)">
                  {{ getStatusLabel(cycleDetail.metadata.status) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('evolution.startedAt')">
                {{ formatDate(cycleDetail.metadata.started_at) }}
              </el-descriptions-item>
              <el-descriptions-item :label="$t('evolution.completedAt')">
                {{ cycleDetail.metadata.completed_at ? formatDate(cycleDetail.metadata.completed_at) : '-' }}
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </el-tab-pane>
        <el-tab-pane label="PLAN" name="plan">
          <el-input
            v-if="cycleDetail"
            type="textarea"
            :rows="20"
            :model-value="cycleDetail.phases.plan"
            readonly
          />
        </el-tab-pane>
        <el-tab-pane label="DO" name="do">
          <el-input
            v-if="cycleDetail"
            type="textarea"
            :rows="20"
            :model-value="cycleDetail.phases.do"
            readonly
          />
        </el-tab-pane>
        <el-tab-pane label="CHECK" name="check">
          <el-input
            v-if="cycleDetail"
            type="textarea"
            :rows="20"
            :model-value="cycleDetail.phases.check"
            readonly
          />
        </el-tab-pane>
        <el-tab-pane label="ACT" name="act">
          <el-input
            v-if="cycleDetail"
            type="textarea"
            :rows="20"
            :model-value="cycleDetail.phases.act"
            readonly
          />
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import {
  Setting,
  VideoPause,
  VideoPlay,
  CloseBold,
  View,
  Refresh,
  CaretRight
} from '@element-plus/icons-vue';
import { evolutionService } from '@/services/api/evolution';
import type {
  EvolutionConfig,
  EvolutionStatusResponse,
  CycleDetailResponse
} from '@/services/api/evolution';

const props = defineProps<{
  workspaceId: string;
}>();

const { t } = useI18n();

// State
const loading = ref(false);
const savingConfig = ref(false);
const actionLoading = ref(false);
const triggerLoading = ref(false);
const loadingCycleDetail = ref(false);

const evolutionEnabled = ref(false);
const evolutionStatus = ref<EvolutionStatusResponse | null>(null);

const showConfigDialog = ref(false);
const showCycleDetailDialog = ref(false);
const activeTab = ref('overview');

const configForm = ref<EvolutionConfig>({
  enabled: false,
  schedule: '0 * * * *',
  phase_duration: '15m',
  max_cycles: 999,
  goals: []
});

const goalsInput = ref('');

const cycleHistory = computed(() => evolutionStatus.value?.all_cycles || []);
const currentCycleId = ref('');
const cycleDetail = ref<CycleDetailResponse | null>(null);

const isRunning = computed(() => evolutionStatus.value?.is_running || false);
const isPaused = computed(() => evolutionStatus.value?.is_paused || false);

// Methods
const loadStatus = async () => {
  loading.value = true;
  try {
    const response = await evolutionService.getEvolutionStatus(props.workspaceId);
    evolutionStatus.value = response.data;
    evolutionEnabled.value = response.data.enabled;

    if (response.data.config) {
      configForm.value = { ...response.data.config };
      goalsInput.value = response.data.config.goals.join('\n');
    }
  } catch (error) {
    console.error('Failed to load evolution status:', error);
    ElMessage.error(t('evolution.loadFailed'));
  } finally {
    loading.value = false;
  }
};

const handleEnableChange = async (enabled: boolean) => {
  savingConfig.value = true;
  try {
    if (enabled) {
      await evolutionService.enableEvolution(props.workspaceId, configForm.value);
      ElMessage.success(t('evolution.enabled'));
    } else {
      await evolutionService.disableEvolution(props.workspaceId);
      ElMessage.success(t('evolution.disabled'));
    }
    await loadStatus();
  } catch (error) {
    console.error('Failed to toggle evolution:', error);
    ElMessage.error(t('evology.toggleFailed'));
    evolutionEnabled.value = !enabled; // Revert
  } finally {
    savingConfig.value = false;
  }
};

const handleSaveConfig = async () => {
  savingConfig.value = true;
  try {
    // Parse goals
    const goals = goalsInput.value
      .split('\n')
      .map(g => g.trim())
      .filter(g => g);

    const config = {
      ...configForm.value,
      goals
    };

    await evolutionService.enableEvolution(props.workspaceId, config);
    ElMessage.success(t('evolution.configSaved'));
    showConfigDialog.value = false;
    await loadStatus();
  } catch (error) {
    console.error('Failed to save config:', error);
    ElMessage.error(t('evolution.saveConfigFailed'));
  } finally {
    savingConfig.value = false;
  }
};

const handleTrigger = async () => {
  triggerLoading.value = true;
  try {
    const response = await evolutionService.triggerEvolution(props.workspaceId);
    ElMessage.success(t('evolution.triggered', { cycleId: response.data.cycle_id }));
    await loadStatus();
  } catch (error) {
    console.error('Failed to trigger evolution:', error);
    ElMessage.error(t('evolution.triggerFailed'));
  } finally {
    triggerLoading.value = false;
  }
};

const handlePause = async () => {
  if (!evolutionStatus.value?.current_cycle) return;

  actionLoading.value = true;
  try {
    await evolutionService.pauseCycle(props.workspaceId, evolutionStatus.value.current_cycle.cycle_id);
    ElMessage.success(t('evolution.paused'));
    await loadStatus();
  } catch (error) {
    console.error('Failed to pause cycle:', error);
    ElMessage.error(t('evolution.pauseFailed'));
  } finally {
    actionLoading.value = false;
  }
};

const handleResume = async () => {
  if (!evolutionStatus.value?.current_cycle) return;

  actionLoading.value = true;
  try {
    await evolutionService.resumeCycle(props.workspaceId, evolutionStatus.value.current_cycle.cycle_id);
    ElMessage.success(t('evolution.resumed'));
    await loadStatus();
  } catch (error) {
    console.error('Failed to resume cycle:', error);
    ElMessage.error(t('evolution.resumeFailed'));
  } finally {
    actionLoading.value = false;
  }
};

const handleAbort = async () => {
  if (!evolutionStatus.value?.current_cycle) return;

  actionLoading.value = true;
  try {
    await evolutionService.abortCycle(props.workspaceId, evolutionStatus.value.current_cycle.cycle_id);
    ElMessage.success(t('evolution.aborted'));
    await loadStatus();
  } catch (error) {
    console.error('Failed to abort cycle:', error);
    ElMessage.error(t('evolution.abortFailed'));
  } finally {
    actionLoading.value = false;
  }
};

const handleViewCycle = () => {
  if (evolutionStatus.value?.current_cycle) {
    handleViewCycleDetail(evolutionStatus.value.current_cycle.cycle_id);
  }
};

const handleViewCycleDetail = async (cycleId: string) => {
  currentCycleId.value = cycleId;
  showCycleDetailDialog.value = true;
  activeTab.value = 'overview';

  loadingCycleDetail.value = true;
  try {
    const response = await evolutionService.getCycleDetail(props.workspaceId, cycleId);
    cycleDetail.value = response.data;
  } catch (error) {
    console.error('Failed to load cycle detail:', error);
    ElMessage.error(t('evolution.loadDetailFailed'));
  } finally {
    loadingCycleDetail.value = false;
  }
};

const handleDeleteCycle = async (cycleId: string) => {
  try {
    await evolutionService.deleteCycle(props.workspaceId, cycleId);
    ElMessage.success(t('evolution.cycleDeleted'));
    await loadStatus();
  } catch (error) {
    console.error('Failed to delete cycle:', error);
    ElMessage.error(t('evolution.deleteFailed'));
  }
};

// Helper functions
const getStatusType = (status: string) => {
  const typeMap: Record<string, any> = {
    pending: 'info',
    running: 'warning',
    paused: 'warning',
    completed: 'success',
    aborted: 'danger',
    failed: 'danger'
  };
  return typeMap[status] || 'info';
};

const getStatusLabel = (status: string) => {
  const labelMap: Record<string, string> = {
    pending: t('evolution.statusPending'),
    running: t('evolution.statusRunning'),
    paused: t('evolution.statusPaused'),
    completed: t('evolution.statusCompleted'),
    aborted: t('evolution.statusAborted'),
    failed: t('evolution.statusFailed')
  };
  return labelMap[status] || status;
};

const getPhaseIndex = (currentPhase: string | null) => {
  const phases = ['plan', 'do', 'check', 'act'];
  return currentPhase ? phases.indexOf(currentPhase) : -1;
};

const getPhaseStatus = (phase: string) => {
  const phaseData = evolutionStatus.value?.current_cycle?.phases[phase];
  if (!phaseData) return '-';

  const statusMap: Record<string, string> = {
    pending: t('evolution.phasePending'),
    in_progress: t('evolution.phaseInProgress'),
    completed: t('evolution.phaseCompleted'),
    failed: t('evolution.phaseFailed')
  };

  return statusMap[phaseData.status] || phaseData.status;
};

const formatSchedule = (schedule: string) => {
  const scheduleMap: Record<string, string> = {
    '0 * * * *': t('evolution.hourly'),
    '0 0 * * *': t('evolution.daily'),
    '0 0 * * 0': t('evolution.weekly'),
    '0 0 1 * *': t('evolution.monthly')
  };
  return scheduleMap[schedule] || schedule;
};

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString();
};

// Lifecycle
onMounted(() => {
  loadStatus();
});
</script>

<style scoped>
.evolution-drawer {
  height: 100%;
  overflow-y: auto;
}

.drawer-content {
  padding: 16px;
}
</style>
