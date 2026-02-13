/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 工具调用组件共享辅助函数
 *
 * 统一的工具调用数据处理、格式化和状态管理函数
 * 消除 ToolCall.vue, ToolCallContent.vue, ToolResultContent.vue, ToolExecutionContent.vue 之间的重复代码
 */

import { ElMessage } from 'element-plus'
import { copyToClipboard as copyToClipboardPlatform } from './clipboard'

// ==================== 类型定义 ====================

/**
 * 工具调用状态
 */
export type ToolCallStatus = 'started' | 'in_progress' | 'completed' | 'failed'

/**
 * 工具执行状态（扩展版）
 */
export type ToolExecutionStatus =
  | 'started'
  | 'validating'
  | 'executing'
  | 'completed'
  | 'failed'
  | 'timeout'

// ==================== 状态映射 ====================

/**
 * 状态到标签类型的映射
 */
export const STATUS_TYPE_MAP: Record<string, 'primary' | 'warning' | 'success' | 'danger' | 'info'> = {
  started: 'primary',
  validating: 'primary',
  in_progress: 'warning',
  executing: 'warning',
  completed: 'success',
  failed: 'danger',
  timeout: 'danger'
}

/**
 * 状态到显示文本的映射（中文）
 */
export const STATUS_TEXT_MAP: Record<string, string> = {
  started: '已启动',
  validating: '验证中',
  in_progress: '进行中',
  executing: '执行中',
  completed: '已完成',
  failed: '失败',
  timeout: '超时'
}

/**
 * 错误代码到标题的映射
 */
export const ERROR_TITLE_MAP: Record<string, string> = {
  TIMEOUT: '执行超时',
  PERMISSION_DENIED: '权限不足',
  INVALID_PARAMS: '参数错误',
  TOOL_NOT_FOUND: '工具不存在',
  NETWORK_ERROR: '网络错误',
  INTERNAL_ERROR: '内部错误'
}

/**
 * 错误代码到建议的映射
 */
export const ERROR_SUGGESTION_MAP: Record<string, string> = {
  TIMEOUT: '请检查网络连接或减少处理数据量后重试',
  PERMISSION_DENIED: '请检查文件权限或联系管理员',
  INVALID_PARAMS: '请检查输入参数格式和内容',
  TOOL_NOT_FOUND: '请确认工具名称是否正确',
  NETWORK_ERROR: '请检查网络连接后重试',
  INTERNAL_ERROR: '请稍后重试或联系技术支持'
}

// ==================== 状态获取函数 ====================

/**
 * 获取状态对应的标签类型
 */
export function getStatusTagType(status: string): 'primary' | 'warning' | 'success' | 'danger' | 'info' {
  return STATUS_TYPE_MAP[status] || 'info'
}

/**
 * 获取状态对应的显示文本
 */
export function getStatusText(status: string): string {
  return STATUS_TEXT_MAP[status] || status
}

/**
 * 获取进度条状态
 */
export function getProgressStatus(status: string): 'success' | 'exception' | undefined {
  if (status === 'completed') return 'success'
  if (status === 'failed' || status === 'timeout') return 'exception'
  return undefined
}

/**
 * 获取错误标题
 */
export function getErrorTitle(errorCode?: string): string {
  if (!errorCode) return '工具执行失败'
  return ERROR_TITLE_MAP[errorCode] || '工具执行失败'
}

/**
 * 获取错误建议
 */
export function getErrorSuggestion(errorCode?: string): string {
  if (!errorCode) return ''
  return ERROR_SUGGESTION_MAP[errorCode] || ''
}

// ==================== 格式化函数 ====================

/**
 * 格式化执行时间
 * @param time 执行时间（秒）
 * @returns 格式化后的时间字符串
 */
export function formatExecutionTime(time: number): string {
  if (time < 1) {
    return `${(time * 1000).toFixed(0)}ms`
  } else if (time < 60) {
    return `${time.toFixed(2)}s`
  } else {
    const minutes = Math.floor(time / 60)
    const seconds = (time % 60).toFixed(0)
    return `${minutes}m ${seconds}s`
  }
}

/**
 * 格式化工具输入参数
 * @param input 输入参数
 * @returns 格式化后的字符串
 */
export function formatToolInput(input: unknown): string {
  if (typeof input === 'string') {
    return input
  } else if (input === null || input === undefined) {
    return 'null'
  } else {
    return JSON.stringify(input, null, 2)
  }
}

/**
 * 格式化工具输出结果
 * @param output 输出结果
 * @returns 格式化后的字符串
 */
export function formatToolOutput(output: unknown): string {
  if (typeof output === 'string') {
    return output
  } else if (output === null || output === undefined) {
    return 'null'
  } else {
    return JSON.stringify(output, null, 2)
  }
}

/**
 * 格式化工具执行结果
 * @param result 执行结果
 * @returns 格式化后的字符串
 */
export function formatToolResult(result: unknown): string {
  if (typeof result === 'string') {
    return result
  } else if (result === null || result === undefined) {
    return 'null'
  } else {
    return JSON.stringify(result, null, 2)
  }
}

/**
 * 格式化错误结果
 * @param result 错误结果
 * @returns 格式化后的字符串
 */
export function formatErrorResult(result: unknown): string {
  if (typeof result === 'string') {
    return result
  } else if (result && typeof result === 'object') {
    return JSON.stringify(result, null, 2)
  }
  return String(result || '')
}

/**
 * 判断是否应该显示错误详情
 * @param result 错误结果
 * @returns 是否显示详情
 */
export function shouldShowErrorDetails(result: unknown): boolean {
  if (typeof result === 'string') {
    return result.length > 100 || result.includes('\n')
  }
  return result && typeof result === 'object' && Object.keys(result).length > 0
}

// ==================== 剪贴板操作 ====================

/**
 * 复制文本到剪贴板
 * @param text 要复制的文本
 * @param successMessage 成功提示消息
 */
export async function copyToClipboard(text: string, successMessage: string = '已复制到剪贴板'): Promise<void> {
  const success = await copyToClipboardPlatform(text)
  if (success) {
    ElMessage.success(successMessage)
  } else {
    ElMessage.error('复制失败')
  }
}

/**
 * 复制工具输入参数
 * @param toolInput 工具输入
 * @param toolName 工具名称（可选，用于提示消息）
 */
export async function copyToolInput(toolInput: unknown, toolName?: string): Promise<void> {
  const text = formatToolInput(toolInput)
  const message = toolName ? `${toolName} 输入参数已复制` : '输入参数已复制到剪贴板'
  await copyToClipboard(text, message)
}

/**
 * 复制工具输出结果
 * @param toolOutput 工具输出
 * @param toolName 工具名称（可选，用于提示消息）
 */
export async function copyToolOutput(toolOutput: unknown, toolName?: string): Promise<void> {
  const text = formatToolOutput(toolOutput)
  const message = toolName ? `${toolName} 输出结果已复制` : '输出结果已复制到剪贴板'
  await copyToClipboard(text, message)
}

/**
 * 复制工具执行结果
 * @param result 执行结果
 * @param toolName 工具名称（可选，用于提示消息）
 */
export async function copyToolResult(result: unknown, toolName?: string): Promise<void> {
  const text = formatToolResult(result)
  const message = toolName ? `${toolName} 执行结果已复制` : '执行结果已复制到剪贴板'
  await copyToClipboard(text, message)
}

/**
 * 复制错误信息
 * @param error 错误信息
 * @param toolName 工具名称（可选，用于提示消息）
 */
export async function copyError(error: string, toolName?: string): Promise<void> {
  const message = toolName ? `${toolName} 错误信息已复制` : '错误信息已复制到剪贴板'
  await copyToClipboard(error || '', message)
}

// ==================== 进度计算辅助函数 ====================

/**
 * 获取步骤样式类名
 * @param index 步骤索引
 * @param currentStepIndex 当前步骤索引
 * @returns 样式类名
 */
export function getStepClass(index: number, currentStepIndex?: number): string {
  if (currentStepIndex === undefined) return ''
  if (index < currentStepIndex) return 'completed'
  if (index === currentStepIndex) return 'active'
  return 'pending'
}

/**
 * 检查是否应该显示进度信息
 * @param progressPercentage 进度百分比
 * @param currentStep 当前步骤
 * @param executionTime 执行时间
 * @param estimatedRemainingTime 预计剩余时间
 * @returns 是否显示进度信息
 */
export function shouldShowProgress(
  progressPercentage?: number,
  currentStep?: string,
  executionTime?: number,
  estimatedRemainingTime?: number
): boolean {
  return (
    progressPercentage !== undefined ||
    currentStep !== undefined ||
    executionTime !== undefined ||
    estimatedRemainingTime !== undefined
  )
}

/**
 * 检查是否应该显示性能指标
 * @param executionTime 执行时间
 * @param performanceMetrics 性能指标对象
 * @returns 是否显示性能指标
 */
export function shouldShowPerformanceMetrics(
  executionTime?: number,
  performanceMetrics?: Record<string, unknown>
): boolean {
  return executionTime !== undefined || performanceMetrics !== undefined
}

// ==================== 导出集合 ====================

export const toolHelpers = {
  // 状态获取
  getStatusTagType,
  getStatusText,
  getProgressStatus,
  getErrorTitle,
  getErrorSuggestion,

  // 格式化
  formatExecutionTime,
  formatToolInput,
  formatToolOutput,
  formatToolResult,
  formatErrorResult,
  shouldShowErrorDetails,

  // 剪贴板
  copyToClipboard,
  copyToolInput,
  copyToolOutput,
  copyToolResult,
  copyError,

  // 进度
  getStepClass,
  shouldShowProgress,
  shouldShowPerformanceMetrics,

  // 映射表
  STATUS_TYPE_MAP,
  STATUS_TEXT_MAP,
  ERROR_TITLE_MAP,
  ERROR_SUGGESTION_MAP
}

export default toolHelpers
