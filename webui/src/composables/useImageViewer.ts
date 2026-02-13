/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { ref } from 'vue'

interface ImageInfo {
  src: string
  filename?: string
}

const viewerVisible = ref(false)
const viewerImages = ref<ImageInfo[]>([])
const initialIndex = ref(0)

export function useImageViewer() {
  const openViewer = (images: ImageInfo[], startIndex = 0) => {
    viewerImages.value = images
    initialIndex.value = startIndex
    viewerVisible.value = true
  }

  const closeViewer = () => {
    viewerVisible.value = false
  }

  return {
    viewerVisible,
    viewerImages,
    initialIndex,
    openViewer,
    closeViewer
  }
}
