/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="element-plus-test">
    <h2>Element Plus 测试组件</h2>
    
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>按钮测试</span>
            </div>
          </template>
          <div class="button-group">
            <el-button type="primary">主要按钮</el-button>
            <el-button type="success">成功按钮</el-button>
            <el-button type="warning">警告按钮</el-button>
            <el-button type="danger">危险按钮</el-button>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="12">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>表单测试</span>
            </div>
          </template>
          <el-form :model="form" label-width="80px">
            <el-form-item label="输入框">
              <el-input v-model="form.input" placeholder="请输入内容" />
            </el-form-item>
            <el-form-item label="选择器">
              <el-select v-model="form.select" placeholder="请选择">
                <el-option label="选项1" value="1" />
                <el-option label="选项2" value="2" />
              </el-select>
            </el-form-item>
            <el-form-item label="开关">
              <el-switch v-model="form.switch" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
    
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="24">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>消息提示测试</span>
            </div>
          </template>
          <div class="button-group">
            <el-button @click="showSuccess">成功提示</el-button>
            <el-button @click="showWarning">警告提示</el-button>
            <el-button @click="showError">错误提示</el-button>
            <el-button @click="showInfo">信息提示</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="24">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>图标测试</span>
            </div>
          </template>
          <div class="icon-group">
            <el-icon :size="30" color="#409EFF"><Edit /></el-icon>
            <el-icon :size="30" color="#67C23A"><Check /></el-icon>
            <el-icon :size="30" color="#E6A23C"><Warning /></el-icon>
            <el-icon :size="30" color="#F56C6C"><Close /></el-icon>
            <el-icon :size="30" color="#909399"><Search /></el-icon>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { ElMessage } from 'element-plus'

const form = reactive({
  input: '',
  select: '',
  switch: false
})

const showSuccess = () => {
  ElMessage.success('这是一条成功消息')
}

const showWarning = () => {
  ElMessage.warning('这是一条警告消息')
}

const showError = () => {
  ElMessage.error('这是一条错误消息')
}

const showInfo = () => {
  ElMessage.info('这是一条信息消息')
}
</script>

<style scoped>
.element-plus-test {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.box-card {
  margin-bottom: 20px;
}

.button-group {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.icon-group {
  display: flex;
  gap: 20px;
  align-items: center;
}
</style>