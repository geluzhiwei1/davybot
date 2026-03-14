/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*
* OnlyOffice 工具函数
*/

/**
 * 根据文件扩展名获取文档类型
 */
export function getDocumentType(extension: string): string | null {
  const docTypes: Record<string, string> = {
    'docx': 'word',
    'doc': 'word',
    'odt': 'word',
    'rtf': 'word',
    'txt': 'word',
    'xlsx': 'cell',
    'xls': 'cell',
    'ods': 'cell',
    'csv': 'cell',
    'pptx': 'slide',
    'ppt': 'slide',
    'odp': 'slide',
  }

  return docTypes[extension.toLowerCase()] || null
}

/**
 * 获取文件扩展名
 */
export function getFileExtension(filename: string): string {
  const parts = filename.split('.')
  return parts.length > 1 ? parts.pop()!.toLowerCase() : ''
}

/**
 * 判断是否为 Office 文件
 */
export function isOfficeFile(filename: string): boolean {
  const ext = getFileExtension(filename)
  const officeExtensions = [
    'docx', 'doc', 'odt', 'rtf', 'txt',
    'xlsx', 'xls', 'ods', 'csv',
    'pptx', 'ppt', 'odp'
  ]
  return officeExtensions.includes(ext)
}
