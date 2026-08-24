//! 生命周期状态机：cmd 会话管理、HTTP 就绪探测、浮层几何同步、退出清理。

use crate::settings::Settings;
use crate::terminal;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager};

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Phase {
    Boot,
    Ready,
    Failed,
    /// 用户手动停止服务后进入的状态（区别于启动失败）
    Stopped,
}

pub struct AppInner {
    pub settings: Settings,
    /// 配置目录（便携模式=程序目录，否则 %APPDATA%\com.lantai.app）
    pub config_dir: PathBuf,
    pub phase: Phase,
    pub message: Option<String>,
    pub url: String,
    pub zoom: f64,
    pub term: Option<terminal::TerminalSession>,
    /// 终端输出环形缓冲：页面晚订阅时补发快照，避免启动早期输出丢失
    pub term_buffer: String,
    /// 连续自动重启计数（达上限后停止）
    pub restart_count: u32,
    /// 探针/保活线程的代次：重启服务时自增，旧线程据此退出
    pub gen: u64,
    pub probe_stop: Arc<AtomicBool>,
    /// 本次启动生效的就绪超时（秒）
    pub ready_timeout: u64,
}

/// 终端输出缓冲上限（字节）
const TERM_BUFFER_MAX: usize = 65536;

/// 截断终端缓冲到上限（保留后半段）。按 UTF-8 字符边界截断，避免 panic。
pub fn truncate_term_buffer(buf: &mut String) {
    if buf.len() > TERM_BUFFER_MAX {
        let cut = buf.floor_char_boundary(buf.len() - TERM_BUFFER_MAX / 2);
        *buf = buf[cut..].to_string();
    }
}

impl AppInner {
    pub fn new(settings: Settings, config_dir: PathBuf) -> Self {
        let url = format!("http://127.0.0.1:{}/", settings.port);
        let zoom = settings.zoom;
        let ready_timeout = settings.ready_timeout_sec;
        Self {
            settings,
            config_dir,
            phase: Phase::Boot,
            message: None,
            url,
            zoom,
            term: None,
            term_buffer: String::new(),
            restart_count: 0,
            gen: 0,
            probe_stop: Arc::new(AtomicBool::new(false)),
            ready_timeout,
        }
    }
}

// ---------- 状态广播 ----------

pub fn emit_state(app: &AppHandle, inner: &Arc<Mutex<AppInner>>) {
    let g = inner.lock().unwrap();
    let _ = app.emit(
        "state:changed",
        serde_json::json!({
            "phase": g.phase,
            "message": g.message,
            "url": g.url,
            "zoom": g.zoom,
        }),
    );
}

pub fn set_phase(
    app: &AppHandle,
    inner: &Arc<Mutex<AppInner>>,
    phase: Phase,
    message: Option<String>,
) {
    let log_msg = message.clone().unwrap_or_default();
    {
        let mut g = inner.lock().unwrap();
        g.phase = phase;
        g.message = message;
    }
    eprintln!("[lantai-shell] phase -> {phase:?} {log_msg}");
    emit_state(app, inner);
}

// ---------- 工作目录 ----------

/// 工作目录解析：设置指定则用之；留空则用壳程序（lantai-shell.exe）所在目录——
/// 兰台服务（lantai.exe）的数据目录基于可执行文件位置（冻结模式 BASE_DIR），
/// 与 cwd 无关，因此便携目录内启动天然正确。
fn resolve_workdir(settings: &Settings) -> PathBuf {
    let wd = settings.working_dir.trim();
    if !wd.is_empty() {
        PathBuf::from(wd)
    } else {
        std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.to_path_buf()))
            .unwrap_or_else(|| PathBuf::from("C:\\"))
    }
}

// ---------- HTTP 探测 ----------

fn http_ok(port: u16) -> bool {
    let addr = format!("127.0.0.1:{port}");
    let Ok(mut sock) = TcpStream::connect_timeout(
        &addr.parse().unwrap_or_else(|_| "127.0.0.1:1".parse().unwrap()),
        Duration::from_millis(800),
    ) else {
        return false;
    };
    let _ = sock.set_read_timeout(Some(Duration::from_millis(800)));
    let req = format!(
        "GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
    );
    if sock.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 128];
    match sock.read(&mut buf) {
        Ok(n) => {
            let head = String::from_utf8_lossy(&buf[..n]);
            head.starts_with("HTTP/1.1 200")
                || head.starts_with("HTTP/1.0 200")
                || head.starts_with("HTTP/1.1 30")
                || head.starts_with("HTTP/1.0 30")
        }
        Err(_) => false,
    }
}

// ---------- 代理 ----------

/// 从 `reg query` 输出解析系统代理：ProxyEnable=1 且 ProxyServer 非空。
fn parse_reg_proxy_output(output: &str) -> Option<String> {
    let mut enabled = false;
    let mut server = String::new();
    for line in output.lines() {
        let lower = line.to_lowercase();
        if lower.contains("proxyenable") {
            // 行尾形如 "0x1"（REG_DWORD 十六进制）
            enabled = line
                .split_whitespace()
                .last()
                .map(|v| v.trim_start_matches("0x").parse::<u32>().unwrap_or(0) != 0)
                .unwrap_or(false);
        } else if lower.contains("proxyserver") {
            // "ProxyServer  REG_SZ  127.0.0.1:10808"（值可能含空格）
            if let Some(idx) = line.find("REG_SZ") {
                server = line[idx + "REG_SZ".len()..].trim().to_string();
            }
        }
    }
    if enabled && !server.is_empty() {
        Some(server)
    } else {
        None
    }
}

/// 读取 Windows 系统代理（WinINET / IE 设置，HKCU）：
/// ProxyEnable=1 时返回 ProxyServer 原始值
/// （可能是 `host:port`，或 `http=...;https=...;...` 多协议格式）。
fn system_proxy() -> Option<String> {
    let out = std::process::Command::new("reg")
        .args([
            "query",
            "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings",
        ])
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    parse_reg_proxy_output(&String::from_utf8_lossy(&out.stdout))
}

/// 归一化代理地址：裸 `host:port` → `http://host:port`；
/// `http=...;https=...;` 多协议串取 http/https 段。
fn normalize_proxy(raw: &str) -> Option<String> {
    let raw = raw.trim();
    if raw.is_empty() {
        return None;
    }
    if raw.contains('=') {
        // 多协议串：取 http=/https= 段
        for seg in raw.split(';') {
            let seg = seg.trim();
            if let Some((k, v)) = seg.split_once('=') {
                let k = k.trim();
                if (k.eq_ignore_ascii_case("http") || k.eq_ignore_ascii_case("https"))
                    && !v.trim().is_empty()
                {
                    let v = v.trim();
                    return Some(if v.contains("://") {
                        v.to_string()
                    } else {
                        format!("http://{v}")
                    });
                }
            }
        }
        return None;
    }
    Some(if raw.contains("://") {
        raw.to_string()
    } else {
        format!("http://{raw}")
    })
}

/// 按设置应用代理环境变量（HTTP_PROXY/HTTPS_PROXY 及小写变体），
/// 供 npx/npm 下载使用；无代理时清除，避免沿用陈旧值。
fn apply_proxy_env(settings: &Settings) {
    let proxy = if settings.use_system_proxy {
        system_proxy().and_then(|s| normalize_proxy(&s))
    } else if !settings.proxy_url.trim().is_empty() {
        normalize_proxy(&settings.proxy_url)
    } else {
        None
    };
    match &proxy {
        Some(p) => {
            eprintln!("[lantai-shell] proxy env -> {p}");
            std::env::set_var("HTTP_PROXY", p);
            std::env::set_var("HTTPS_PROXY", p);
            std::env::set_var("http_proxy", p);
            std::env::set_var("https_proxy", p);
        }
        None => {
            eprintln!("[lantai-shell] proxy: none");
            for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"] {
                std::env::remove_var(k);
            }
        }
    }
}

// ---------- 启动流程 ----------

/// 端口是否已被监听（TCP 层）：有监听即视为占用，直接连接
fn port_listening(port: u16) -> bool {
    let addr = format!("127.0.0.1:{port}");
    TcpStream::connect_timeout(
        &addr.parse().unwrap_or_else(|_| "127.0.0.1:1".parse().unwrap()),
        Duration::from_millis(800),
    )
    .is_ok()
}

/// 从 `netstat -ano` 输出解析"监听指定端口"的 PID 列表（去重）。
/// 行格式（Windows netstat 固定英文输出）：
///   TCP    127.0.0.1:3080    0.0.0.0:0    LISTENING    12345
///   TCP    [::]:3080         [::]:0        LISTENING    12345
/// 匹配 `:{port}` 后必须是空白/行尾，避免 30800 之类误命中。
fn parse_listening_pids(output: &str, port: u16) -> Vec<u32> {
    let needle = format!(":{port}");
    let mut pids: Vec<u32> = Vec::new();
    for line in output.lines() {
        let lower = line.to_lowercase();
        if !lower.contains("listening") {
            continue;
        }
        // 逐段查找 :port，确认后一位是空白或行尾
        let mut idx = 0;
        let mut hit = false;
        while let Some(rel) = lower[idx..].find(&needle) {
            let pos = idx + rel;
            let after = &lower[pos + needle.len()..];
            if after.is_empty() || after.starts_with(|c: char| c.is_whitespace()) {
                hit = true;
                break;
            }
            idx = pos + needle.len();
        }
        if !hit {
            continue;
        }
        // 行尾 token 是 PID（ASCII 数字）
        if let Some(pid) = line
            .split_whitespace()
            .last()
            .and_then(|t| t.parse::<u32>().ok())
        {
            if !pids.contains(&pid) {
                pids.push(pid);
            }
        }
    }
    pids
}

/// 按端口结束进程：netstat 找监听 PID → taskkill /T /F 杀整树。
/// 用于结束 keep-alive 后台服务（脱离客户端的进程树无法经 JobObject 清理）。
/// 竞态处理：当前会话树刚被 JobObject 整树终止时，端口释放是异步的——
/// 若 netstat 找不到监听进程，须再确认端口是否已释放；已释放视为成功（无需按端口杀），
/// 否则短暂重试后仍找不到才报错。
fn kill_by_port(port: u16) -> Result<(), String> {
    for attempt in 0..3 {
        let out = std::process::Command::new("netstat")
            .args(["-ano"])
            .output()
            .map_err(|e| format!("无法执行 netstat：{e}"))?;
        let pids = parse_listening_pids(&String::from_utf8_lossy(&out.stdout), port);
        if !pids.is_empty() {
            for pid in &pids {
                eprintln!("[lantai-shell] killing pid {pid} (port {port})");
                match std::process::Command::new("taskkill")
                    .args(["/PID", &pid.to_string(), "/T", "/F"])
                    .status()
                {
                    Ok(st) if st.success() => {}
                    Ok(st) => eprintln!("[lantai-shell] taskkill {pid} exited {st:?}"),
                    Err(e) => eprintln!("[lantai-shell] taskkill {pid} failed: {e}"),
                }
            }
            if port_listening(port) {
                return Err(format!("端口 {port} 仍被监听（进程可能无权限结束）"));
            }
            return Ok(());
        }
        // 未找到监听进程：端口已释放 = 进程已被整树终止，无需按端口杀
        if !port_listening(port) {
            return Ok(());
        }
        eprintln!("[lantai-shell] kill_by_port: port {port} still held, retry {attempt}");
        std::thread::sleep(Duration::from_millis(300));
    }
    Err(format!("未找到监听端口 {port} 的进程"))
}

/// 终端输出中的失败特征（小写匹配）：命中即快速失败，不必干等超时
const FAIL_PATTERNS: &[&str] = &[
    "eaddrinuse",
    "is not recognized",
    "command not found",
    "npm error",
    "npm err!",
    "fatal error",
    "unhandled exception",
];

pub fn boot(app: &AppHandle, inner: &Arc<Mutex<AppInner>>) {
    let settings = { inner.lock().unwrap().settings.clone() };
    let port = settings.port;
    // 端口已被占用 → 直接连接（不区分占用者是否为兰台服务，
    // 也无需 HTTP 200：TCP 有监听即直连，避免误启动撞 EADDRINUSE）
    if port_listening(port) {
        eprintln!("[lantai-shell] port {port} occupied, connect directly");
        // 仍提供终端会话（不喂启动命令），供查看/排查
        start_session(app, inner, false);
        if let Some(t) = inner.lock().unwrap().term.as_mut() {
            t.write(
                format!(
                    "echo [lantai-shell] 端口 {port} 已有服务监听，已直接连接；若页面显示异常，可能是非兰台服务占用该端口\r"
                )
                .as_bytes(),
            );
        }
        set_phase(app, inner, Phase::Ready, None);
        start_keepalive(app, inner.clone());
        return;
    }
    eprintln!("[lantai-shell] port {port} free, starting session");
    start_session(app, inner, true);
    start_probe(app.clone(), inner.clone());
}

fn start_session(app: &AppHandle, inner: &Arc<Mutex<AppInner>>, feed: bool) {
    let (settings, workdir) = {
        let g = inner.lock().unwrap();
        let workdir = resolve_workdir(&g.settings);
        (g.settings.clone(), workdir)
    };

    // 代次 +1，令旧探针/保活线程失效
    {
        let mut g = inner.lock().unwrap();
        g.probe_stop.store(true, Ordering::Relaxed);
        g.gen += 1;
        g.term = None;
    }

    set_phase(app, inner, Phase::Boot, None);

    let (session, reader) = match terminal::spawn(&workdir, 24, 100) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("[lantai-shell] cmd spawn failed: {e}");
            set_phase(
                app,
                inner,
                Phase::Failed,
                Some(format!("无法启动 cmd 会话：{e}")),
            );
            return;
        }
    };
    eprintln!(
        "[lantai-shell] cmd session spawned, workdir={}",
        workdir.display()
    );

    // 喂入：切 UTF-8 → 进入工作目录 →（可选）执行启动命令
    let mut feed_str = String::from("chcp 65001 >nul\r");
    let wd = workdir.to_string_lossy().to_string();
    if !wd.is_empty() {
        feed_str.push_str(&format!("cd /d \"{}\"\r", wd.replace('"', "\"\"")));
    }
    if feed {
        feed_str.push_str(&settings.startup_command);
        feed_str.push('\r');
    }

    {
        let mut g = inner.lock().unwrap();
        g.probe_stop.store(false, Ordering::Relaxed);
        g.term_buffer.clear();
        g.term = Some(session);
    }
    if let Some(t) = inner.lock().unwrap().term.as_mut() {
        t.write(feed_str.as_bytes());
    }

    // 读取线程：ConPTY 输出 → 前端；同时扫描失败特征
    let app2 = app.clone();
    let inner2 = inner.clone();
    let gen = { inner.lock().unwrap().gen };
    std::thread::spawn(move || {
        let mut reader = reader;
        let mut buf = [0u8; 8192];
        let mut recent = String::new();
        let mut failed_once = false;
        loop {
            match reader.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    let text = String::from_utf8_lossy(&buf[..n]).to_string();
                    let _ = app2.emit("terminal:data", serde_json::json!({ "data": text }));
                    // 追加到环形缓冲
                    {
                        let mut g = inner2.lock().unwrap();
                        g.term_buffer.push_str(&text);
                        truncate_term_buffer(&mut g.term_buffer);
                    }
                    if failed_once {
                        continue;
                    }
                    recent.push_str(&text);
                    if recent.len() > 8192 {
                        recent = recent[recent.len() - 4096..].to_string();
                    }
                    let lower = recent.to_lowercase();
                    if let Some(p) = FAIL_PATTERNS.iter().find(|p| lower.contains(**p)) {
                        failed_once = true;
                        if inner2.lock().unwrap().gen == gen {
                            eprintln!("[lantai-shell] failure pattern in output: {p}");
                            inner2.lock().unwrap().probe_stop.store(true, Ordering::Relaxed);
                            set_phase(
                                &app2,
                                &inner2,
                                Phase::Failed,
                                Some(format!("启动失败（终端输出含 \"{p}\"），详见终端")),
                            );
                        }
                        // 继续读取，终端保持可交互查看
                    }
                }
                Err(_) => break,
            }
        }
        let _ = app2.emit("terminal:exit", serde_json::json!({ "code": null }));
    });
}

fn start_probe(app: AppHandle, inner: Arc<Mutex<AppInner>>) {
    std::thread::spawn(move || {
        let (port, timeout, gen) = {
            let g = inner.lock().unwrap();
            (g.settings.port, g.ready_timeout, g.gen)
        };
        let deadline = Instant::now() + Duration::from_secs(timeout);
        loop {
            // 一次锁内读取 stop 与 gen，避免 TOCTOU
            let (stop, stale) = {
                let g = inner.lock().unwrap();
                (g.probe_stop.clone(), g.gen != gen)
            };
            if stop.load(Ordering::Relaxed) || stale {
                return;
            }
            if http_ok(port) {
                if inner.lock().unwrap().gen != gen {
                    return;
                }
                eprintln!("[lantai-shell] ready (probe ok)");
                inner.lock().unwrap().restart_count = 0;
                set_phase(&app, &inner, Phase::Ready, None);
                start_keepalive(&app, inner);
                return;
            }
            // 进程提前退出 → 快速失败（如启动命令即报错）
            if !child_alive(&inner) {
                eprintln!("[lantai-shell] child exited during boot");
                set_phase(
                    &app,
                    &inner,
                    Phase::Failed,
                    Some("启动失败：服务进程已退出".into()),
                );
                return;
            }
            if Instant::now() >= deadline {
                let alive = child_alive(&inner);
                set_phase(
                    &app,
                    &inner,
                    Phase::Failed,
                    Some(if !alive {
                        "启动失败：服务进程已退出".into()
                    } else {
                        format!("启动超时（{timeout}s）：端口 {port} 未就绪")
                    }),
                );
                return;
            }
            std::thread::sleep(Duration::from_millis(500));
        }
    });
}

fn start_keepalive(app: &AppHandle, inner: Arc<Mutex<AppInner>>) {
    let app = app.clone();
    std::thread::spawn(move || {
        let port = { inner.lock().unwrap().settings.port };
        let gen = { inner.lock().unwrap().gen };
        let mut fails = 0u32;
        loop {
            std::thread::sleep(Duration::from_secs(2));
            // 退出语义：restart() 会置 probe_stop=true 并 gen+=1，
            // 这里一次锁内读两者；任一命中即退，双保险覆盖重启竞态窗口
            let (stop, stale) = {
                let g = inner.lock().unwrap();
                (g.probe_stop.clone(), g.gen != gen)
            };
            if stop.load(Ordering::Relaxed) || stale {
                return;
            }
            if port_listening(port) {
                fails = 0;
                continue;
            }
            fails += 1;
            if !child_alive(&inner) {
                eprintln!("[lantai-shell] keepalive: child exited");
                fail_or_restart(&app, &inner, "服务进程已退出");
                return;
            }
            if fails >= 3 {
                eprintln!("[lantai-shell] keepalive: no response");
                fail_or_restart(&app, &inner, "服务无响应");
                return;
            }
        }
    });
}

fn child_alive(inner: &Arc<Mutex<AppInner>>) -> bool {
    let mut g = inner.lock().unwrap();
    match g.term.as_mut() {
        Some(t) => t.alive(),
        None => false,
    }
}

// ---------- 重启 ----------

/// 失败处理：auto_restart 开启且未超上限 → 自动重启；否则进入 Failed
fn fail_or_restart(app: &AppHandle, inner: &Arc<Mutex<AppInner>>, msg: &str) {
    let (auto, count) = {
        let g = inner.lock().unwrap();
        (g.settings.auto_restart, g.restart_count)
    };
    if auto && count < 3 {
        eprintln!("[lantai-shell] auto restart ({count}/3): {msg}");
        restart(app, inner);
    } else {
        set_phase(app, inner, Phase::Failed, Some(msg.into()));
    }
}

pub fn restart(app: &AppHandle, inner: &Arc<Mutex<AppInner>>) {
    {
        let mut g = inner.lock().unwrap();
        g.probe_stop.store(true, Ordering::Relaxed);
        g.gen += 1;
        g.restart_count += 1;
        if let Some(mut term) = g.term.take() {
            term.kill();
            // JobObject 句柄随 term drop 关闭 → 整树终止
        }
    }
    set_phase(app, inner, Phase::Boot, Some("正在重新启动…".into()));
    start_session(app, inner, true);
    start_probe(app.clone(), inner.clone());
}

// ---------- 手动停止 ----------

/// 停止服务（终端工具栏"停止"按钮）：
/// 1. 杀当前 cmd 会话进程树（JobObject 整树终止）
/// 2. 兜底：端口仍被监听（keep-alive 后台服务 / 外部进程）→ 按端口杀
/// 进入 Stopped 状态，可再点"重新启动"恢复。
pub fn stop(app: &AppHandle, inner: &Arc<Mutex<AppInner>>) -> Result<(), String> {
    let port = {
        let mut g = inner.lock().unwrap();
        g.probe_stop.store(true, Ordering::Relaxed);
        g.gen += 1;
        if let Some(mut term) = g.term.take() {
            term.kill();
            // JobObject 句柄随 term drop 关闭 → 整树终止
        }
        g.settings.port
    };
    // 当前会话树已杀；若端口仍被监听（detached keep-alive 服务），按端口杀
    let mut port_err: Option<String> = None;
    if port_listening(port) {
        if let Err(e) = kill_by_port(port) {
            port_err = Some(e);
        }
    }
    let msg = match &port_err {
        Some(e) => format!("服务已停止，但端口 {port} 仍被监听：{e}"),
        None => "服务已手动停止".into(),
    };
    set_phase(app, inner, Phase::Stopped, Some(msg.clone()));
    match port_err {
        Some(_) => Err(msg),
        None => Ok(()),
    }
}

// ---------- 退出 ----------

/// 主窗口关闭：勾选"退出后保持服务运行"时询问用户是否同时结束后台服务。
pub fn handle_close(app: &AppHandle) {
    eprintln!("[lantai-shell] main window close requested");
    let keep_alive = app
        .state::<Arc<Mutex<AppInner>>>()
        .lock()
        .unwrap()
        .settings
        .keep_alive_on_exit;
    if !keep_alive {
        // 进程退出时 JobObject 自动清理 cmd 进程树
        return;
    }
    // 询问：保持运行（默认）还是同时结束后台服务
    if ask_end_service(app) {
        // 结束后台服务：detached 进程不在本客户端进程树内，按端口杀
        let port = { app.state::<Arc<Mutex<AppInner>>>().lock().unwrap().settings.port };
        if port_listening(port) {
            match kill_by_port(port) {
                Ok(()) => eprintln!("[lantai-shell] background service ended on close"),
                Err(e) => eprintln!("[lantai-shell] failed to end background service: {e}"),
            }
        }
        return;
    }
    // 保持后台运行：脱离作业，另起一个独立 cmd 会话
    let (cmdline, log_path) = {
        let state = app.state::<Arc<Mutex<AppInner>>>();
        let g = state.lock().unwrap();
        let settings = g.settings.clone();
        // 后台服务同样需要代理环境（下载/更新场景）
        apply_proxy_env(&settings);
        let workdir = resolve_workdir(&settings);
        // 便携模式日志放程序目录，否则 %APPDATA% 下
        let log = if g.config_dir.join("portable.marker").exists() {
            g.config_dir.join("lantai-service.log")
        } else {
            app.path()
                .app_log_dir()
                .map(|d| d.join("lantai-service.log"))
                .unwrap_or_else(|_| PathBuf::from("lantai-service.log"))
        };
        let cmd = format!(
            "cd /d \"{}\" && {} > \"{}\" 2>&1",
            workdir.to_string_lossy().replace('"', "\"\""),
            settings.startup_command,
            log.to_string_lossy().replace('"', "\"\"")
        );
        (cmd, log)
    };
    if let Some(dir) = log_path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    // 脱离作业的后台进程：cmd /c start "" /b cmd /c "<命令>"（不占用当前进程树）
    match std::process::Command::new("cmd")
        .args(["/c", "start", "\"\"", "/b", "cmd", "/c", &cmdline])
        .spawn()
    {
        Ok(_) => eprintln!("[lantai-shell] keep-alive service launched, log: {}", log_path.display()),
        Err(e) => {
            eprintln!("[lantai-shell] keep-alive launch failed: {e}");
            let _ = app.emit("keepalive:failed", serde_json::json!({ "error": e.to_string() }));
        }
    }
}

/// 关闭确认对话框：返回 true = 保持后台运行（默认按钮），false = 同时结束后台服务。
/// blocking_show 内部在独立线程运行原生对话框（rfd async），主线程等待回调，无死锁风险。
fn ask_end_service(app: &AppHandle) -> bool {
    use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
    app.dialog()
        .message(
            "已勾选“退出后保持服务运行”。\n\n是否在退出时同时结束后台服务进程？\n· 保持运行：下次启动直接连接现有服务\n· 结束服务：下次启动将重新启动服务",
        )
        .title("退出兰台")
        .kind(MessageDialogKind::Warning)
        .buttons(MessageDialogButtons::OkCancelCustom(
            "保持运行".into(),
            "结束服务".into(),
        ))
        .blocking_show()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn truncate_buffer_respects_utf8_boundaries() {
        // 多字节字符（"测" 3 字节）反复填充后截断，不得 panic 且输出为合法 UTF-8
        let mut buf = String::new();
        for _ in 0..40000 {
            buf.push_str("测试中文输出📦 ");
        }
        truncate_term_buffer(&mut buf);
        assert!(buf.len() <= TERM_BUFFER_MAX);
        assert!(std::str::from_utf8(buf.as_bytes()).is_ok());
    }

    #[test]
    fn truncate_buffer_keeps_small_buffers_untouched() {
        let mut buf = String::from("short");
        truncate_term_buffer(&mut buf);
        assert_eq!(buf, "short");
    }

    #[test]
    fn netstat_parse_finds_ipv4_and_ipv6_pids() {
        let out = "  TCP    127.0.0.1:3080    0.0.0.0:0    LISTENING    12345\r\n\
                    TCP    [::]:3080         [::]:0        LISTENING    12345\r\n\
                    TCP    127.0.0.1:30800   0.0.0.0:0     LISTENING    9999\r\n";
        let pids = parse_listening_pids(out, 3080);
        assert_eq!(pids, vec![12345], "IPv4/IPv6 同 PID 应去重，30800 不应误命中");
    }

    #[test]
    fn netstat_parse_no_match_or_garbage() {
        assert!(parse_listening_pids("", 3080).is_empty());
        assert!(parse_listening_pids("  TCP  ... no listening lines here", 3080).is_empty());
        // 乱码行（非 UTF-8 损失）不 panic、不产生 PID
        let garbage = "TCP\u{0}\u{FFFD}\u{FFFD} 127.0.0.1:3080 LISTENING \u{FFFD}";
        assert!(parse_listening_pids(garbage, 3080).is_empty());
    }

    #[test]
    fn netstat_parse_multi_pid_deduplicated() {
        let out = "  TCP    0.0.0.0:3080    0.0.0.0:0    LISTENING    111\r\n\
                    TCP    [::]:3080        [::]:0        LISTENING    222\r\n";
        let pids = parse_listening_pids(out, 3080);
        assert_eq!(pids, vec![111, 222]);
    }

    #[test]
    fn reg_proxy_enabled_parses_server() {
        let out = "\r\nHKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings\r\n    ProxyEnable    REG_DWORD    0x1\r\n    ProxyServer    REG_SZ    127.0.0.1:10808\r\n    ProxyOverride    REG_SZ    <local>\r\n";
        assert_eq!(
            parse_reg_proxy_output(out),
            Some("127.0.0.1:10808".into())
        );
    }

    #[test]
    fn reg_proxy_disabled_or_absent_returns_none() {
        // ProxyEnable=0 → 无代理
        let disabled = "    ProxyEnable    REG_DWORD    0x0\r\n    ProxyServer    REG_SZ    127.0.0.1:10808\r\n";
        assert_eq!(parse_reg_proxy_output(disabled), None);
        // 无 ProxyServer 行
        let no_server = "    ProxyEnable    REG_DWORD    0x1\r\n";
        assert_eq!(parse_reg_proxy_output(no_server), None);
        // 乱码/空输出
        assert_eq!(parse_reg_proxy_output(""), None);
        assert_eq!(parse_reg_proxy_output("\u{FFFD}\u{FFFD}"), None);
    }

    #[test]
    fn normalize_proxy_handles_bare_url_and_multi() {
        assert_eq!(normalize_proxy("127.0.0.1:10808"), Some("http://127.0.0.1:10808".into()));
        assert_eq!(normalize_proxy("http://127.0.0.1:10808"), Some("http://127.0.0.1:10808".into()));
        assert_eq!(normalize_proxy("socks5://127.0.0.1:1080"), Some("socks5://127.0.0.1:1080".into()));
        // 多协议串取 https/http 段
        assert_eq!(
            normalize_proxy("ftp=127.0.0.1:21;https=proxy.example:8443;http=proxy.example:8080"),
            Some("http://proxy.example:8443".into())
        );
        assert_eq!(normalize_proxy(""), None);
        assert_eq!(normalize_proxy("   "), None);
        assert_eq!(normalize_proxy("ftp=127.0.0.1:21"), None);
    }
}
