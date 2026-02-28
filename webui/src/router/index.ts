/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { createRouter, createWebHashHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import WorkspacesView from '../views/WorkspacesView.vue'
import ElementPlusTest from '../components/ElementPlusTest.vue'

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
            path: '/element-plus-test',
            name: 'element-plus-test',
            component: ElementPlusTest
        },
        {
            path: '/',
            redirect: '/workspaces'
        }
    ]
})

export default router
