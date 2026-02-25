// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::fs;
use serde_json::Value;

// ==================== 崩溃处理模块 ====================
mod crash_handler;
use crash_handler::{setup_panic_hook, get_all_crash_reports, clear_all_crash_reports};

// Only include backend management for standalone version
#[cfg(feature = "standalone")]
mod backend_management {
    use std::path::PathBuf;
    use std::process::Command;

    #[cfg(target_os = "windows")]
    pub fn get_backend_script() -> PathBuf {
        let mut exe_path = std::env::current_exe().unwrap();
        exe_path.pop();
        exe_path.push("start-backend.bat");
        exe_path
    }

    #[cfg(not(target_os = "windows"))]
    pub fn get_backend_script() -> PathBuf {
        let mut exe_path = std::env::current_exe().unwrap();
        exe_path.pop();
        exe_path.push("start-backend.sh");
        exe_path
    }

    #[cfg(target_os = "windows")]
    pub fn get_stop_script() -> PathBuf {
        let mut exe_path = std::env::current_exe().unwrap();
        exe_path.pop();
        exe_path.push("stop-backend.bat");
        exe_path
    }

    #[cfg(not(target_os = "windows"))]
    pub fn get_stop_script() -> PathBuf {
        let mut exe_path = std::env::current_exe().unwrap();
        exe_path.pop();
        exe_path.push("stop-backend.sh");
        exe_path
    }

    pub async fn start_backend() -> Result<String, String> {
        let script_path = get_backend_script();

        if !script_path.exists() {
            return Err(format!("Backend script not found: {:?}", script_path));
        }

        #[cfg(target_os = "windows")]
        let output = Command::new("cmd")
            .args(["/C", script_path.to_str().unwrap()])
            .output();

        #[cfg(not(target_os = "windows"))]
        let output = Command::new("sh")
            .arg(script_path.to_str().unwrap())
            .output();

        match output {
            Ok(_) => Ok("Backend started successfully".to_string()),
            Err(e) => Err(format!("Failed to start backend: {}", e)),
        }
    }

    pub async fn stop_backend() -> Result<String, String> {
        let script_path = get_stop_script();

        if !script_path.exists() {
            return Err(format!("Stop script not found: {:?}", script_path));
        }

        #[cfg(target_os = "windows")]
        let output = Command::new("cmd")
            .args(["/C", script_path.to_str().unwrap()])
            .output();

        #[cfg(not(target_os = "windows"))]
        let output = Command::new("sh")
            .arg(script_path.to_str().unwrap())
            .output();

        match output {
            Ok(_) => Ok("Backend stopped successfully".to_string()),
            Err(e) => Err(format!("Failed to stop backend: {}", e)),
        }
    }

    pub async fn restart_backend() -> Result<String, String> {
        // First stop
        match stop_backend().await {
            Ok(_) => {
                // Wait a bit for the backend to stop
                tokio::time::sleep(std::time::Duration::from_secs(2)).await;
                // Then start
                start_backend().await
            }
            Err(e) => Err(format!("Failed to stop backend during restart: {}", e)),
        }
    }
}

// Backend management for non-standalone versions (via API calls)
mod backend_management_api {
    use std::time::Duration;

    /// Try to restart backend via API call
    pub async fn restart_backend_via_api() -> Result<String, String> {
        // Try to call the backend's restart endpoint if it exists
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(10))
            .build()
            .map_err(|e| format!("Failed to create HTTP client: {}", e))?;

        // First try to get health to see if backend is running
        let health_url = "http://127.0.0.1:8465/health";
        let health_response = client.get(health_url).send().await;

        if health_response.is_err() {
            return Err("Backend is not running. Please start it manually using 'dawei server start'".to_string());
        }

        // Try to call restart endpoint (this may not exist in all versions)
        let restart_url = "http://127.0.0.1:8465/api/server/restart";
        let response = client.post(restart_url).send().await;

        match response {
            Ok(resp) => {
                if resp.status().is_success() {
                    Ok("Backend restart signal sent".to_string())
                } else {
                    Err(format!("Backend returned status: {}", resp.status()))
                }
            }
            Err(_) => {
                Err("Restart endpoint not available. Please restart manually using 'dawei server restart'".to_string())
            }
        }
    }
}

// Tauri commands - only available in standalone version
#[cfg(feature = "standalone")]
#[tauri::command]
async fn start_backend() -> Result<String, String> {
    backend_management::start_backend().await
}

#[cfg(feature = "standalone")]
#[tauri::command]
async fn stop_backend() -> Result<String, String> {
    backend_management::stop_backend().await
}

#[cfg(feature = "standalone")]
#[tauri::command]
async fn restart_backend() -> Result<String, String> {
    backend_management::restart_backend().await
}

/// Restart backend command for non-standalone versions (via API)
#[tauri::command]
async fn restart_backend_api() -> Result<String, String> {
    backend_management_api::restart_backend_via_api().await
}

// ==================== 崩溃报告 Tauri Commands ====================

/// 导航到主应用
#[tauri::command]
async fn navigate_to_main() -> Result<(), String> {
    // 前端会直接处理导航，这个命令保留用于未来扩展
    Ok(())
}

/// 选择目录
#[tauri::command]
async fn select_directory() -> Result<Option<String>, String> {
    use rfd::AsyncFileDialog;

    let file_dialog = AsyncFileDialog::new();
    let folder = file_dialog.pick_folder().await;

    Ok(folder.map(|p| p.path().to_string_lossy().to_string()))
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
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init());

    #[cfg(feature = "standalone")]
    let builder = builder.setup(|app| {
        // Auto-start backend on app launch (standalone only)
        let _app_handle = app.handle().clone();
        tauri::async_runtime::spawn(async move {
            // Wait a bit for the app to initialize
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;

            match start_backend().await {
                Ok(msg) => println!("{}", msg),
                Err(e) => eprintln!("Failed to start backend: {}", e),
            }
        });
        Ok(())
    });

    #[cfg(feature = "standalone")]
    let builder = builder.on_window_event(|window, event| {
        // Stop backend when window is closing (standalone only)
        if let tauri::WindowEvent::CloseRequested { .. } = event {
            let _app_handle = window.app_handle();
            tauri::async_runtime::block_on(async move {
                match stop_backend().await {
                    Ok(msg) => println!("{}", msg),
                    Err(e) => eprintln!("Failed to stop backend: {}", e),
                }
            });
        }
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
            #[cfg(feature = "standalone")]
            start_backend,
            #[cfg(feature = "standalone")]
            stop_backend,
            #[cfg(feature = "standalone")]
            restart_backend,
            // 非standalone版本的重启命令
            restart_backend_api,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
