// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::fs;
use serde_json::Value;
use tauri::Manager;

// ==================== 崩溃处理模块 ====================
mod crash_handler;
use crash_handler::{setup_panic_hook, get_all_crash_reports, clear_all_crash_reports};

/// Start backend command - unified for both dev and standalone
#[tauri::command]
async fn start_backend() -> Result<String, String> {
    use std::process::Command;
    use std::path::PathBuf;

    // Get uv path from environment variable or use default
    let uv_path = if let Ok(path) = std::env::var("DAWEI_UV_PATH") {
        PathBuf::from(path)
    } else {
        // Default: check if running from standalone build
        let exe_path = std::env::current_exe().unwrap();
        let exe_dir = exe_path.parent().unwrap();

        // Check if resources/python-env/uv exists
        let standalone_uv = exe_dir.join("resources/python-env/bin/uv");
        let standalone_uv_bat = exe_dir.join("resources/python-env/Scripts/uv.exe");

        if standalone_uv.exists() {
            standalone_uv
        } else if standalone_uv_bat.exists() {
            standalone_uv_bat
        } else {
            // Fallback to system uv
            PathBuf::from("uv")
        }
    };

    // Unified: use uv dawei server start
    #[cfg(unix)]
    let result = Command::new(&uv_path)
        .args(["run", "--directory", "../agent", "dawei", "server", "start"])
        .spawn();

    #[cfg(windows)]
    let result = Command::new(&uv_path)
        .args(["run", "--directory", "..\\agent", "dawei", "server", "start"])
        .spawn();

    match result {
        Ok(_) => Ok("Backend started successfully".to_string()),
        Err(e) => Err(format!("Failed to start backend: {}", e))
    }
}

// ==================== 崩溃报告 Tauri Commands ====================

/// 导航到主应用
#[tauri::command]
async fn navigate_to_main() -> Result<(), String> {
    // 前端会直接处理导航，这个命令保留用于未来扩展
    Ok(())
}

/// 选择目录（跨平台支持）
#[tauri::command]
async fn select_directory() -> Result<Option<String>, String> {
    use rfd::AsyncFileDialog;

    // 获取用户主目录作为默认位置
    let home_dir = dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."));

    // 创建文件对话框，设置初始目录为用户主目录
    let mut file_dialog = AsyncFileDialog::new()
        .set_directory(&home_dir);

    // 平台特定优化
    #[cfg(target_os = "macos")]
    {
        // macOS显示优化
        file_dialog = file_dialog.set_title("选择工作区目录");
    }

    #[cfg(target_os = "windows")]
    {
        // Windows显示优化
        file_dialog = file_dialog.set_title("选择工作区目录");
    }

    #[cfg(target_os = "linux")]
    {
        // Linux显示优化
        file_dialog = file_dialog.set_title("选择工作区目录");
    }

    let folder = file_dialog.pick_folder().await;

    match folder {
        Some(path) => {
            let path_str = path.path().to_string_lossy().to_string();
            Ok(Some(path_str))
        }
        None => Ok(None)
    }
}

/// 获取所有崩溃报告
#[tauri::command]
async fn get_crash_reports() -> Result<Vec<crash_handler::CrashReport>, String> {
    Ok(get_all_crash_reports())
}

/// 获取 DAWEI_HOME 目录
fn get_dawei_home() -> PathBuf {
    // 优先从环境变量读取
    if let Ok(home) = std::env::var("DAWEI_HOME") {
        return PathBuf::from(home);
    }

    // 默认使用用户主目录下的 .dawei
    #[cfg(target_os = "windows")]
    let base_dir = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));

    #[cfg(not(target_os = "windows"))]
    let base_dir = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));

    base_dir.join(".dawei")
}

/// 获取 DAWEI_HOME 目录 (Tauri command)
#[tauri::command]
async fn get_dawei_home_command() -> Result<String, String> {
    get_dawei_home()
        .to_str()
        .map(|s| s.to_string())
        .ok_or_else(|| "Failed to convert DAWEI_HOME to string".to_string())
}

/// 读取服务器启动信息
#[tauri::command]
async fn get_server_start_info() -> Result<Option<Value>, String> {
    let dawei_home = get_dawei_home();
    let server_start_file = dawei_home.join("server.start");

    if !server_start_file.exists() {
        return Ok(None);
    }

    fs::read_to_string(&server_start_file)
        .map_err(|e| format!("Failed to read server.start: {}", e))
        .and_then(|content| {
            serde_json::from_str(&content)
                .map_err(|e| format!("Failed to parse server.start: {}", e))
        })
        .map(Some)
}

/// 清除所有崩溃报告
#[tauri::command]
async fn clear_crash_reports() -> Result<(), String> {
    clear_all_crash_reports().map_err(|e| e.to_string())
}

fn main() {
    // ==================== 设置 Panic Hook ====================
    setup_panic_hook();

    // 只在debug模式启用DevTools
    #[cfg(debug_assertions)]
    {
        std::env::set_var("TAURI_DEVTOOLS", "1");
    }

    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init());

    // 只在debug模式自动打开DevTools (所有构建类型)
    #[cfg(debug_assertions)]
    let builder = builder.setup(|app| {
        if let Some(window) = app.get_webview_window("main") {
            window.open_devtools();
        }
        Ok(())
    });

    builder
        .invoke_handler(tauri::generate_handler![
            // 导航命令
            navigate_to_main,
            // 文件操作命令
            select_directory,
            // 崩溃报告命令
            get_crash_reports,
            clear_crash_reports,
            // 服务器信息命令
            get_dawei_home_command,
            get_server_start_info,
            // 后端管理命令
            start_backend,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
