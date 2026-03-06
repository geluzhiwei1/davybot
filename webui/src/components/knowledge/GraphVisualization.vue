<!-- Knowledge Graph Visualization Component -->
<template>
  <div class="graph-visualization">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p>{{ t('knowledge.graphLoading') }}</p>
    </div>

    <!-- 错误状态 -->
    <el-alert
      v-else-if="error"
      type="error"
      :title="error"
      :closable="false"
      show-icon
    />

    <!-- 图谱控制栏 -->
    <div v-else class="graph-controls">
      <div class="control-group">
        <el-input
          v-model="searchQuery"
          :placeholder="t('knowledge.searchEntities')"
          clearable
          style="width: 200px;"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <el-select
          v-model="filterType"
          :placeholder="t('knowledge.filterEntityType')"
          clearable
          style="width: 150px;"
        >
          <el-option label="All" value="" />
          <el-option label="PERSON" value="PERSON" />
          <el-option label="ORG" value="ORG" />
          <el-option label="TECH" value="TECH" />
          <el-option label="CONCEPT" value="CONCEPT" />
          <el-option label="chunk" value="chunk" />
          <el-option label="document" value="document" />
        </el-select>

        <el-select
          v-model="layoutType"
          :placeholder="'Layout'"
          style="width: 150px;"
        >
          <el-option label="Force" value="force" />
          <el-option label="Circular" value="circular" />
          <el-option label="Radial" value="radial" />
        </el-select>

        <el-button :icon="Refresh" @click="loadGraphData">
          {{ t('knowledge.refresh') }}
        </el-button>

        <el-button :icon="ZoomIn" @click="zoomIn">+</el-button>
        <el-button :icon="ZoomOut" @click="zoomOut">-</el-button>
        <el-button :icon="FullScreen" @click="toggleFullscreen">
          {{ isFullscreen ? t('knowledge.exitFullscreen') : t('knowledge.fullscreen') }}
        </el-button>
      </div>

      <div class="stats-info">
        <el-tag>Nodes: {{ filteredEntities.length }}</el-tag>
        <el-tag type="success">Edges: {{ filteredRelations.length }}</el-tag>
      </div>
    </div>

    <!-- ECharts 图谱容器 -->
    <v-chart
      v-show="!loading && !error"
      ref="chartRef"
      class="graph-chart"
      :option="chartOption"
      :autoresize="true"
      @click="handleChartClick"
    />

    <!-- 实体详情抽屉 -->
    <el-drawer
      v-model="detailsDrawerVisible"
      :title="t('knowledge.entityDetails')"
      size="400px"
    >
      <div v-if="selectedEntity" class="entity-details">
        <el-descriptions :column="1" border>
          <el-descriptions-item :label="t('knowledge.entityName')">
            {{ selectedEntity.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('knowledge.entityType')">
            <el-tag :type="getEntityTypeColor(selectedEntity.type)">
              {{ selectedEntity.type }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="selectedEntity.description" :label="t('knowledge.description')">
            {{ selectedEntity.description }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('knowledge.connections')">
            {{ getEntityConnections(selectedEntity.id) }}
          </el-descriptions-item>
        </el-descriptions>

        <el-divider />

        <h4>{{ t('knowledge.properties') }}</h4>
        <el-table :data="getPropertiesList(selectedEntity)" size="small" max-height="300">
          <el-table-column prop="key" label="Key" width="150" />
          <el-table-column prop="value" label="Value" />
        </el-table>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  Loading,
  Search,
  Refresh,
  ZoomIn,
  ZoomOut,
  FullScreen
} from '@element-plus/icons-vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  TitleComponent
} from 'echarts/components'
import type { EChartsOption } from 'echarts'
import { knowledgeBasesApi } from '@/services/api/knowledge'
import type { GraphEntity, GraphRelation } from '@/types/knowledge'
import { logger } from '@/utils/logger'

// 注册 ECharts 组件
use([
  CanvasRenderer,
  GraphChart,
  GridComponent,
  TooltipComponent,
  TitleComponent
])

const { t } = useI18n()

// Props
const props = defineProps<{
  baseId: string
}>()

// 状态
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')
const filterType = ref('')
const layoutType = ref<'force' | 'circular' | 'radial'>('force')
const isFullscreen = ref(false)
const detailsDrawerVisible = ref(false)
const selectedEntity = ref<GraphEntity | null>(null)

// 图谱数据
const entities = ref<GraphEntity[]>([])
const relations = ref<GraphRelation[]>([])

// ECharts 实例
const chartRef = ref<InstanceType<typeof VChart> | null>(null)

// 计算属性：过滤后的数据
const filteredEntities = computed(() => {
  let filtered = entities.value

  // 按类型过滤
  if (filterType.value) {
    filtered = filtered.filter(e => e.type === filterType.value)
  }

  // 按搜索关键词过滤
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(e =>
      e.name.toLowerCase().includes(query) ||
      e.description?.toLowerCase().includes(query)
    )
  }

  return filtered
})

const filteredRelations = computed(() => {
  const entityIds = new Set(filteredEntities.value.map(e => e.id))
  return relations.value.filter(r =>
    entityIds.has(r.from_entity) && entityIds.has(r.to_entity)
  )
})

// ECharts 配置
const chartOption = computed<EChartsOption>(() => {
  // 构建节点数据
  const nodes = filteredEntities.value.map(entity => ({
    id: entity.id,
    name: entity.name,
    category: entity.type,
    value: entity.properties?.size || 10,
    symbolSize: getEntitySymbolSize(entity.type),
    itemStyle: {
      color: getEntityColor(entity.type)
    },
    label: {
      show: true,
      position: 'right',
      formatter: (params: any) => {
        const name = params.data.name as string
        return name.length > 10 ? name.substring(0, 10) + '...' : name
      }
    }
  }))

  // 构建边数据
  const edges = filteredRelations.value.map(rel => ({
    source: rel.from_entity,
    target: rel.to_entity,
    name: rel.relation_type,
    lineStyle: {
      color: '#ddd',
      curveness: 0.3
    }
  }))

  // 类别（用于图例）
  const categories = Array.from(new Set(filteredEntities.value.map(e => e.type)))

  return {
    tooltip: {
      formatter: (params: any) => {
        if (params.dataType === 'node') {
          return `
            <div style="padding: 8px;">
              <strong>${params.data.name}</strong><br/>
              Type: ${params.data.category}<br/>
              Connections: ${params.data.value}
            </div>
          `
        } else if (params.dataType === 'edge') {
          return `
            <div style="padding: 8px;">
              <strong>${params.data.name}</strong><br/>
              ${params.data.source} → ${params.data.target}
            </div>
          `
        }
        return ''
      }
    },
    legend: [{
      data: categories,
      top: 10,
      right: 10
    }],
    series: [
      {
        type: 'graph',
        layout: layoutType.value,
        data: nodes,
        links: edges,
        categories: categories.map(cat => ({ name: cat })),
        roam: true,
        label: {
          position: 'right',
          formatter: '{b}'
        },
        labelLayout: {
          hideOverlap: true
        },
        scaleLimit: {
          min: 0.3,
          max: 3
        },
        lineStyle: {
          color: 'source',
          curveness: 0.3
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: {
            width: 3
          }
        },
        force: {
          repulsion: 300,
          edgeLength: [50, 150],
          gravity: 0.1,
          layoutAnimation: true
        },
        circular: {
          rotateLabel: true
        },
        radial: {
          focusNodeExpansion: true
        }
      }
    ]
  }
})

// 获取实体符号大小
const getEntitySymbolSize = (type: string) => {
  const sizes: Record<string, number> = {
    'document': 30,
    'chunk': 20,
    'PERSON': 25,
    'ORG': 25,
    'TECH': 20,
    'CONCEPT': 18,
    'OTHER': 15
  }
  return sizes[type] || 15
}

// 获取实体颜色
const getEntityColor = (type: string) => {
  const colors: Record<string, string> = {
    'document': '#409EFF',
    'chunk': '#67C23A',
    'PERSON': '#E6A23C',
    'ORG': '#F56C6C',
    'TECH': '#909399',
    'CONCEPT': '#606266',
    'OTHER': '#C0C4CC'
  }
  return colors[type] || '#C0C4CC'
}

// 获取实体类型颜色标签
const getEntityTypeColor = (type: string) => {
  const colors: Record<string, string> = {
    'PERSON': 'warning',
    'ORG': 'danger',
    'TECH': 'info',
    'CONCEPT': 'success',
    'document': 'primary',
    'chunk': 'success'
  }
  return colors[type] || ''
}

// 获取实体连接数
const getEntityConnections = (entityId: string) => {
  const incoming = relations.value.filter(r => r.to_entity === entityId).length
  const outgoing = relations.value.filter(r => r.from_entity === entityId).length
  return `${incoming} in, ${outgoing} out`
}

// 获取属性列表
const getPropertiesList = (entity: GraphEntity) => {
  return Object.entries(entity.properties || {}).map(([key, value]) => ({
    key,
    value: String(value)
  }))
}

// 显示实体详情
const showEntityDetails = (entityId: string) => {
  selectedEntity.value = entities.value.find(e => e.id === entityId) || null
  if (selectedEntity.value) {
    detailsDrawerVisible.value = true
  }
}

// 加载图谱数据
const loadGraphData = async () => {
  try {
    loading.value = true
    error.value = ''

    logger.info(`Loading graph data for base: ${props.baseId}`)

    // 并行获取实体和关系数据
    const [entitiesResponse, relationsResponse] = await Promise.all([
      knowledgeBasesApi.getGraphEntities(props.baseId, { limit: 1000 }),
      knowledgeBasesApi.getGraphRelations(props.baseId, { limit: 2000 })
    ])

    // 提取实际数据 - 兼容多种响应格式
    const entitiesData = entitiesResponse.items || entitiesResponse.entities || entitiesResponse.data || entitiesResponse || []
    const relationsData = relationsResponse.items || relationsResponse.relations || relationsResponse.data || relationsResponse || []

    // 确保是数组
    entities.value = Array.isArray(entitiesData) ? entitiesData : []
    relations.value = Array.isArray(relationsData) ? relationsData : []

    logger.info(`Loaded ${entities.value.length} entities and ${relations.value.length} relations`)

    if (entities.value.length === 0) {
      error.value = t('knowledge.noGraphData')
      logger.warn('No entities found in graph data')
      return
    }

    ElMessage.success(t('knowledge.graphLoaded', { count: entities.value.length }))
  } catch (err: any) {
    logger.error('Failed to load graph data:', err)
    error.value = `${t('knowledge.loadGraphFailed')}: ${err.message || err}`
  } finally {
    loading.value = false
  }
}

// 处理图表点击
const handleChartClick = (params: any) => {
  if (params.dataType === 'node' && params.data?.id) {
    showEntityDetails(params.data.id)
  }
}

// 缩放控制
const zoomIn = () => {
  if (chartRef.value) {
    const chart = chartRef.value.getInstance()
    chart.dispatchAction({
      type: 'dataZoom',
      zoom: 1.2
    })
  }
}

const zoomOut = () => {
  if (chartRef.value) {
    const chart = chartRef.value.getInstance()
    chart.dispatchAction({
      type: 'dataZoom',
      zoom: 0.8
    })
  }
}

// 全屏切换
const toggleFullscreen = () => {
  const chartElement = chartRef.value?.$el
  if (!chartElement) return

  if (!document.fullscreenElement) {
    chartElement.requestFullscreen()
    isFullscreen.value = true
  } else {
    document.exitFullscreen()
    isFullscreen.value = false
  }
}

// 监听baseId变化
watch(() => props.baseId, () => {
  if (props.baseId) {
    loadGraphData()
  }
})

// 生命周期
onMounted(() => {
  if (props.baseId) {
    loadGraphData()
  }
})

onUnmounted(() => {
  // 清理资源
})
</script>

<script lang="ts">
export default {
  name: 'GraphVisualization'
}
</script>

<style scoped>
.graph-visualization {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: var(--el-text-color-secondary);
}

.graph-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
}

.control-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.stats-info {
  display: flex;
  gap: 8px;
}

.graph-chart {
  flex: 1;
  min-height: 500px;
  width: 100%;
}

.graph-chart :fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
}

.entity-details {
  padding: 16px 0;
}

.entity-details h4 {
  margin-bottom: 16px;
  color: var(--el-text-color-primary);
}
</style>
