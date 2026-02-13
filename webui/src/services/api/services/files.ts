/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { httpClient } from '../http';
import type {
  FileContent,
  FileSaveRequest,
  FileSaveResponse,
  SearchResult,
  SearchParams
} from '../types';

// 文件API服务类
export class FilesApiService {
  private baseUrl = '/files';

  // 获取文件内容
  async getFileContent(workspaceId: string, filePath: string, options?: {
    encoding?: string;
    lineNumbers?: boolean;
    highlight?: boolean;
  }): Promise<FileContent> {
    const params = {
      path: filePath,
      ...options
    };
    return await httpClient.get<FileContent>(`/workspaces/${workspaceId}/files`, params);
  }

  // 保存文件内容
  async saveFileContent(workspaceId: string, data: FileSaveRequest): Promise<FileSaveResponse> {
    return await httpClient.post<FileSaveResponse>(`/workspaces/${workspaceId}/files`, data);
  }

  // 创建文件
  async createFile(workspaceId: string, data: {
    path: string;
    content?: string;
    encoding?: string;
    overwrite?: boolean;
  }): Promise<{
    path: string;
    size: number;
    createdAt: string;
  }> {
    return await httpClient.post(`/workspaces/${workspaceId}/files/create`, data);
  }

  // 删除文件
  async deleteFile(workspaceId: string, filePath: string, options?: {
    permanent?: boolean;
  }): Promise<void> {
    const params = {
      path: filePath,
      ...options
    };
    return await httpClient.delete<void>(`/workspaces/${workspaceId}/files`, { params });
  }

  // 复制文件
  async copyFile(workspaceId: string, data: {
    sourcePath: string;
    targetPath: string;
    overwrite?: boolean;
  }): Promise<{
    sourcePath: string;
    targetPath: string;
    size: number;
    copiedAt: string;
  }> {
    return await httpClient.post(`/workspaces/${workspaceId}/files/copy`, data);
  }

  // 移动文件
  async moveFile(workspaceId: string, data: {
    sourcePath: string;
    targetPath: string;
    overwrite?: boolean;
  }): Promise<{
    sourcePath: string;
    targetPath: string;
    size: number;
    movedAt: string;
  }> {
    return await httpClient.post(`/workspaces/${workspaceId}/files/move`, data);
  }

  // 重命名文件
  async renameFile(workspaceId: string, data: {
    oldPath: string;
    newPath: string;
  }): Promise<{
    oldPath: string;
    newPath: string;
    renamedAt: string;
  }> {
    return await httpClient.post(`/workspaces/${workspaceId}/files/rename`, data);
  }

  // 创建目录
  async createDirectory(workspaceId: string, data: {
    path: string;
    recursive?: boolean;
  }): Promise<{
    path: string;
    createdAt: string;
  }> {
    return await httpClient.post(`/workspaces/${workspaceId}/directories`, data);
  }

  // 删除目录
  async deleteDirectory(workspaceId: string, dirPath: string, options?: {
    recursive?: boolean;
    force?: boolean;
  }): Promise<void> {
    const params = {
      path: dirPath,
      ...options
    };
    return await httpClient.delete<void>(`/workspaces/${workspaceId}/directories`, { params });
  }

  // 获取文件信息
  async getFileInfo(workspaceId: string, filePath: string): Promise<{
    path: string;
    name: string;
    type: 'file' | 'directory';
    size: number;
    createdAt: string;
    updatedAt: string;
    accessedAt: string;
    permissions: {
      readable: boolean;
      writable: boolean;
      executable: boolean;
    };
    mimeType?: string;
    encoding?: string;
    language?: string;
  }> {
    const params = { path: filePath };
    return await httpClient.get(`/workspaces/${workspaceId}/files/info`, params);
  }

  // 获取文件历史版本
  async getFileHistory(workspaceId: string, filePath: string, params?: {
    page?: number;
    limit?: number;
    since?: string;
    until?: string;
  }): Promise<{
    versions: Array<{
      version: string;
      timestamp: string;
      author: string;
      message?: string;
      size: number;
      changes: {
        added: number;
        removed: number;
        modified: number;
      };
    }>;
    pagination: {
      page: number;
      limit: number;
      total: number;
      totalPages: number;
    };
  }> {
    const requestParams = {
      path: filePath,
      ...params
    };
    return await httpClient.get(`/workspaces/${workspaceId}/files/history`, requestParams);
  }

  // 恢复文件到指定版本
  async restoreFileVersion(workspaceId: string, data: {
    path: string;
    version: string;
    createBackup?: boolean;
  }): Promise<{
    path: string;
    version: string;
    restoredAt: string;
    backupPath?: string;
  }> {
    return await httpClient.post(`/workspaces/${workspaceId}/files/restore`, data);
  }

  // 搜索文件内容
  async searchFiles(workspaceId: string, searchParams: SearchParams): Promise<{
    results: SearchResult[];
    total: number;
    searchTime: number;
    hasMore: boolean;
  }> {
    return await httpClient.get(`/workspaces/${workspaceId}/files/search`, searchParams);
  }

  // 上传文件
  async uploadFile(workspaceId: string, data: {
    file: File;
    path?: string;
    overwrite?: boolean;
    createBackup?: boolean;
  }): Promise<{
    path: string;
    name: string;
    size: number;
    uploadedAt: string;
    mimeType: string;
  }> {
    const formData = new FormData();
    formData.append('file', data.file);
    if (data.path) {
      formData.append('path', data.path);
    }
    if (data.overwrite !== undefined) {
      formData.append('overwrite', data.overwrite.toString());
    }
    if (data.createBackup !== undefined) {
      formData.append('createBackup', data.createBackup.toString());
    }

    return await httpClient.upload(`/workspaces/${workspaceId}/files/upload`, formData);
  }

  // 下载文件
  async downloadFile(workspaceId: string, filePath: string): Promise<Blob> {
    const params = { path: filePath };
    return await httpClient.download(`/workspaces/${workspaceId}/files/download`, { params });
  }

  // 获取文件预览
  async getFilePreview(workspaceId: string, filePath: string, options?: {
    lines?: number;
    startLine?: number;
    endLine?: number;
    highlight?: boolean;
  }): Promise<{
    content: string;
    lines: number;
    startLine: number;
    endLine: number;
    totalLines: number;
    language?: string;
  }> {
    const params = {
      path: filePath,
      ...options
    };
    return await httpClient.get(`/workspaces/${workspaceId}/files/preview`, params);
  }

  // 获取文件差异
  async getFileDiff(workspaceId: string, data: {
    path: string;
    version1?: string;
    version2?: string;
    content?: string;
  }): Promise<{
    path: string;
    diff: string;
    summary: {
      added: number;
      removed: number;
      modified: number;
    };
    version1?: string;
    version2?: string;
  }> {
    return await httpClient.post(`/workspaces/${workspaceId}/files/diff`, data);
  }

  // 批量操作文件
  async batchOperation(workspaceId: string, data: {
    operation: 'delete' | 'copy' | 'move';
    files: string[];
    targetPath?: string;
    options?: {
      overwrite?: boolean;
      createBackup?: boolean;
      recursive?: boolean;
    };
  }): Promise<{
    results: Array<{
      path: string;
      success: boolean;
      error?: string;
    }>;
    summary: {
      total: number;
      successful: number;
      failed: number;
    };
  }> {
    return await httpClient.post(`/workspaces/${workspaceId}/files/batch`, data);
  }

  // 获取文件统计信息
  async getFileStats(workspaceId: string, params?: {
    path?: string;
    recursive?: boolean;
    includeHidden?: boolean;
  }): Promise<{
    totalFiles: number;
    totalDirectories: number;
    totalSize: number;
    fileTypes: Record<string, number>;
    largestFiles: Array<{
      path: string;
      size: number;
    }>;
    recentlyModified: Array<{
      path: string;
      modifiedAt: string;
    }>;
  }> {
    return await httpClient.get(`/workspaces/${workspaceId}/files/stats`, params);
  }

  // 获取工作区文件列表（用于@命令提示）
  async getWorkspaceFiles(workspaceId: string, params?: {
    path?: string;
    recursive?: boolean;
    includeHidden?: boolean;
    maxDepth?: number;
    fileExtensions?: string[];
  }): Promise<{
    files: Array<{
      path: string;
      name: string;
      type: 'file' | 'directory';
      size?: number;
      language?: string;
    }>;
  }> {
    const requestParams = {
      path: params?.path || '.',
      recursive: params?.recursive || false,
      include_hidden: params?.includeHidden || false,
      max_depth: params?.maxDepth || 2,
      file_extensions: params?.fileExtensions
    };
    return await httpClient.get(`/api/files/list`, requestParams);
  }

}

// 创建文件API服务实例
export const filesApi = new FilesApiService();

// 导出便捷函数
export const {
  getFileContent,
  saveFileContent,
  createFile,
  deleteFile,
  copyFile,
  moveFile,
  renameFile,
  createDirectory,
  deleteDirectory,
  getFileInfo,
  getFileHistory,
  restoreFileVersion,
  searchFiles,
  uploadFile,
  downloadFile,
  getFilePreview,
  getFileDiff,
  batchOperation,
  getFileStats,
  getWorkspaceFiles
} = {
  getFileContent: filesApi.getFileContent.bind(filesApi),
  saveFileContent: filesApi.saveFileContent.bind(filesApi),
  createFile: filesApi.createFile.bind(filesApi),
  deleteFile: filesApi.deleteFile.bind(filesApi),
  copyFile: filesApi.copyFile.bind(filesApi),
  moveFile: filesApi.moveFile.bind(filesApi),
  renameFile: filesApi.renameFile.bind(filesApi),
  createDirectory: filesApi.createDirectory.bind(filesApi),
  deleteDirectory: filesApi.deleteDirectory.bind(filesApi),
  getFileInfo: filesApi.getFileInfo.bind(filesApi),
  getFileHistory: filesApi.getFileHistory.bind(filesApi),
  restoreFileVersion: filesApi.restoreFileVersion.bind(filesApi),
  searchFiles: filesApi.searchFiles.bind(filesApi),
  uploadFile: filesApi.uploadFile.bind(filesApi),
  downloadFile: filesApi.downloadFile.bind(filesApi),
  getFilePreview: filesApi.getFilePreview.bind(filesApi),
  getFileDiff: filesApi.getFileDiff.bind(filesApi),
  batchOperation: filesApi.batchOperation.bind(filesApi),
  getFileStats: filesApi.getFileStats.bind(filesApi),
  getWorkspaceFiles: filesApi.getWorkspaceFiles.bind(filesApi)
};