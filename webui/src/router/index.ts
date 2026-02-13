/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { createRouter, createWebHashHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import WorkspacesView from '../views/WorkspacesView.vue'
import WorkspaceSettingsView from '../views/WorkspaceSettingsView.vue'
import ElementPlusTest from '../components/ElementPlusTest.vue'
import CheckpointView from '../views/CheckpointView.vue'
import E2ETestPage from '../views/E2ETestPage.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/dawei/:workspaceId?',
      name: 'chat',
      component: ChatView
    },
    {
      path: '/workspaces',
      name: 'workspaces',
      component: WorkspacesView
    },
    {
      path: '/workspaces/:workspaceId/settings',
      name: 'workspace-settings',
      component: WorkspaceSettingsView,
      props: true
    },
    {
      path: '/element-plus-test',
      name: 'element-plus-test',
      component: ElementPlusTest
    },
    {
      path: '/checkpoints',
      name: 'checkpoints',
      component: CheckpointView,
      props: (route) => ({ taskGraphId: route.query.taskGraphId })
    },
    {
      path: '/e2e-test',
      name: 'e2e-test',
      component: E2ETestPage
    },
    {
      path: '/',
      redirect: '/workspaces'
    }
  ]
})

export default router
