// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::fs;
use serde_json::Value;
use tauri::Manager;
use tauri::Emitter;

// ==================== 崩溃处理模块 ====================
mod crash_handler;
use crash_handler::{setup_panic_hook, get_all_crash_reports, clear_all_crash_reports};

/// Get UV executable path (shared helper function)
fn get_uv_path() -> PathBuf {
    use std::process::Command;

    // Get uv path from environment variable or detect standalone uv
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

    // Determine if we're using standalone UV
    let is_standalone_uv = uv_path.to_string_lossy().contains("resources/python-env");

    // Get absolute path for uv
    // For standalone builds, use the path directly (already absolute from exe_dir)
    // For system UV, try to resolve the full path
    let uv_path_abs = if is_standalone_uv {
        // Standalone UV is already an absolute path (exe_dir + resources/...)
        // Try canonicalize, but if it fails, use the path as-is
        uv_path.canonicalize().unwrap_or_else(|_| uv_path.clone())
    } else {
        // System UV: try canonicalize first
        let canonical = uv_path.canonicalize();
        if canonical.is_ok() {
            canonical.unwrap()
        } else {
            // If canonicalize fails (e.g., "uv" is not absolute), find it in PATH
            #[cfg(unix)]
            {
                let which_output = Command::new("which")
                    .arg("uv")
                    .output();

                match which_output {
                    Ok(output) if output.status.success() => {
                        let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
                        PathBuf::from(path)
                    }
                    _ => uv_path.clone()
                }
            }

            #[cfg(windows)]
            {
                let where_output = Command::new("where")
                    .arg("uv")
                    .output();

                match where_output {
                    Ok(output) if output.status.success() => {
                        let path = String::from_utf8_lossy(&output.stdout).lines().next().unwrap_or("").trim().to_string();
                        if !path.is_empty() {
                            PathBuf::from(path)
                        } else {
                            uv_path.clone()
                        }
                    }
                    _ => uv_path.clone()
                }
            }
        }
    };

    uv_path_abs
}

/// Get Python information (version and path) using uv
#[tauri::command]
async fn get_python_info() -> Result<String, String> {
    use std::process::Command;
    use std::path::PathBuf;
    use std::fs::OpenOptions;
    use std::io::Write;

    // Get UV path using shared helper
    let uv_path_final = get_uv_path();

    // Check if standalone Python environment exists
    let exe_path = std::env::current_exe().unwrap();
    let exe_dir = exe_path.parent().unwrap();

    #[cfg(unix)]
    let standalone_python = exe_dir.join("resources/python-env/bin/python");
    #[cfg(windows)]
    let standalone_python = exe_dir.join("resources/python-env/Scripts/python.exe");

    let python_path = if standalone_python.exists() {
        // Use standalone Python environment
        standalone_python
    } else {
        // Fallback: use uv to find Python
        let python_output = Command::new(&uv_path_final)
            .args(["python", "find"])
            .output();

        match python_output {
            Ok(output) if output.status.success() => {
                let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
                PathBuf::from(path)
            }
            _ => {
                return Err("无法找到 Python 环境".to_string());
            }
        }
    };

    // Get absolute path for Python
    let python_path_abs = python_path.canonicalize().unwrap_or_else(|_| python_path.clone());

    // Get Python version directly from Python
    let version_output = Command::new(&python_path_abs)
        .arg("--version")
        .output();

    match version_output {
        Ok(output) => {
            let version_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let python_path_str = python_path_abs.display().to_string();
            let uv_path_str = uv_path_final.display().to_string();

            // Write paths to .env file in the davybot executable directory
            let exe_path = std::env::current_exe().unwrap();
            let exe_dir = exe_path.parent().unwrap();
            let env_file = exe_dir.join(".env");

            let env_content = format!(
                "DAWEI_PYTHON_PATH={}\nDAWEI_UV_PATH={}\n",
                python_path_str, uv_path_str
            );

            match OpenOptions::new()
                .write(true)
                .create(true)
                .truncate(true)
                .open(&env_file)
            {
                Ok(mut file) => {
                    if let Err(e) = file.write_all(env_content.as_bytes()) {
                        eprintln!("Warning: Failed to write .env file: {}", e);
                    } else {
                        eprintln!("✓ Environment paths written to: {:?}", env_file);
                    }
                }
                Err(e) => {
                    eprintln!("Warning: Failed to create .env file: {}", e);
                }
            }

            Ok(format!("{} @ {}\nUV: {}", version_str, python_path_str, uv_path_str))
        }
        Err(e) => {
            Err(format!("无法获取 Python 版本: {}", e))
        }
    }
}

/// Start backend command - unified for both dev and standalone
#[tauri::command]
async fn start_backend(app: tauri::AppHandle) -> Result<String, String> {
    use std::process::Command;

    let mut logs = Vec::new();
    logs.push("🚀 [start_backend] Starting backend server...".to_string());

    // Get UV path using shared helper (ensures consistency with get_python_info)
    let uv_path = get_uv_path();
    logs.push(format!("✓ [start_backend] UV path: {:?}", uv_path));

    // Get davybot executable directory
    let exe_path = std::env::current_exe().unwrap();
    let exe_dir = exe_path.parent().unwrap();
    logs.push(format!("✓ [start_backend] Executable location: {:?}", exe_path));

    // Detect if running in dev mode using debug_assertions
    let is_dev = cfg!(debug_assertions);

    let result = if is_dev {
        // Dev mode: use project's agent directory as working directory
        let agent_dir = PathBuf::from("/home/dev007/ws/davybot-proxy/agent");
        logs.push(format!("✓ [start_backend] Detected dev mode"));

        let full_command = format!("{} run --directory {} dawei server start",
            uv_path.display(), agent_dir.display());

        logs.push(format!("📁 [start_backend] Working directory: {:?}", agent_dir));
        logs.push(format!("⏳ [start_backend] Full command: {}", full_command));

        Command::new(&uv_path)
            .args(["run", "--directory", agent_dir.to_str().unwrap(), "dawei", "server", "start"])
            .current_dir(&agent_dir)
            .spawn()
    } else {
        // Standalone mode: use tauri app directory as working directory
        logs.push(format!("✓ [start_backend] Detected standalone mode"));

        let venv_path = exe_dir.join("resources/python-env");
        let full_command = format!("{} run dawei server start", uv_path.display());
        let env_vars = format!("VIRTUAL_ENV={}", venv_path.display());

        logs.push(format!("📁 [start_backend] Working directory: {:?}", exe_dir));
        logs.push(format!("🔧 [start_backend] Environment: {}", env_vars));
        logs.push(format!("⏳ [start_backend] Full command: {}", full_command));

        Command::new(&uv_path)
            .args(["run", "dawei", "server", "start"])
            .env("VIRTUAL_ENV", &venv_path)
            .current_dir(exe_dir)
            .spawn()
    };

    match result {
        Ok(child) => {
            logs.push(format!("✅ [start_backend] Backend process started successfully (PID: {:?})", child.id()));

            // Emit logs to frontend via app log event
            let log_message = logs.join("\n");
            if let Err(e) = app.emit("app-log", log_message.clone()) {
                eprintln!("Failed to emit app-log: {}", e);
            }

            Ok(log_message)
        },
        Err(e) => {
            let error_msg = format!("❌ [start_backend] Failed to start backend: {}", e);
            logs.push(error_msg.clone());

            // Emit error logs to frontend
            let log_message = logs.join("\n");
            if let Err(e) = app.emit("app-log", log_message.clone()) {
                eprintln!("Failed to emit app-log: {}", e);
            }

            Err(error_msg)
        }
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

    // DevTools 配置 - 所有模式下都可用
    // 通过环境变量 DAWEI_DEVTOOLS=1 控制是否自动打开
    let auto_open_devtools = std::env::var("DAWEI_DEVTOOLS")
        .unwrap_or_default()
        == "1";

    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init());

    // 设置窗口事件和 DevTools
    let builder = builder.setup(move |app| {
        // 自动打开 DevTools（如果环境变量设置）
        if auto_open_devtools {
            if let Some(window) = app.get_webview_window("main") {
                window.open_devtools();
            }
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
            get_python_info,
            // 后端管理命令
            start_backend,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
