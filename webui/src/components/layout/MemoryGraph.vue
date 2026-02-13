/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="memory-graph" ref="graphContainer">
    <svg
      ref="svgRef"
      :width="width"
      :height="height"
      @mousedown="handleMouseDown"
      @mousemove="handleMouseMove"
      @mouseup="handleMouseUp"
      @wheel="handleWheel"
    >
      <g :transform="`translate(${panX}, ${panY}) scale(${scale})`">
        <!-- Links -->
        <g class="links">
          <line
            v-for="link in graphDataWithPositions.links"
            :key="link.id || `${link.source}-${link.target}`"
            :x1="getNodeById(link.source)?.x || 0"
            :y1="getNodeById(link.source)?.y || 0"
            :x2="getNodeById(link.target)?.x || 0"
            :y2="getNodeById(link.target)?.y || 0"
            :stroke="getLinkColor(link)"
            :stroke-width="getLinkWidth(link)"
            :opacity="link.confidence"
            class="graph-link"
          />
          <!-- Link labels -->
          <text
            v-for="link in graphDataWithPositions.links"
            :key="`label-${link.id || `${link.source}-${link.target}`}`"
            :x="getLinkMidpoint(link).x"
            :y="getLinkMidpoint(link).y"
            text-anchor="middle"
            font-size="10"
            fill="var(--el-text-color-secondary)"
            class="link-label"
          >
            {{ link.label }}
          </text>
        </g>

        <!-- Nodes -->
        <g class="nodes">
          <g
            v-for="node in graphDataWithPositions.nodes"
            :key="node.id"
            :transform="`translate(${node.x}, ${node.y})`"
            class="graph-node"
            :class="{ selected: node.id === selectedId }"
            @click="handleNodeClick(node)"
            @mouseenter="hoveredNodeId = node.id"
            @mouseleave="hoveredNodeId = null"
          >
            <!-- Node circle -->
            <circle
              :r="node.radius || getNodeSize(node)"
              :fill="getNodeColor(node)"
              :stroke="node.id === selectedId ? 'var(--el-color-primary)' : 'none'"
              :stroke-width="node.id === selectedId ? 3 : 0"
              class="node-circle"
            />

            <!-- Node label -->
            <text
              v-if="scale > 0.5"
              y="5"
              text-anchor="middle"
              font-size="11"
              fill="var(--el-text-color-primary)"
              class="node-label"
            >
              {{ truncateText(node.label, 20) }}
            </text>

            <!-- Energy indicator -->
            <circle
              v-if="showEnergy"
              :r="(node.radius || getNodeSize(node)) * 0.3"
              :cx="(node.radius || getNodeSize(node)) * 0.5"
              :cy="-(node.radius || getNodeSize(node)) * 0.5"
              :fill="getEnergyColor(node.energy)"
              class="energy-indicator"
            />
          </g>
        </g>
      </g>
    </svg>

    <!-- Tooltip -->
    <div
      v-if="hoveredNodeId"
      class="graph-tooltip"
      :style="{ left: tooltipX + 'px', top: tooltipY + 'px' }"
    >
      <div class="tooltip-title">{{ getNodeById(hoveredNodeId)?.label }}</div>
      <div class="tooltip-info">
        Type: {{ getNodeById(hoveredNodeId)?.type }}
      </div>
      <div class="tooltip-info">
        Energy: {{ (getNodeById(hoveredNodeId)?.energy * 100).toFixed(0) }}%
      </div>
    </div>

    <!-- Controls -->
    <div class="graph-controls">
      <el-button-group size="small">
        <el-button :icon="ZoomIn" @click="zoomIn" />
        <el-button :icon="ZoomOut" @click="zoomOut" />
        <el-button :icon="RefreshRight" @click="resetView" />
      </el-button-group>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, shallowRef, computed } from 'vue'
import { ZoomIn, ZoomOut, RefreshRight } from '@element-plus/icons-vue'
import type { GraphData, GraphNode, GraphLink } from '@/types/memory'
import { MemoryType } from '@/types/memory'

const props = defineProps<{
  graphData: GraphData
  selectedId?: string | null
}>()

const emit = defineEmits<{
  selectNode: [nodeId: string]
}>()

// Refs
const graphContainer = ref<HTMLElement>()
const svgRef = ref<SVGElement>()

// Local node positions (computed from props but stored locally to avoid mutating props)
const localNodes = shallowRef<GraphNode[]>([])

// View state
const width = ref(400)
const height = ref(400)
const scale = ref(1)
const panX = ref(0)
const panY = ref(0)
const isDragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })
const hoveredNodeId = ref<string | null>(null)
const tooltipX = ref(0)
const tooltipY = ref(0)
const showEnergy = ref(true)

// Derived graph data using local nodes
const graphDataWithPositions = computed(() => ({
  nodes: localNodes.value,
  links: props.graphData.links
}))

// Initialize local nodes from props (deep copy to avoid mutating original)
function initializeLocalNodes() {
  // Only update when node structure changes (not when positions change)
  localNodes.value = props.graphData.nodes.map(node => ({
    ...node
  }))
}

// Recompute layout when graph structure changes
watch(() => props.graphData, () => {
  initializeLocalNodes()
  computeForceLayout()
}, { deep: true })

// Initialize on mount
onMounted(() => {
  if (graphContainer.value) {
    width.value = Math.max(300, graphContainer.value.clientWidth - 24)
    height.value = 400
  }

  // Initial force-directed layout
  initializeLocalNodes()
  computeForceLayout()
})

// Compute force-directed layout
function computeForceLayout() {
  const nodes = localNodes.value
  const links = props.graphData.links

  if (nodes.length === 0) return

  // Initialize positions if not set
  nodes.forEach((node, i) => {
    if (node.x === undefined) {
      const angle = (i / nodes.length) * Math.PI * 2
      const radius = Math.min(width.value, height.value) / 3
      node.x = width.value / 2 + Math.cos(angle) * radius
      node.y = height.value / 2 + Math.sin(angle) * radius
    }
  })

  // Simple force simulation
  const iterations = 50
  const k = Math.sqrt((width.value * height.value) / nodes.length) / 2

  for (let iter = 0; iter < iterations; iter++) {
    // Repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[j].x! - nodes[i].x!
        const dy = nodes[j].y! - nodes[i].y!
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const force = (k * k) / dist

        nodes[i].x! -= (dx / dist) * force
        nodes[i].y! -= (dy / dist) * force
        nodes[j].x! += (dx / dist) * force
        nodes[j].y! += (dy / dist) * force
      }
    }

    // Attraction (links)
    for (const link of links) {
      const source = nodes.find(n => n.id === link.source)
      const target = nodes.find(n => n.id === link.target)

      if (source && target) {
        const dx = target.x! - source.x!
        const dy = target.y! - source.y!
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const force = (dist - k) / dist

        source.x! += (dx / dist) * force * 0.5
        source.y! += (dy / dist) * force * 0.5
        target.x! -= (dx / dist) * force * 0.5
        target.y! -= (dy / dist) * force * 0.5
      }
    }

    // Center gravity
    for (const node of nodes) {
      node.x! += (width.value / 2 - node.x!) * 0.01
      node.y! += (height.value / 2 - node.y!) * 0.01
    }

    // Boundary constraints
    for (const node of nodes) {
      node.x = Math.max(50, Math.min(width.value - 50, node.x))
      node.y = Math.max(50, Math.min(height.value - 50, node.y))
    }
  }
}

// Helper functions
function getNodeById(id: string): GraphNode | undefined {
  return localNodes.value.find(n => n.id === id)
}

function getNodeSize(node: GraphNode): number {
  return 20 + node.energy * 20
}

function getNodeColor(node: GraphNode): string {
  const colors: Record<MemoryType, string> = {
    [MemoryType.FACT]: '#409EFF',
    [MemoryType.PREFERENCE]: '#67C23A',
    [MemoryType.PROCEDURE]: '#E6A23C',
    [MemoryType.CONTEXT]: '#909399',
    [MemoryType.STRATEGY]: '#F56C6C',
    [MemoryType.EPISODE]: '#9C27B0'
  }
  return colors[node.type] || '#409EFF'
}

function getLinkColor(link: GraphLink): string {
  return `rgba(64, 158, 255, ${link.confidence})`
}

function getLinkWidth(link: GraphLink): number {
  return 1 + link.confidence * 2
}

function getLinkMidpoint(link: GraphLink): { x: number; y: number } {
  const source = getNodeById(link.source)
  const target = getNodeById(link.target)

  if (!source || !target) return { x: 0, y: 0 }

  return {
    x: (source.x! + target.x!) / 2,
    y: (source.y! + target.y!) / 2
  }
}

function getEnergyColor(energy: number): string {
  if (energy > 0.7) return '#67C23A'
  if (energy > 0.4) return '#E6A23C'
  return '#F56C6C'
}

function truncateText(text: string, maxLen: number): string {
  return text.length > maxLen ? text.substring(0, maxLen) + '...' : text
}

// Event handlers
function handleNodeClick(node: GraphNode) {
  emit('selectNode', node.id)
}

function handleMouseDown(e: MouseEvent) {
  isDragging.value = true
  dragStart.value = { x: e.clientX - panX.value, y: e.clientY - panY.value }
}

function handleMouseMove(e: MouseEvent) {
  if (isDragging.value) {
    panX.value = e.clientX - dragStart.value.x
    panY.value = e.clientY - dragStart.value.y
  }

  if (hoveredNodeId.value) {
    tooltipX.value = e.clientX + 10
    tooltipY.value = e.clientY + 10
  }
}

function handleMouseUp() {
  isDragging.value = false
}

function handleWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  scale.value = Math.max(0.1, Math.min(3, scale.value * delta))
}

// Control handlers
function zoomIn() {
  scale.value = Math.min(3, scale.value * 1.2)
}

function zoomOut() {
  scale.value = Math.max(0.1, scale.value * 0.8)
}

function resetView() {
  scale.value = 1
  panX.value = 0
  panY.value = 0
}
</script>

<style scoped>
.memory-graph {
  position: relative;
  width: 100%;
  height: 400px;
  background-color: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  overflow: hidden;
}

svg {
  display: block;
  cursor: grab;
}

svg:active {
  cursor: grabbing;
}

.graph-node {
  cursor: pointer;
  transition: opacity 0.2s;
}

.graph-node:hover circle.node-circle {
  opacity: 0.8;
}

.graph-node.selected circle.node-circle {
  filter: drop-shadow(0 0 8px var(--el-color-primary));
}

.link-label {
  pointer-events: none;
  font-family: monospace;
}

.energy-indicator {
  pointer-events: none;
}

.graph-tooltip {
  position: fixed;
  padding: 8px 12px;
  background-color: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  pointer-events: none;
  z-index: 1000;
}

.tooltip-title {
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--el-text-color-primary);
}

.tooltip-info {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.graph-controls {
  position: absolute;
  bottom: 12px;
  right: 12px;
  background-color: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  padding: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
</style>
