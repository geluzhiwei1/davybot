/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <div class="about-tab">
    <div class="about-section">
      <el-result icon="success" :title="t('userSettings.about.title')" :sub-title="t('userSettings.about.subtitle')">
        <template #extra>
          <el-descriptions :column="1" border>
            <el-descriptions-item :label="t('userSettings.about.version')">v{{ appVersion
              }}</el-descriptions-item>
            <el-descriptions-item :label="t('userSettings.about.buildTime')">{{ buildTime
              }}</el-descriptions-item>
            <el-descriptions-item :label="t('userSettings.about.vueVersion')">{{ vueVersion
              }}</el-descriptions-item>
            <el-descriptions-item :label="t('userSettings.about.elementVersion')">{{ elementVersion
              }}</el-descriptions-item>
            <el-descriptions-item :label="t('userSettings.about.homepage')">
              <a href="https://github.com/geluzhiwei1/davybot" target="_blank" class="github-link">
                https://github.com/geluzhiwei1/davybot
                <el-icon>
                  <Link />
                </el-icon>
              </a>
            </el-descriptions-item>
          </el-descriptions>
        </template>
      </el-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { version as vueVersion } from 'vue';
import { Link } from '@element-plus/icons-vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

// @ts-ignore - Vite env variables
const buildTime = (import.meta.env?.VITE_BUILD_TIME as string) || new Date().toISOString();
// @ts-ignore - Vite env variables
const appVersion = (import.meta.env?.VITE_APP_VERSION as string) || '0.0.0';
const elementVersion = '2.13.1'; // Hardcode version or import from package
</script>

<style scoped lang="scss">
.about-tab {
  .hero-section {
    text-align: center;
    margin-bottom: var(--spacing-3xl);
    animation: fadeInUp 0.8s var(--ease-out);
  }

  .hero-badge {
    display: inline-flex;
    align-items: center;
    gap: var(--spacing-sm);
    padding: var(--spacing-sm) var(--spacing-lg);
    background: var(--color-surface-2);
    border: 1px solid var(--color-border-default);
    border-radius: var(--radius-full);
    margin-bottom: var(--spacing-lg);
    font-size: var(--text-sm);
    color: var(--color-text-secondary);
    box-shadow: var(--shadow-sm);
  }

  .badge-dot {
    width: 8px;
    height: 8px;
    background: var(--color-primary);
    border-radius: var(--radius-full);
    animation: pulse 2s var(--ease-default) infinite;
  }

  .hero-title {
    font-size: clamp(2.5rem, 5vw, 4rem);
    font-weight: 700;
    line-height: 1.1;
    margin-bottom: var(--spacing-lg);
    font-family: var(--font-display);
    letter-spacing: -0.02em;
  }

  .text-gradient {
    background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-accent) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .hero-description {
    font-size: var(--text-lg);
    color: var(--color-text-secondary);
    max-width: 600px;
    margin: 0 auto;
    line-height: 1.6;
  }

  .about-section {
    padding: 16px;
  }

  .github-link {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--el-color-primary);
    text-decoration: none;
    word-break: break-all;
  }

  .github-link:hover {
    text-decoration: underline;
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse {

  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.5;
  }
}
</style>
