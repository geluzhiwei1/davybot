/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="alert-system-panel">
    <el-card class="alert-card" header="告警系统">
      <template #extra>
        <div class="alert-controls">
          <el-switch
            v-model="alertEnabled"
            active-text="启用"
            inactive-text="禁用"
            @change="onAlertToggle"
          />
          <el-button 
            size="small"
            @click="showRuleDialog = true"
          >
            <el-icon><Setting /></el-icon>
            规则配置
          </el-button>
          <el-button
            size="small"
            @click="handleClearAlerts"
          >
            <el-icon><Delete /></el-icon>
            清除
          </el-button>
        </div>
      </template>

      <!-- 告警统计 -->
      <div class="alert-statistics">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-statistic 
              title="严重告警" 
              :value="criticalAlerts.length"
              :value-style="{ color: '#f56c6c' }"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic 
              title="高级告警" 
              :value="highAlerts.length"
              :value-style="{ color: '#e6a23c' }"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic 
              title="中级告警" 
              :value="mediumAlerts.length"
              :value-style="{ color: '#409eff' }"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic 
              title="低级告警" 
              :value="lowAlerts.length"
              :value-style="{ color: '#67c23a' }"
            />
          </el-col>
        </el-row>
      </div>

      <!-- 告警列表 -->
      <el-tabs v-model="activeTab" class="alert-tabs">
        <el-tab-pane label="实时告警" name="realtime">
          <div class="alert-list">
            <div
              v-for="alert in recentAlerts"
              :key="alert.alertId"
              class="alert-item"
              :class="getAlertItemClass(alert.severity)"
            >
              <div class="alert-header">
                <div class="alert-title">
                  <span class="alert-icon">
                    <Warning v-if="alert.severity === 'high'" />
                    <CircleCloseFilled v-else-if="alert.severity === 'critical'" />
                    <InfoFilled v-else />
                  </span>
                  {{ alert.title }}
                </div>
                <div class="alert-time">
                  {{ formatTimestamp(alert.timestamp, 'time') }}
                </div>
              </div>
              
              <div class="alert-content">
                <p>{{ alert.message }}</p>
                <div class="alert-details">
                  <el-tag :type="getSeverityTagType(alert.severity)" size="small">
                    {{ getSeverityText(alert.severity) }}
                  </el-tag>
                  <span class="alert-metric">
                    指标: {{ alert.metric }}
                  </span>
                  <span class="alert-threshold">
                    阈值: {{ alert.threshold }}
                  </span>
                  <span class="alert-current">
                    当前值: {{ alert.currentValue }}
                  </span>
                </div>
              </div>
              
              <div class="alert-actions">
                <el-button 
                  size="small" 
                  type="primary"
                  @click="viewAlertDetail(alert)"
                >
                  详情
                </el-button>
                <el-button 
                  size="small"
                  @click="dismissAlert(alert)"
                >
                  忽略
                </el-button>
              </div>
            </div>
          </div>
        </el-tab-pane>
        
        <el-tab-pane label="告警规则" name="rules">
          <div class="rules-list">
            <el-table :data="alertRules" stripe>
              <el-table-column prop="name" label="规则名称" />
              <el-table-column prop="description" label="描述" />
              <el-table-column prop="metric" label="监控指标" />
              <el-table-column prop="condition.threshold" label="阈值" />
              <el-table-column prop="severity" label="严重程度">
                <template #default="{ row }">
                  <el-tag :type="getSeverityTagType(row.severity)" size="small">
                    {{ getSeverityText(row.severity) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="enabled" label="状态">
                <template #default="{ row }">
                  <el-switch
                    v-model="row.enabled"
                    @change="updateAlertRule(row)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150">
                <template #default="{ row }">
                  <el-button 
                    size="small" 
                    type="primary"
                    @click="editRule(row)"
                  >
                    编辑
                  </el-button>
                  <el-button 
                    size="small" 
                    type="danger"
                    @click="deleteRule(row)"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>
        
        <el-tab-pane label="告警历史" name="history">
          <div class="alert-history">
            <el-table :data="alertHistory" stripe v-loading="historyLoading">
              <el-table-column prop="title" label="告警标题" />
              <el-table-column prop="severity" label="严重程度">
                <template #default="{ row }">
                  <el-tag :type="getSeverityTagType(row.severity)" size="small">
                    {{ getSeverityText(row.severity) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="timestamp" label="时间">
                <template #default="{ row }">
                  {{ formatTimestamp(row.timestamp, 'time') }}
                </template>
              </el-table-column>
              <el-table-column prop="executionId" label="执行ID" />
              <el-table-column prop="nodeId" label="节点ID" />
              <el-table-column label="操作">
                <template #default="{ row }">
                  <el-button 
                    size="small" 
                    type="primary"
                    @click="viewAlertDetail(row)"
                  >
                    详情
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 告警规则配置对话框 -->
    <el-dialog
      v-model="showRuleDialog"
      :title="editingRule ? '编辑告警规则' : '新建告警规则'"
      width="600px"
    >
      <el-form :model="ruleForm" :rules="ruleRules" ref="ruleFormRef" label-width="100px">
        <el-form-item label="规则名称" prop="name">
          <el-input v-model="ruleForm.name" placeholder="请输入规则名称" />
        </el-form-item>
        
        <el-form-item label="描述" prop="description">
          <el-input 
            v-model="ruleForm.description" 
            type="textarea" 
            :rows="3"
            placeholder="请输入规则描述"
          />
        </el-form-item>
        
        <el-form-item label="监控指标" prop="condition.metric">
          <el-select v-model="ruleForm.condition.metric" placeholder="选择监控指标">
            <el-option label="CPU使用率" value="cpu_usage" />
            <el-option label="内存使用率" value="memory_usage" />
            <el-option label="磁盘使用率" value="disk_usage" />
            <el-option label="网络延迟" value="network_latency" />
            <el-option label="任务失败率" value="task_failure_rate" />
            <el-option label="执行时间" value="execution_time" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="条件" prop="condition.operator">
          <el-select v-model="ruleForm.condition.operator" placeholder="选择条件">
            <el-option label="大于" value=">" />
            <el-option label="小于" value="<" />
            <el-option label="等于" value="=" />
            <el-option label="大于等于" value=">=" />
            <el-option label="小于等于" value="<=" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="阈值" prop="condition.threshold">
          <el-input-number 
            v-model="ruleForm.condition.threshold" 
            placeholder="请输入阈值"
            :min="0"
          />
        </el-form-item>
        
        <el-form-item label="持续时间" prop="condition.duration">
          <el-input-number 
            v-model="ruleForm.condition.duration" 
            placeholder="持续时间(秒)"
            :min="0"
          />
        </el-form-item>
        
        <el-form-item label="严重程度" prop="severity">
          <el-select v-model="ruleForm.severity" placeholder="选择严重程度">
            <el-option label="低" value="low" />
            <el-option label="中" value="medium" />
            <el-option label="高" value="high" />
            <el-option label="严重" value="critical" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="通知方式">
          <el-checkbox-group v-model="ruleForm.notifications">
            <el-checkbox label="inApp">应用内通知</el-checkbox>
            <el-checkbox label="email">邮件通知</el-checkbox>
            <el-checkbox label="webhook">Webhook通知</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        
        <el-form-item v-if="ruleForm.notifications.includes('email')" label="邮件地址">
          <el-input 
            v-model="ruleForm.emailAddresses" 
            placeholder="请输入邮件地址，多个地址用逗号分隔"
          />
        </el-form-item>
        
        <el-form-item v-if="ruleForm.notifications.includes('webhook')" label="Webhook URL">
          <el-input 
            v-model="ruleForm.webhookUrl" 
            placeholder="请输入Webhook URL"
          />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showRuleDialog = false">取消</el-button>
        <el-button type="primary" @click="saveRule">保存</el-button>
      </template>
    </el-dialog>

    <!-- 告警详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      title="告警详情"
      width="600px"
    >
      <div v-if="selectedAlert" class="alert-detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="告警ID">
            {{ selectedAlert.alertId }}
          </el-descriptions-item>
          <el-descriptions-item label="标题">
            {{ selectedAlert.title }}
          </el-descriptions-item>
          <el-descriptions-item label="严重程度">
            <el-tag :type="getSeverityTagType(selectedAlert.severity)">
              {{ getSeverityText(selectedAlert.severity) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="时间">
            {{ formatTimestamp(selectedAlert.timestamp, 'time') }}
          </el-descriptions-item>
          <el-descriptions-item label="监控指标">
            {{ selectedAlert.metric }}
          </el-descriptions-item>
          <el-descriptions-item label="阈值">
            {{ selectedAlert.threshold }}
          </el-descriptions-item>
          <el-descriptions-item label="当前值">
            {{ selectedAlert.currentValue }}
          </el-descriptions-item>
          <el-descriptions-item v-if="selectedAlert.executionId" label="执行ID">
            {{ selectedAlert.executionId }}
          </el-descriptions-item>
          <el-descriptions-item v-if="selectedAlert.nodeId" label="节点ID">
            {{ selectedAlert.nodeId }}
          </el-descriptions-item>
          <el-descriptions-item label="详细消息">
            {{ selectedAlert.message }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
      
      <template #footer>
        <el-button @click="showDetailDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMonitoringStore } from '@/stores/monitoring'
import { monitoringService } from '@/services/monitoring'
import { ElMessage } from 'element-plus'
import { formatTimestamp } from '@/utils/formatters'
import {
  Setting,
  Delete,
  Warning,
  CircleCloseFilled,
  InfoFilled
} from '@element-plus/icons-vue'
import type {
  AlertRule,
  PerformanceAlert
} from '@/types/monitoring'

const monitoringStore = useMonitoringStore()
const {
  state,
  criticalAlerts,
  highAlerts,
  updateConfig,
  clearAlerts
} = monitoringStore

// 从state获取其他alerts
const recentAlerts = computed(() => state.recentAlerts || [])
const mediumAlerts = computed(() => recentAlerts.value.filter((a: PerformanceAlert) => a.severity === 'medium'))
const lowAlerts = computed(() => recentAlerts.value.filter((a: PerformanceAlert) => a.severity === 'low'))

// 状态
const alertEnabled = ref(true)
const activeTab = ref('realtime')
const showRuleDialog = ref(false)
const showDetailDialog = ref(false)
const editingRule = ref<AlertRule | null>(null)
const selectedAlert = ref<PerformanceAlert | null>(null)
const historyLoading = ref(false)

// 告警规则
const alertRules = ref<AlertRule[]>([])

// 表单数据
const ruleForm = ref({
  name: '',
  description: '',
  condition: {
    metric: '',
    operator: '>',
    threshold: 0,
    duration: 60
  },
  severity: 'medium',
  notifications: [] as string[],
  emailAddresses: '',
  webhookUrl: ''
})

// 告警历史
const alertHistory = ref<PerformanceAlert[]>([])

// 表单验证规则
const ruleRules = {
  name: [
    { required: true, message: '请输入规则名称', trigger: 'blur' }
  ],
  description: [
    { required: true, message: '请输入规则描述', trigger: 'blur' }
  ],
  'condition.metric': [
    { required: true, message: '请选择监控指标', trigger: 'change' }
  ],
  'condition.threshold': [
    { required: true, message: '请输入阈值', trigger: 'blur' }
  ],
  'condition.duration': [
    { required: true, message: '请输入持续时间', trigger: 'blur' }
  ],
  severity: [
    { required: true, message: '请选择严重程度', trigger: 'change' }
  ]
}

const ruleFormRef = ref()

// 获取告警项样式类
const getAlertItemClass = (severity: string): string => {
  return `alert-item-${severity}`
}

// 获取严重程度标签类型
const getSeverityTagType = (severity: string): string => {
  const types: Record<string, string> = {
    low: 'success',
    medium: 'primary',
    high: 'warning',
    critical: 'danger'
  }
  return types[severity] || 'info'
}

// 获取严重程度文本
const getSeverityText = (severity: string): string => {
  const texts: Record<string, string> = {
    low: '低',
    medium: '中',
    high: '高',
    critical: '严重'
  }
  return texts[severity] || '未知'
}

// 使用统一的格式化函数（从 @/utils/formatters 导入）

// 告警开关切换
const onAlertToggle = (enabled: boolean) => {
  updateConfig({ enableAlerts: enabled })
  ElMessage.success(enabled ? '告警已启用' : '告警已禁用')
}

// 清除告警
const handleClearAlerts = () => {
  clearAlerts()
  ElMessage.success('告警已清除')
}

// 查看告警详情
const viewAlertDetail = (alert: PerformanceAlert) => {
  selectedAlert.value = alert
  showDetailDialog.value = true
}

// 忽略告警
const dismissAlert = (alert: PerformanceAlert) => {
  // 从告警列表中移除
  const index = recentAlerts.value.findIndex(a => a.alertId === alert.alertId)
  if (index !== -1) {
    recentAlerts.value.splice(index, 1)
  }
  ElMessage.success('告警已忽略')
}

// 编辑规则
const editRule = (rule: AlertRule) => {
  editingRule.value = rule
  ruleForm.value = {
    name: rule.name,
    description: rule.description,
    condition: { ...rule.condition },
    severity: rule.severity,
    notifications: Object.keys(rule.notifications).filter(key => rule.notifications[key as keyof typeof rule.notifications]).map((key: string) => {
      if (key === 'email') {
        return 'email'
      } else if (key === 'webhook') {
        return 'webhook'
      } else {
        return key
      }
    }),
    emailAddresses: rule.notifications.email ? rule.notifications.email.join(', ') : '',
    webhookUrl: rule.notifications.webhook || ''
  }
  showRuleDialog.value = true
}

// 删除规则
const deleteRule = async (rule: AlertRule) => {
  try {
    await ElMessageBox.confirm('确定要删除此告警规则吗？', '确认删除', {
      type: 'warning'
    })
    
    await monitoringService.deleteAlertRule(rule.id)
    await loadAlertRules()
    ElMessage.success('规则已删除')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除规则失败')
    }
  }
}

// 更新告警规则
const updateAlertRule = async (rule: AlertRule) => {
  try {
    await monitoringService.updateAlertRule(rule.id, { enabled: rule.enabled })
    ElMessage.success('规则已更新')
  } catch {
    ElMessage.error('更新规则失败')
  }
}

// 保存规则
const saveRule = async () => {
  if (!ruleFormRef.value) return
  
  try {
    await ruleFormRef.value.validate()
    
    const notifications: unknown = {}
    ruleForm.value.notifications.forEach(notification => {
      if (notification === 'email') {
        notifications.email = ruleForm.value.emailAddresses.split(',').map(email => email.trim())
      } else if (notification === 'webhook') {
        notifications.webhook = ruleForm.value.webhookUrl
      } else {
        notifications[notification] = true
      }
    })

    const ruleData: Partial<AlertRule> = {
      name: ruleForm.value.name,
      description: ruleForm.value.description,
      condition: {
        ...ruleForm.value.condition,
        operator: ruleForm.value.condition.operator as ">" | "<" | "=" | ">=" | "<="
      },
      severity: ruleForm.value.severity as 'low' | 'medium' | 'high' | 'critical',
      enabled: true,
      notifications
    }

    if (editingRule.value) {
      await monitoringService.updateAlertRule(editingRule.value.id, ruleData)
      ElMessage.success('规则已更新')
    } else {
      await monitoringService.createAlertRule(ruleData as Omit<AlertRule, 'createdAt' | 'updatedAt' | 'id'>)
      ElMessage.success('规则已创建')
    }
    
    await loadAlertRules()
    showRuleDialog.value = false
    resetRuleForm()
  } catch {
    ElMessage.error('保存规则失败')
  }
}

// 重置表单
const resetRuleForm = () => {
  ruleForm.value = {
    name: '',
    description: '',
    condition: {
      metric: '',
      operator: '>',
      threshold: 0,
      duration: 60
    },
    severity: 'medium',
    notifications: [] as string[],
    emailAddresses: '',
    webhookUrl: ''
  }
  editingRule.value = null
}

// 加载告警规则
const loadAlertRules = async () => {
  try {
    alertRules.value = await monitoringService.getAlertRules()
  } catch (error) {
    console.error('加载告警规则失败:', error)
  }
}

// 加载告警历史
const loadAlertHistory = async () => {
  historyLoading.value = true
  try {
    alertHistory.value = await monitoringService.getAlertHistory(100)
  } catch (error) {
    console.error('加载告警历史失败:', error)
  } finally {
    historyLoading.value = false
  }
}

onMounted(() => {
  alertEnabled.value = state.config.enableAlerts
  loadAlertRules()
  loadAlertHistory()
})
</script>

<style scoped>
.alert-system-panel {
  height: 100%;
}

.alert-card {
  height: 100%;
}

.alert-controls {
  display: flex;
  gap: 10px;
  align-items: center;
}

.alert-statistics {
  margin-bottom: 20px;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 4px;
}

.alert-tabs {
  margin-top: 20px;
}

.alert-list {
  max-height: 400px;
  overflow-y: auto;
}

.alert-item {
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  margin-bottom: 10px;
  padding: 15px;
  transition: all 0.3s;
}

.alert-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.alert-item-critical {
  border-left: 4px solid #f56c6c;
  background-color: #fef0f0;
}

.alert-item-high {
  border-left: 4px solid #e6a23c;
  background-color: #fdf6ec;
}

.alert-item-medium {
  border-left: 4px solid #409eff;
  background-color: #ecf5ff;
}

.alert-item-low {
  border-left: 4px solid #67c23a;
  background-color: #f0f9ff;
}

.alert-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.alert-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: bold;
  font-size: 16px;
  color: #303133;
}

.alert-icon {
  font-size: 18px;
}

.alert-time {
  font-size: 12px;
  color: #909399;
}

.alert-content p {
  margin: 0 0 10px 0;
  color: #606266;
}

.alert-details {
  display: flex;
  gap: 15px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #909399;
}

.alert-metric {
  background-color: #f0f0f0;
  padding: 2px 6px;
  border-radius: 2px;
}

.alert-threshold {
  background-color: #f0f0f0;
  padding: 2px 6px;
  border-radius: 2px;
}

.alert-current {
  background-color: #f0f0f0;
  padding: 2px 6px;
  border-radius: 2px;
}

.alert-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.rules-list {
  max-height: 400px;
  overflow-y: auto;
}

.alert-history {
  max-height: 400px;
  overflow-y: auto;
}

.alert-detail {
  padding: 20px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .alert-controls {
    flex-direction: column;
    align-items: stretch;
  }
  
  .alert-statistics .el-col {
    margin-bottom: 15px;
  }
  
  .alert-list {
    max-height: 300px;
  }
  
  .rules-list {
    max-height: 300px;
  }
  
  .alert-history {
    max-height: 300px;
  }
}
</style>