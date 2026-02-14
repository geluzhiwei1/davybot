//! 崩溃处理模块
//!
//! 提供 panic hook 和崩溃报告功能

use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

/// 崩溃报告结构
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrashReport {
    /// 崩溃时间戳
    pub timestamp: u64,
    /// ISO 8601 格式的时间
    pub timestamp_iso: String,
    /// 错误消息
    pub error_message: String,
    /// 堆栈跟踪
    pub backtrace: String,
    /// 平台
    pub platform: String,
    /// 应用版本
    pub app_version: String,
    /// 文件名
    pub filename: String,
}

impl CrashReport {
    /// 创建新的崩溃报告
    pub fn new(error: String, backtrace: String) -> Self {
        let now = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        let chrono_now = chrono::Local::now();
        let timestamp_iso = chrono_now.to_rfc3339();

        // 生成文件名
        let filename = format!("crash_{}.json", chrono_now.format("%Y%m%d_%H%M%S"));

        Self {
            timestamp: now,
            timestamp_iso,
            error_message: error,
            backtrace,
            platform: std::env::consts::OS.to_string(),
            app_version: env!("CARGO_PKG_VERSION").to_string(),
            filename,
        }
    }

    /// 转换为 JSON 字符串
    pub fn to_json(&self) -> String {
        serde_json::to_string_pretty(self).unwrap_or_else(|_| "{}".to_string())
    }

    /// 保存崩溃报告到文件
    pub fn save(&self) -> std::io::Result<PathBuf> {
        // 获取可执行文件所在目录
        let exe_path = std::env::current_exe()?;
        let mut crash_dir = exe_path.parent().unwrap_or(Path::new(".")).to_path_buf();
        crash_dir.push("crashes");

        // 创建崩溃报告目录
        fs::create_dir_all(&crash_dir)?;

        // 保存崩溃报告
        let crash_file_path = crash_dir.join(&self.filename);
        let mut file = File::create(&crash_file_path)?;
        file.write_all(self.to_json().as_bytes())?;
        file.write_all(b"\n")?;

        eprintln!("✅ Crash report saved to: {:?}", crash_file_path);
        Ok(crash_file_path)
    }

    /// 格式化错误信息用于显示
    pub fn format_display(&self) -> String {
        format!(
            "Error: {}\nPlatform: {}\nVersion: {}\nTime: {}\n\nBacktrace:\n{}",
            self.error_message,
            self.platform,
            self.app_version,
            self.timestamp_iso,
            self.backtrace
        )
    }
}

/// 获取崩溃报告目录
pub fn get_crashes_dir() -> Option<PathBuf> {
    let exe_path = std::env::current_exe().ok()?;
    let mut crash_dir = exe_path.parent()?.to_path_buf();
    crash_dir.push("crashes");
    Some(crash_dir)
}

/// 获取所有崩溃报告
pub fn get_all_crash_reports() -> Vec<CrashReport> {
    let mut reports = Vec::new();

    if let Some(crash_dir) = get_crashes_dir() {
        if let Ok(entries) = fs::read_dir(&crash_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().and_then(|s| s.to_str()) == Some("json") {
                    if let Ok(content) = fs::read_to_string(&path) {
                        if let Ok(report) = serde_json::from_str::<CrashReport>(&content) {
                            reports.push(report);
                        }
                    }
                }
            }
        }
    }

    // 按时间倒序排序（最新的在前）
    reports.sort_by(|a, b| b.timestamp.cmp(&a.timestamp));
    reports
}

/// 清除所有崩溃报告
pub fn clear_all_crash_reports() -> std::io::Result<()> {
    if let Some(crash_dir) = get_crashes_dir() {
        if crash_dir.exists() {
            fs::remove_dir_all(&crash_dir)?;
            println!("✅ All crash reports cleared");
        }
    }
    Ok(())
}

/// 设置 panic hook
pub fn setup_panic_hook() {
    std::panic::set_hook(Box::new(|panic_info| {
        // 获取错误信息
        let error_msg = if let Some(s) = panic_info.payload().downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = panic_info.payload().downcast_ref::<String>() {
            s.clone()
        } else {
            "Unknown panic".to_string()
        };

        // 获取位置信息
        let location = panic_info.location().map(|l| {
            format!("{}:{}:{}", l.file(), l.line(), l.column())
        });

        // 构建完整的错误消息
        let full_error = if let Some(loc) = location {
            format!("Panic at {}: {}", loc, error_msg)
        } else {
            error_msg
        };

        // 获取堆栈跟踪
        let backtrace = std::backtrace::Backtrace::capture().to_string();

        // 创建并保存崩溃报告
        let report = CrashReport::new(full_error, backtrace);

        // 尝试保存崩溃报告
        if let Err(e) = report.save() {
            eprintln!("❌ Failed to save crash report: {}", e);
        }

        // 打印到 stderr
        eprintln!("\n{}", "=".repeat(60));
        eprintln!("🚨 APPLICATION PANIC");
        eprintln!("{}", "=".repeat(60));
        eprintln!("{}", report.format_display());
        eprintln!("{}\n", "=".repeat(60));
    }));

    println!("✅ Panic hook installed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_crash_report_creation() {
        let report = CrashReport::new(
            "Test error".to_string(),
            "Test backtrace".to_string(),
        );

        assert_eq!(report.error_message, "Test error");
        assert_eq!(report.backtrace, "Test backtrace");
    }

    #[test]
    fn test_json_serialization() {
        let report = CrashReport::new(
            "Test error".to_string(),
            "Test backtrace".to_string(),
        );

        let json = report.to_json();
        assert!(json.contains("Test error"));
        assert!(json.contains("Test backtrace"));
    }
}
