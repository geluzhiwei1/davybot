/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*
* X2T 转换工具 - OnlyOffice 文档格式转换
* 提供文档与二进制格式之间的转换功能
*/

// X2T WASM 模块加载状态
let x2tModule: any = null
let x2tInitialized = false

// 文件类型常量
export const c_oAscFileType2 = {
  docx: 1,
  xlsx: 2,
  pptx: 3,
  odt: 4,
  ods: 5,
  odp: 6,
  doc: 7,
  xls: 8,
  ppt: 9,
  rtf: 10,
  txt: 11,
  pdf: 12,
}

/**
 * 加载 X2T WASM 脚本
 */
export async function initX2TScript(): Promise<void> {
  if (x2tInitialized) {
    return
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = '/onlyoffice/wasm/x2t/x2t.js'
    script.onload = () => {
      x2tInitialized = true
      resolve()
    }
    script.onerror = () => reject(new Error('无法加载 X2T 脚本'))
    document.head.appendChild(script)
  })
}

/**
 * 初始化 X2T 模块
 */
export async function initX2T(): Promise<void> {
  if (x2tModule) {
    return
  }

  // @ts-ignore
  if (typeof window.createX2TModule !== 'function') {
    throw new Error('X2T 模块未加载，请先调用 initX2TScript')
  }

  try {
    // @ts-ignore
    x2tModule = await window.createX2TModule()
  } catch (error) {
    console.error('[x2t] 初始化失败:', error)
    throw error
  }
}

/**
 * 转换文档为 OnlyOffice 二进制格式
 */
export async function convertDocument(file: File): Promise<{ bin: ArrayBuffer }> {
  if (!x2tModule) {
    throw new Error('X2T 模块未初始化')
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const arrayBuffer = reader.result as ArrayBuffer
        const uint8Array = new Uint8Array(arrayBuffer)

        // 调用 X2T 转换
        // 注意：这里需要根据实际的 X2T API 进行调整
        const result = x2tModule.convertDocument(uint8Array)

        resolve({ bin: result })
      } catch (error) {
        console.error('[x2t] 文档转换失败:', error)
        reject(error)
      }
    }
    reader.onerror = () => reject(new Error('文件读取失败'))
    reader.readAsArrayBuffer(file)
  })
}

/**
 * 将二进制格式转换回文档并下载
 */
export async function convertBinToDocumentAndDownload(
  binData: ArrayBuffer,
  filename: string,
  outputFormat: number
): Promise<void> {
  if (!x2tModule) {
    throw new Error('X2T 模块未初始化')
  }

  try {
    // 调用 X2T 反向转换
    const result = x2tModule.convertBinToDocument(new Uint8Array(binData), outputFormat)

    // 创建 Blob 并下载
    const blob = new Blob([result], { type: getMimeType(outputFormat) })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    console.error('[x2t] 反向转换失败:', error)
    throw error
  }
}

/**
 * 根据输出格式获取 MIME 类型
 */
function getMimeType(format: number): string {
  const mimeTypes: Record<number, string> = {
    1: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // docx
    2: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // xlsx
    3: 'application/vnd.openxmlformats-officedocument.presentationml.presentation', // pptx
    4: 'application/vnd.oasis.opendocument.text', // odt
    5: 'application/vnd.oasis.opendocument.spreadsheet', // ods
    6: 'application/vnd.oasis.opendocument.presentation', // odp
    7: 'application/msword', // doc
    8: 'application/vnd.ms-excel', // xls
    9: 'application/vnd.ms-powerpoint', // ppt
    10: 'application/rtf', // rtf
    11: 'text/plain', // txt
    12: 'application/pdf', // pdf
  }
  return mimeTypes[format] || 'application/octet-stream'
}
