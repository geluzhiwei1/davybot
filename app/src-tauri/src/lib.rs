use serde::{Deserialize, Serialize};
use std::fs;
use std::sync::atomic::{AtomicU16, Ordering};
#[cfg(desktop)]
use std::net::TcpListener;
#[cfg(desktop)]
use std::sync::atomic::AtomicU32;
#[cfg(desktop)]
use std::sync::Arc;
#[cfg(desktop)]
use tauri::{Emitter, Listener, Manager};
#[cfg(desktop)]
use tauri_plugin_shell::process::CommandEvent;
#[cfg(desktop)]
use tauri_plugin_shell::ShellExt;

/// Max sidecar restart attempts before giving up.
#[cfg(desktop)]
const MAX_RESTART_COUNT: u32 = 3;

/// Dynamically-picked localhost port the sidecar is (being) started on.
/// 0 = not yet assigned. Read by the `get_sidecar_port` command so the
/// webview can resolve its API/WS base URL at runtime.
static SIDECAR_PORT: AtomicU16 = AtomicU16::new(0);

/// Bumped on every spawn attempt; lets stale health-watchers detect that a
/// newer spawn superseded them and skip emitting an outdated ready/failed.
#[cfg(desktop)]
static SIDECAR_GEN: AtomicU32 = AtomicU32::new(0);

/// Lifecycle event payload emitted to the webview on the `sidecar-status` channel.
/// `progress` (health-check attempt N of M with elapsed ms) and `failed` (carrying
/// a log tail) are what make the startup overlay informative instead of a blind
/// spinner — see [[desktop-stuck-starting-csp-ipc]].
#[cfg(desktop)]
#[derive(Serialize, Clone)]
struct SidecarStatus {
    status: String,                   // "starting" | "progress" | "ready" | "failed"
    port: Option<u16>,
    message: Option<String>,
    attempt: Option<u32>,             // progress: 1-based attempt index
    max_attempts: Option<u32>,        // progress: total retries
    elapsed_ms: Option<u64>,          // progress: ms since health watch began
    logs: Option<Vec<String>>,        // failed: tail of the sidecar log file
}

#[cfg(desktop)]
impl SidecarStatus {
    fn starting(p: u16) -> Self {
        Self {
            status: "starting".into(), port: Some(p), message: None,
            attempt: None, max_attempts: None, elapsed_ms: None, logs: None,
        }
    }
    fn ready(p: u16) -> Self {
        Self {
            status: "ready".into(), port: Some(p), message: None,
            attempt: None, max_attempts: None, elapsed_ms: None, logs: None,
        }
    }
    fn failed(p: u16, msg: &str, logs: Vec<String>) -> Self {
        Self {
            status: "failed".into(), port: (p != 0).then_some(p),
            message: Some(msg.into()),
            attempt: None, max_attempts: None, elapsed_ms: None,
            logs: Some(logs),
        }
    }
    fn progress(p: u16, attempt: u32, max_attempts: u32, elapsed_ms: u64) -> Self {
        Self {
            status: "progress".into(), port: Some(p), message: None,
            attempt: Some(attempt), max_attempts: Some(max_attempts),
            elapsed_ms: Some(elapsed_ms), logs: None,
        }
    }
}

#[derive(Serialize, Deserialize)]
struct InstallResult {
    success: bool,
    path: String,
    message: Option<String>,
}

// ============================================================
// Sidecar log file (tail + reveal)
// ============================================================

/// The sidecar (when launched with piped stdout, i.e. by Tauri) redirects its
/// Python stdout/stderr to this file — see dawei/cli/commands/server.py. That
/// redirect is exactly why the supervisor's `CommandEvent::Stdout/Stderr`
/// captures almost nothing useful: the authoritative startup log lives HERE,
/// so we tail this file to make startup visible.
fn sidecar_log_path(port: u16) -> Option<std::path::PathBuf> {
    Some(dirs::home_dir()?.join(".normnomos").join("logs").join(format!("dawei-sidecar-{port}.log")))
}

/// Last `n` lines of the sidecar's log file (empty if missing/unreadable).
/// Attached to `failed` events so the failure screen shows the smoking gun
/// (e.g. a GBK import traceback) without the user hunting for the file.
#[cfg(desktop)]
fn read_log_tail(port: u16, n: usize) -> Vec<String> {
    let Some(path) = sidecar_log_path(port) else { return Vec::new() };
    let Ok(text) = std::fs::read_to_string(&path) else { return Vec::new() };
    let lines: Vec<&str> = text.lines().collect();
    let start = lines.len().saturating_sub(n);
    lines[start..].iter().map(|s| s.to_string()).collect()
}

/// Wall-clock ms since the Unix epoch, for `sidecar-log` timestamps.
#[cfg(desktop)]
fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

// ============================================================
// Sidecar lifecycle
// ============================================================

/// Bind a transient TCP socket to let the OS pick a free localhost port,
/// then drop the socket. Tiny race vs. another process grabbing it before
/// uvicorn rebinds is self-healing: the sidecar's non-interactive
/// port-in-use check exits non-zero, the monitor retries with a fresh port.
#[cfg(desktop)]
fn pick_free_port() -> Option<u16> {
    TcpListener::bind(("127.0.0.1", 0)).ok()?.local_addr().ok().map(|addr| addr.port())
}

/// Kill a process and its entire descendant tree.
///
/// The bundled `dawei.exe` is a PyInstaller bootloader (the process we actually
/// spawn) that re-execs the real uvicorn server in a *child* process.
/// `CommandChild::kill()` only terminates that bootloader, leaving the uvicorn
/// child orphaned and listening forever — which is exactly how stray dawei.exe
/// processes accumulated across previous app launches. Killing the whole tree
/// rooted at the spawned PID closes that leak on both restart and app exit.
///
/// On Windows this is `taskkill /F /T /PID <pid>` (`/T` walks the tree).
#[cfg(desktop)]
fn kill_process_tree(pid: u32) {
    #[cfg(target_os = "windows")]
    {
        let status = std::process::Command::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
        match status {
            Ok(s) if s.success() => {}
            // Non-zero usually just means the process already exited; harmless.
            _ => eprintln!(
                "[sidecar] taskkill /T for pid {} reported non-success (process may have already exited)",
                pid
            ),
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        // No taskkill /T on Unix: parse `ps` for every (pid, ppid), DFS the
        // subtree under `pid`, and SIGKILL the whole set at once — mirrors the
        // Windows toolhelp tree kill and handles the PyInstaller bootloader +
        // its uvicorn child (and deeper descendants). Uses the single `-o
        // pid,ppid` form (portable across BSD/macOS and Linux ps); the parser
        // skips the header line.
        let out = std::process::Command::new("ps")
            .args(["-A", "-o", "pid,ppid"])
            .output();
        if let Ok(o) = out {
            let mut procs: Vec<(u32, u32)> = Vec::new();
            for line in String::from_utf8_lossy(&o.stdout).lines() {
                let mut it = line.split_whitespace();
                if let (Some(a), Some(b)) = (it.next(), it.next()) {
                    if let (Ok(p), Ok(pp)) = (a.parse::<u32>(), b.parse::<u32>()) {
                        procs.push((p, pp));
                    }
                }
            }
            let mut stack = vec![pid];
            let mut victims: Vec<String> = vec![pid.to_string()];
            while let Some(p) = stack.pop() {
                for &(cid, cpid) in procs.iter() {
                    if cpid == p && cid != p {
                        stack.push(cid);
                        victims.push(cid.to_string());
                    }
                }
            }
            let _ = std::process::Command::new("kill")
                .arg("-9")
                .args(&victims)
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status();
        }
    }
}

/// macOS/Linux crash safety net (no kernel Job-Object equivalent on Unix).
///
/// Spawns a detached `sh` that polls normnomos's own PID; the instant we're
/// gone — a crash or force-kill, where `tauri://destroy` never fires — it reaps
/// every sidecar process. `pgrep -f 'dawei.*--sidecar'` matches both the
/// PyInstaller bootloader and its uvicorn child (both carry --sidecar in argv);
/// the `[ "$p" != "$$" ]` guard stops the watchdog matching its own script,
/// whose command line contains that pattern string.
#[cfg(all(desktop, not(target_os = "windows")))]
fn spawn_crash_watchdog() {
    let self_pid = std::process::id();
    let script = format!(
        "while kill -0 {self_pid} 2>/dev/null; do sleep 1; done; \
         for p in $(pgrep -f 'dawei.*--sidecar'); do \
           [ \"$p\" != \"$$\" ] && kill -9 \"$p\" 2>/dev/null; \
         done"
    );
    match std::process::Command::new("/bin/sh")
        .arg("-c")
        .arg(&script)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
    {
        Ok(_) => eprintln!("[sidecar] crash-watchdog armed (watching pid {self_pid})"),
        Err(e) => eprintln!("[sidecar] failed to arm crash-watchdog: {e}"),
    }
}

#[cfg(target_os = "windows")]
mod kill_job {
    //! Windows Job Object with kill-on-close. Every sidecar process — the
    //! PyInstaller bootloader AND the uvicorn child it spawns — is enrolled
    //! here, so the whole tree is terminated the moment normnomos.exe exits
    //! for *any* reason: a clean close (covered also by the destroy-handler
    //! taskkill), but crucially a crash or force-kill, where the
    //! `tauri://destroy` handler never runs. Closing the job's last handle
    //! (which the OS does on process death) trips JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.

    use std::mem;
    use std::sync::OnceLock;
    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W,
        TH32CS_SNAPPROCESS,
    };
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    use windows_sys::Win32::System::Threading::{OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE};

    // The job handle lives for the whole app (closing it = kill the job). Stored
    // as usize because raw HANDLE pointers are not Sync and can't sit in a static.
    static JOB: OnceLock<usize> = OnceLock::new();
    const ASSIGN_RIGHTS: u32 = PROCESS_SET_QUOTA | PROCESS_TERMINATE;

    /// Lazily create the kill-on-close job once and reuse it for every spawn.
    fn handle() -> usize {
        *JOB.get_or_init(|| unsafe {
            let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if job.is_null() {
                eprintln!("[sidecar] CreateJobObjectW failed; crash-cleanup disabled");
                return 0;
            }
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const core::ffi::c_void,
                mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            ) == 0
            {
                eprintln!("[sidecar] SetInformationJobObject failed; crash-cleanup disabled");
            }
            job as usize
        })
    }

    fn assign_pid(pid: u32) {
        let job = handle();
        if job == 0 {
            return;
        }
        unsafe {
            let proc = OpenProcess(ASSIGN_RIGHTS, 0, pid);
            if proc.is_null() {
                eprintln!("[sidecar] OpenProcess({}) failed; not added to kill job", pid);
                return;
            }
            if AssignProcessToJobObject(job as _, proc) == 0 {
                // Rare (e.g. nested-job conflict on old Windows). Not fatal: the
                // destroy-handler taskkill still covers a normal exit; the job is
                // only the crash safety net.
                eprintln!("[sidecar] AssignProcessToJobObject({}) failed", pid);
            }
            CloseHandle(proc);
        }
    }

    /// Enroll `root_pid` and every currently-existing descendant in the job.
    /// Children spawned *after* the parent joins auto-inherit the job — this
    /// only mops up the uvicorn child the bootloader spawns in the tiny window
    /// between CreateProcess and this call.
    pub fn assign_tree(root_pid: u32) {
        assign_pid(root_pid);

        // Snapshot all (pid, ppid) pairs, then DFS the subtree under root_pid.
        let mut procs: Vec<(u32, u32)> = Vec::new();
        unsafe {
            let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
            if snap as usize == INVALID_HANDLE_VALUE as usize {
                return;
            }
            let mut entry: PROCESSENTRY32W = mem::zeroed();
            entry.dwSize = mem::size_of::<PROCESSENTRY32W>() as u32;
            if Process32FirstW(snap, &mut entry) != 0 {
                loop {
                    procs.push((entry.th32ProcessID, entry.th32ParentProcessID));
                    if Process32NextW(snap, &mut entry) == 0 {
                        break;
                    }
                }
            }
            CloseHandle(snap);
        }

        let mut stack = vec![root_pid];
        while let Some(p) = stack.pop() {
            for &(cid, cpid) in procs.iter() {
                if cpid == p && cid != p {
                    assign_pid(cid);
                    stack.push(cid);
                }
            }
        }
    }
}

/// Pick a fresh port, record it, emit `starting`, launch a generation-tagged
/// health watcher, and return a configured sidecar `Command` ready to spawn.
/// Returns `None` only if port-pick or command construction fails.
#[cfg(desktop)]
fn prepare_sidecar(app: &tauri::AppHandle) -> Option<(u16, tauri_plugin_shell::process::Command)> {
    let port = pick_free_port()?;
    SIDECAR_PORT.store(port, Ordering::SeqCst);
    let gen = SIDECAR_GEN.fetch_add(1, Ordering::SeqCst) + 1;
    let _ = app.emit("sidecar-status", SidecarStatus::starting(port));

    // Stream the sidecar's log file to the webview so startup is observable.
    // Bound to this generation: a restart bumps SIDECAR_GEN and the old tailer
    // exits so logs from the superseded port don't interleave with the new one.
    spawn_log_tailer(app.clone(), port, gen);

    // Health watcher bound to this generation — ignored if superseded.
    let app_h = app.clone();
    tauri::async_runtime::spawn(async move {
        let healthy = wait_for_health(&app_h, port, gen, 30, 2).await;
        if SIDECAR_GEN.load(Ordering::SeqCst) != gen {
            return; // a newer spawn has replaced this one
        }
        if healthy {
            eprintln!("[sidecar] healthy on port {}", port);
            let _ = app_h.emit("sidecar-status", SidecarStatus::ready(port));
        } else {
            eprintln!("[sidecar] health check timeout on port {}", port);
            let logs = read_log_tail(port, 40);
            let _ = app_h.emit(
                "sidecar-status",
                SidecarStatus::failed(port, "本地引擎健康检查超时", logs),
            );
        }
    });

    let port_str = port.to_string();
    let mut cmd = match app.shell().sidecar("dawei") {
        Ok(c) => c.args([
            "server", "start", "--host", "127.0.0.1",
            "--port", port_str.as_str(), "--sidecar",
        ]),
        Err(e) => {
            eprintln!("[sidecar] failed to create sidecar command: {}", e);
            return None;
        }
    };
    // WS/HTTP JWT 鉴权密钥注入:sidecar 进程不继承 agent/.env(CWD 不同),
    // 缺省时引擎用开发默认密钥 → 真实登录 token 全部 403(2026-08-29 实锤)。
    // 解析链:进程 env JWT_SECRET > ~/.normnomos/.env 的 JWT_SECRET 行。
    if let Some(secret) = resolve_jwt_secret() {
        cmd = cmd.env("JWT_SECRET", secret);
        eprintln!("[sidecar] JWT_SECRET injected from config");
    } else {
        eprintln!("[sidecar] WARN: JWT_SECRET not found (env or ~/.normnomos/.env) — WS auth will use dev default");
    }
    Some((port, cmd))
}

/// 解析 sidecar 用的 JWT 签名密钥(与 nn-user-system 共享)。
#[cfg(desktop)]
fn resolve_jwt_secret() -> Option<String> {
    if let Ok(v) = std::env::var("JWT_SECRET") {
        if !v.trim().is_empty() {
            return Some(v.trim().to_string());
        }
    }
    let path = dirs::home_dir()?.join(".normnomos").join(".env");
    let content = std::fs::read_to_string(path).ok()?;
    for line in content.lines() {
        let line = line.trim();
        if let Some(rest) = line.strip_prefix("JWT_SECRET=") {
            let v = rest.trim().trim_matches('"').trim_matches('\'').to_string();
            if !v.is_empty() {
                return Some(v);
            }
        }
    }
    None
}

/// Spawn the dawei sidecar and supervise it: monitor stdout/termination,
/// retry up to `MAX_RESTART_COUNT` times (each on a fresh port), and emit
/// `sidecar-status` events for the webview.
#[cfg(desktop)]
fn spawn_sidecar(app: &tauri::AppHandle) {
    let (_port, cmd) = match prepare_sidecar(app) {
        Some(v) => v,
        None => {
            eprintln!("[sidecar] initial prepare failed");
            return;
        }
    };

    let (mut current_rx, child) = match cmd.spawn() {
        Ok(pair) => pair,
        Err(e) => {
            eprintln!("[sidecar] spawn failed: {}", e);
            let _ = app.emit(
                "sidecar-status",
                SidecarStatus::failed(0, &format!("spawn 失败: {e}"), Vec::new()),
            );
            return;
        }
    };

    eprintln!("[sidecar] spawned dawei sidecar, waiting for health...");

    // Enroll the sidecar tree in the kill-on-close job so it is reaped even if
    // normnomos.exe crashes or is force-killed (where destroy can't fire).
    #[cfg(target_os = "windows")]
    kill_job::assign_tree(child.pid());

    // Store child handle for cleanup on exit / supervised restart.
    let child_handle = Arc::new(std::sync::Mutex::new(Some(child)));

    let app_handle = app.clone();
    let restart_cnt = Arc::new(AtomicU32::new(0));
    let child_for_monitor = child_handle.clone();

    // Single supervisor task: monitors stdout/stderr AND handles restart on termination.
    tauri::async_runtime::spawn(async move {
        // Wait a bit for the initial sidecar to start.
        tokio::time::sleep(std::time::Duration::from_secs(3)).await;

        loop {
            // Monitor output and wait for termination event.
            let terminated = loop {
                match current_rx.recv().await {
                    Some(CommandEvent::Stdout(line)) => {
                        let s = String::from_utf8_lossy(&line).to_string();
                        eprintln!("[sidecar] {}", s);
                        let _ = app_handle.emit(
                            "sidecar-log",
                            serde_json::json!({ "line": s.trim_end(), "ts_ms": now_ms() }),
                        );
                    }
                    Some(CommandEvent::Stderr(line)) => {
                        let s = String::from_utf8_lossy(&line).to_string();
                        eprintln!("[sidecar:err] {}", s);
                        let _ = app_handle.emit(
                            "sidecar-log",
                            serde_json::json!({ "line": s.trim_end(), "ts_ms": now_ms() }),
                        );
                    }
                    Some(CommandEvent::Terminated(status)) => {
                        eprintln!("[sidecar] terminated: {:?}", status);
                        break true;
                    }
                    Some(CommandEvent::Error(e)) => {
                        eprintln!("[sidecar] error: {}", e);
                        break true;
                    }
                    Some(_) => {}
                    None => {
                        break false;
                    }
                }
            };

            if !terminated {
                eprintln!("[sidecar] output stream ended without termination");
                return;
            }

            // Check if sidecar was intentionally killed (app exit) — don't restart.
            {
                let guard = child_for_monitor.lock().unwrap();
                if guard.is_none() {
                    return;
                }
            }

            // Attempt restart (on a fresh port).
            let count = restart_cnt.fetch_add(1, Ordering::SeqCst) + 1;
            eprintln!("[sidecar] exited, restart attempt {}/{}", count, MAX_RESTART_COUNT);

            if count > MAX_RESTART_COUNT {
                eprintln!("[sidecar] max restarts reached, giving up");
                let port = SIDECAR_PORT.load(Ordering::SeqCst);
                let logs = read_log_tail(port, 40);
                let _ = app_handle.emit(
                    "sidecar-status",
                    SidecarStatus::failed(port, "多次重启后仍失败", logs),
                );
                return;
            }

            let (new_port, new_cmd) = match prepare_sidecar(&app_handle) {
                Some(v) => v,
                None => {
                    eprintln!("[sidecar] restart prepare failed");
                    return;
                }
            };
            eprintln!("[sidecar] restarting on port {}", new_port);

            let (new_rx, new_child) = match new_cmd.spawn() {
                Ok(p) => p,
                Err(e) => {
                    eprintln!("[sidecar] restart spawn failed: {}", e);
                    return;
                }
            };

            #[cfg(target_os = "windows")]
            kill_job::assign_tree(new_child.pid());

            {
                let mut guard = child_for_monitor.lock().unwrap();
                // Tear down the previous sidecar's whole process tree before
                // replacing the handle. The bundled dawei.exe is a PyInstaller
                // bootloader that runs uvicorn in a child process; merely
                // dropping the old CommandChild (or killing only the parent)
                // would orphan that uvicorn child.
                if let Some(old) = guard.take() {
                    let old_pid = old.pid();
                    eprintln!(
                        "[sidecar] killing previous sidecar tree (pid {}) on restart",
                        old_pid
                    );
                    kill_process_tree(old_pid);
                }
                *guard = Some(new_child);
            }

            current_rx = new_rx;
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        }
    });

    // Kill sidecar on app exit. Kill the *whole tree* (not just the parent
    // bootloader) so the uvicorn child process isn't orphaned — which is what
    // leaked dawei.exe processes across previous launches.
    let kill_handle = child_handle.clone();
    app.once("tauri://destroy", move |_event| {
        let mut guard = kill_handle.lock().unwrap();
        if let Some(child) = guard.take() {
            let pid = child.pid();
            eprintln!("[sidecar] killing sidecar tree (pid {}) on app exit", pid);
            kill_process_tree(pid);
        }
    });
}

/// Poll the sidecar health endpoint up to `retries` times, waiting `interval_secs`
/// between attempts. Emits a `progress` event before each attempt (1-based) so the
/// overlay shows live "第 N/M 次 · 已等待 Xs" instead of a blind spinner. Each emit
/// is gated on `gen`: if a newer spawn superseded this watcher, it stops early so
/// a stale watcher can't overwrite the live overlay.
#[cfg(desktop)]
async fn wait_for_health(
    app: &tauri::AppHandle,
    port: u16,
    gen: u32,
    retries: u32,
    interval_secs: u64,
) -> bool {
    let url = format!("http://127.0.0.1:{port}/api/health");
    let client = reqwest::Client::new();
    let start = std::time::Instant::now();
    for i in 0..retries {
        // A newer spawn replaced us — stop emitting; the new watcher owns the overlay.
        if SIDECAR_GEN.load(Ordering::SeqCst) != gen {
            return false;
        }
        let _ = app.emit(
            "sidecar-status",
            SidecarStatus::progress(port, i + 1, retries, start.elapsed().as_millis() as u64),
        );
        // /api/health is a lightweight liveness probe: once uvicorn is up it
        // answers in <100ms, and while it's not listening the connect is refused
        // instantly. A 2s timeout (down from 5s) is plenty and tightens the
        // worst-case wait without risking a false negative — a miss just retries.
        match client
            .get(&url)
            .timeout(std::time::Duration::from_secs(2))
            .send()
            .await
        {
            Ok(resp) if resp.status().is_success() => return true,
            _ => {
                if i < retries - 1 {
                    tokio::time::sleep(std::time::Duration::from_secs(interval_secs)).await;
                }
            }
        }
    }
    false
}

/// Stream newly-appended lines of the sidecar's log file to the webview as
/// `sidecar-log` events, so the startup overlay can show what the engine is
/// actually doing (uvicorn boot, model load, or a crash traceback).
///
/// The sidecar writes its Python stdout/stderr to the file (see
/// `sidecar_log_path`), so we tail *that* rather than relying on
/// `CommandEvent::Stdout`, which captures almost nothing. Each instance starts
/// at EOF (only new lines — never replays a previous run) and self-terminates
/// the moment its generation is superseded by a restart. Uses blocking `std::fs`
/// inside an interval-gated async loop: reads are tiny and spaced 300ms apart,
/// so the blocking is negligible and no `tokio::fs`/tail crate is warranted.
#[cfg(desktop)]
fn spawn_log_tailer(app: tauri::AppHandle, port: u16, gen: u32) {
    tauri::async_runtime::spawn(async move {
        let Some(path) = sidecar_log_path(port) else { return };

        // Wait (up to ~10s) for the sidecar to create the file.
        for _ in 0..50 {
            if path.exists() {
                break;
            }
            if SIDECAR_GEN.load(Ordering::SeqCst) != gen {
                return;
            }
            tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        }

        // Start at EOF so we only emit lines appended after we attach.
        let mut offset = match std::fs::metadata(&path) {
            Ok(m) => m.len(),
            Err(_) => return,
        };

        use std::io::{Read, Seek, SeekFrom};
        loop {
            if SIDECAR_GEN.load(Ordering::SeqCst) != gen {
                return;
            }
            tokio::time::sleep(std::time::Duration::from_millis(300)).await;

            let len = match std::fs::metadata(&path) {
                Ok(m) => m.len(),
                Err(_) => continue,
            };
            if len < offset {
                // File was truncated/rotated under us — restart from the top.
                offset = 0;
            }
            if len == offset {
                continue; // nothing new
            }

            let Ok(mut f) = std::fs::File::open(&path) else { continue };
            if f.seek(SeekFrom::Start(offset)).is_err() {
                continue;
            }
            let mut buf = Vec::with_capacity((len - offset) as usize);
            if f.read_to_end(&mut buf).is_err() {
                continue;
            }
            offset = len;

            let text = String::from_utf8_lossy(&buf);
            for line in text.lines() {
                if line.trim().is_empty() {
                    continue;
                }
                let _ = app.emit(
                    "sidecar-log",
                    serde_json::json!({ "line": line, "ts_ms": now_ms() }),
                );
            }
        }
    });
}

// ============================================================
// Tauri commands
// ============================================================

/// The port the sidecar is running on (or being started on). `None` if not
/// yet assigned. Called by the webview at boot to resolve its API/WS base URL.
#[tauri::command]
fn get_sidecar_port() -> Option<u16> {
    let p = SIDECAR_PORT.load(Ordering::SeqCst);
    (p != 0).then_some(p)
}

/// Relaunch the whole app — used by the failure overlay's "restart" button.
/// A full restart re-runs `spawn_sidecar` cleanly (new port, fresh health check)
/// without coordinating supervisor state from the webview.
#[tauri::command]
fn restart_app(app: tauri::AppHandle) {
    app.restart();
}

/// Open the sidecar log directory (or reveal the current port's log file) in the
/// OS file manager — used by the failure overlay's "打开日志文件夹" button so
/// support can grab `~/.normnomos/logs/dawei-sidecar-<port>.log` quickly. There
/// is no `tauri-plugin-opener` and `shell:allow-open` is URL-only, so this shells
/// out to the platform's file manager directly.
#[tauri::command]
fn reveal_sidecar_log(port: Option<u16>) -> Result<bool, String> {
    let dir = dirs::home_dir()
        .ok_or_else(|| "cannot resolve home directory".to_string())?
        .join(".normnomos")
        .join("logs");

    // Prefer to reveal the specific port's file if it exists; else open the dir.
    let target_file = port.and_then(sidecar_log_path).filter(|p| p.exists());

    let mut cmd = if cfg!(target_os = "windows") {
        let mut c = std::process::Command::new("explorer");
        match &target_file {
            Some(f) => {
                // explorer's "/select," takes the path as the next arg.
                c.arg(format!("/select,{}", f.display()));
            }
            None => {
                c.arg(dir.display().to_string());
            }
        }
        c
    } else if cfg!(target_os = "macos") {
        let mut c = std::process::Command::new("open");
        match &target_file {
            Some(f) => {
                c.arg("-R").arg(f);
            }
            None => {
                c.arg(&dir);
            }
        }
        c
    } else {
        let mut c = std::process::Command::new("xdg-open");
        c.arg(&dir);
        c
    };

    cmd.spawn().map_err(|e| format!("failed to open log folder: {e}"))?;
    Ok(true)
}

/// Install a resource by downloading it from the market API to ~/.davybot-nn/
#[tauri::command]
async fn install_resource(
    resource_id: String,
    resource_type: String,
    resource_name: String,
    download_url: String,
    auth_token: Option<String>,
) -> Result<InstallResult, String> {
    let home = dirs::home_dir().ok_or("Cannot find home directory")?;
    let base_dir = home.join(".davybot-nn");

    // Create type-specific subdirectory
    let install_dir = base_dir.join(&resource_type);
    fs::create_dir_all(&install_dir).map_err(|e| format!("Failed to create directory: {}", e))?;

    // Sanitize resource name for filesystem
    let safe_name = sanitize_resource_name(&resource_name);
    let file_path = install_dir.join(format!("{}-{}", safe_name, &resource_id[..8.min(resource_id.len())]));

    // Download the resource
    let client = reqwest::Client::new();
    let mut req = client.get(&download_url);
    if let Some(token) = auth_token {
        req = req.bearer_auth(&token);
    }

    let resp = req
        .send()
        .await
        .map_err(|e| format!("Download failed: {}", e))?;

    if !resp.status().is_success() {
        return Ok(InstallResult {
            success: false,
            path: file_path.display().to_string(),
            message: Some(format!("HTTP {}", resp.status())),
        });
    }

    let bytes = resp
        .bytes()
        .await
        .map_err(|e| format!("Failed to read response: {}", e))?;

    fs::write(&file_path, &bytes).map_err(|e| format!("Failed to write file: {}", e))?;

    // Create metadata file
    let meta = serde_json::json!({
        "id": resource_id,
        "type": resource_type,
        "name": resource_name,
        "installed_at": chrono::Utc::now().to_rfc3339(),
    });
    let meta_path = file_path.with_extension("meta.json");
    fs::write(&meta_path, serde_json::to_string_pretty(&meta).unwrap_or_default())
        .map_err(|e| format!("Failed to write metadata: {}", e))?;

    Ok(InstallResult {
        success: true,
        path: file_path.display().to_string(),
        message: None,
    })
}

/// Check if a resource is already installed
#[tauri::command]
fn is_resource_installed(resource_id: String) -> Result<bool, String> {
    let home = dirs::home_dir().ok_or("Cannot find home directory")?;
    let base_dir = home.join(".davybot-nn");

    if !base_dir.exists() {
        return Ok(false);
    }

    // Check for any file containing the resource ID prefix
    for entry in fs::read_dir(&base_dir).map_err(|e| format!("Failed to read dir: {}", e))? {
        let entry = entry.map_err(|e| format!("Failed to read entry: {}", e))?;
        let path = entry.path();
        if path.is_dir() {
            for file in fs::read_dir(&path).map_err(|e| format!("Failed to read dir: {}", e))? {
                let file = file.map_err(|e| format!("Failed to read file: {}", e))?;
                let file_name = file.file_name();
                let name = file_name.to_string_lossy();
                if name.contains(&resource_id[..8.min(resource_id.len())]) {
                    return Ok(true);
                }
            }
        }
    }

    Ok(false)
}

/// Sanitize a resource name for safe filesystem usage.
/// Replaces non-alphanumeric characters (except `-` and `_`) with `_`.
fn sanitize_resource_name(name: &str) -> String {
    name.chars()
        .map(|c| if c.is_alphanumeric() || c == '-' || c == '_' { c } else { '_' })
        .collect()
}

// ============================================================
// Main
// ============================================================

/// Entry point shared by the desktop binary (src/main.rs) and mobile
/// (Android/iOS load this crate as a cdylib; `mobile_entry_point` generates
/// the JNI glue the generated Kotlin/Swift host calls into).
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_http::init());

    // Single-instance is a desktop-only plugin (mobile apps are always
    // single-instance by OS design); guard so it links only on desktop.
    #[cfg(desktop)]
    let builder = builder.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
        // Second instance: bring existing window to front instead of spawning a new one.
        let windows = app.webview_windows();
        for (_, window) in windows {
            let _: Result<(), _> = window.set_focus();
            let _: Result<(), _> = window.unminimize();
            let _: Result<(), _> = window.show();
        }
    }));

    builder
        .setup(|app| {
            // Desktop only: launch and supervise the bundled dawei sidecar.
            // Mobile (Android/iOS) cannot exec bundled binaries — the frontend
            // is built with --mode mobile there and runs in cloud mode against
            // the build-time VITE_* endpoints instead.
            #[cfg(desktop)]
            {
                let handle = app.handle().clone();
                // Crash safety net: reap the sidecar even if normnomos is
                // force-killed. Windows uses the kill-on-close Job Object for
                // this; macOS/Linux arm a tiny detached watchdog that polls our
                // own PID.
                #[cfg(not(target_os = "windows"))]
                spawn_crash_watchdog();
                spawn_sidecar(&handle);
            }
            #[cfg(mobile)]
            let _ = app;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            install_resource,
            is_resource_installed,
            get_sidecar_port,
            restart_app,
            reveal_sidecar_log,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize_simple() {
        assert_eq!(sanitize_resource_name("hello"), "hello");
    }

    #[test]
    fn test_sanitize_with_spaces() {
        assert_eq!(sanitize_resource_name("my resource"), "my_resource");
    }

    #[test]
    fn test_sanitize_with_special_chars() {
        // . is not alphanumeric in Rust
        assert_eq!(
            sanitize_resource_name("skill@v1.2/legal!helper"),
            "skill_v1_2_legal_helper"
        );
    }

    #[test]
    fn test_sanitize_keeps_hyphens_and_underscores() {
        assert_eq!(
            sanitize_resource_name("my-skill_name"),
            "my-skill_name"
        );
    }

    #[test]
    fn test_sanitize_chinese() {
        // Chinese characters ARE alphanumeric in Rust (Unicode-aware)
        assert_eq!(sanitize_resource_name("法律助手"), "法律助手");
    }

    #[test]
    fn test_sanitize_empty() {
        assert_eq!(sanitize_resource_name(""), "");
    }

    #[test]
    fn test_sanitize_mixed() {
        // Space → _, . → _
        assert_eq!(
            sanitize_resource_name("Legal Agent v2.0"),
            "Legal_Agent_v2_0"
        );
    }

    #[test]
    fn test_sanitize_dots() {
        // Dots are not alphanumeric
        assert_eq!(sanitize_resource_name("file.tar.gz"), "file_tar_gz");
    }
}
