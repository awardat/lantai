//! WebView2 下载支持：处理 DownloadStarting（设置保存路径）与完成通知。
//!
//! 背景：wry 默认下载 handler 只放行不设路径，WebView2 无内置"另存为"UI，
//! ResultFilePath 为空时下载被取消（表现：点击导出无反应）。
//! 这里在主窗口 webview 上挂标准 WebView2 下载事件：
//! 下载 → 存到 %USERPROFILE%\Downloads + 服务端建议文件名 → 完成/失败事件通知前端。

use std::path::PathBuf;
use tauri::{AppHandle, Emitter, WebviewWindow};
use webview2_com::{
    DownloadStartingEventHandler, PermissionRequestedEventHandler, StateChangedEventHandler,
    Microsoft::Web::WebView2::Win32::{
        ICoreWebView2_4, ICoreWebView2_8, COREWEBVIEW2_DOWNLOAD_STATE_COMPLETED,
        COREWEBVIEW2_DOWNLOAD_STATE_IN_PROGRESS,
        COREWEBVIEW2_PERMISSION_KIND_MULTIPLE_AUTOMATIC_DOWNLOADS,
        COREWEBVIEW2_PERMISSION_STATE_ALLOW,
    },
};
use windows_core::{Interface, PWSTR};

/// 默认下载目录：%USERPROFILE%\Downloads（不存在则退回用户主目录）
fn download_dir() -> PathBuf {
    if let Ok(home) = std::env::var("USERPROFILE") {
        let dl = PathBuf::from(&home).join("Downloads");
        if dl.is_dir() {
            return dl;
        }
        return PathBuf::from(home);
    }
    PathBuf::from("C:\\")
}

fn pwstr_to_string(pw: PWSTR) -> String {
    // 安全：WebView2 回调传出的 PWSTR 指向事件参数内部缓冲区，事件参数在回调
    // 返回前保持有效；to_string 复制内容，不保留指针。
    unsafe { pw.to_string() }.unwrap_or_default()
}

/// 从 Content-Disposition 头解析文件名（纯函数，可单测）。
/// 支持 `filename="x"`、无引号 `filename=x`、RFC 5987 `filename*=UTF-8''x`。
fn parse_disposition_filename(cd: &str) -> Option<String> {
    // filename*=UTF-8''<pct-encoded>
    if let Some(i) = cd.find("filename*=") {
        let rest = cd[i + "filename*=".len()..].trim();
        let value = rest.split(';').next().unwrap_or("");
        let encoded = value.split("''").nth(1).unwrap_or("");
        if !encoded.is_empty() {
            let decoded = percent_decode(encoded);
            if !decoded.is_empty() {
                return Some(decoded);
            }
        }
    }
    // filename="x" 或 filename=x
    if let Some(i) = cd.find("filename=") {
        let rest = cd[i + "filename=".len()..].trim();
        if let Some(stripped) = rest.strip_prefix('"') {
            let name = stripped.split('"').next().unwrap_or("").trim();
            if !name.is_empty() {
                return Some(name.to_string());
            }
        } else {
            let name = rest.split(';').next().unwrap_or("").trim().to_string();
            if !name.is_empty() {
                return Some(name);
            }
        }
    }
    None
}

/// 极简百分号解码（RFC 5987 文件名），非 %XX 字符原样保留。
fn percent_decode(input: &str) -> String {
    let bytes = input.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let hex = std::str::from_utf8(&bytes[i + 1..i + 3]).unwrap_or("");
            if let Ok(v) = u8::from_str_radix(hex, 16) {
                out.push(v);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// 从 Content-Disposition + URL 解析下载文件名；
/// 兜底从 URL 的 sessionId 生成 dsh 命名；再兜底时间戳。
fn resolve_filename(
    operation: &webview2_com::Microsoft::Web::WebView2::Win32::ICoreWebView2DownloadOperation,
    url: &str,
) -> String {
    // 1) Content-Disposition 的 filename
    let mut pw = PWSTR::null();
    if unsafe { operation.ContentDisposition(&mut pw) }.is_ok() {
        let cd = pwstr_to_string(pw);
        if let Some(name) = parse_disposition_filename(&cd) {
            return sanitize_filename(&name);
        }
    }
    // 2) query 里的 sessionId（dsh 导出约定命名）
    if let Some(i) = url.find("sessionId=") {
        let rest = &url[i + "sessionId=".len()..];
        let id: String = rest
            .chars()
            .take_while(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
            .collect();
        if !id.is_empty() {
            return format!("dsh-session-{id}.zip");
        }
    }
    // 3) 兜底
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("download-{ts}.zip")
}

/// S-M7 修复：净化下载文件名——仅保留最后一段（file_name），剥离路径分隔符与 `..`，
/// 防止 Content-Disposition 的绝对路径/`..\` 越界写盘（PathBuf::join 遇绝对路径会整体替换基路径）。
fn sanitize_filename(name: &str) -> String {
    use std::path::Path;
    let cleaned = Path::new(name).file_name()
        .and_then(|s| s.to_str())
        .filter(|s| !s.is_empty() && *s != "." && *s != "..")
        .unwrap_or("download");
    // 剥离剩余的路径分隔符（file_name 理论上不含，但 percent_decode 后可能残留）
    cleaned
        .chars()
        .filter(|c| *c != '/' && *c != '\\' && *c != ':')
        .collect()
}

/// 挂载下载事件。token 不保存（进程生命周期内有效，无需注销）。
pub fn setup(app: &AppHandle, main: &WebviewWindow) {
    let app = app.clone();
    let _ = main.as_ref().with_webview(move |platform| {
        let controller = platform.controller();
        // 安全：controller 由 tauri/wry 持有并在 webview 生命周期内有效；
        // CoreWebView2 返回的接口引用计数由 windows-core 管理，闭包持 handle 不持指针。
        let Ok(core) = (unsafe { controller.CoreWebView2() }) else {
            eprintln!("[lantai-shell] download: no ICoreWebView2");
            return;
        };
        let Ok(wv4) = core.cast::<ICoreWebView2_4>() else {
            eprintln!("[lantai-shell] download: no ICoreWebView2_4");
            return;
        };

        // 自动允许"下载多个文件"权限（否则 WebView2 弹 edge://permission-request-dialog）
        if let Ok(wv8) = core.cast::<ICoreWebView2_8>() {
            let handle_perm = app.clone();
            let perm_handler = PermissionRequestedEventHandler::create(Box::new(move |_, args| {
                let Some(args) = args else {
                    return Ok(());
                };
                // 安全：事件参数指针由 WebView2 在回调期间保证有效
                let mut kind = webview2_com::Microsoft::Web::WebView2::Win32::COREWEBVIEW2_PERMISSION_KIND(
                    0,
                );
                let _ = unsafe { args.PermissionKind(&mut kind) };
                if kind == COREWEBVIEW2_PERMISSION_KIND_MULTIPLE_AUTOMATIC_DOWNLOADS {
                    let _ = unsafe { args.SetState(COREWEBVIEW2_PERMISSION_STATE_ALLOW) };
                }
                let _ = handle_perm;
                Ok(())
            }));
            let mut token: i64 = 0;
            let _ = unsafe { wv8.add_PermissionRequested(&perm_handler, &mut token) };
        }

        // 下载起始：确定文件名/路径、挂完成通知、放行
        let handle = app.clone();
        let handler = DownloadStartingEventHandler::create(Box::new(move |_, args| {
            let Some(args) = args else {
                return Ok(());
            };
            // 安全：事件参数与下载操作对象在回调期间由 WebView2 保证有效；
            // 闭包捕获的 app handle / path 均为自有数据，不持有 COM 指针跨回调
            let operation = unsafe { args.DownloadOperation() }?;
            let uri = {
                let mut pw = PWSTR::null();
                let _ = unsafe { operation.Uri(&mut pw) };
                pwstr_to_string(pw)
            };
            let name = resolve_filename(&operation, &uri);
            let path = download_dir().join(&name);

            // 完成通知（StateChanged：离开 IN_PROGRESS 即终态）
            let handle_done = handle.clone();
            let path_done = path.clone();
            let state_changed = StateChangedEventHandler::create(Box::new(move |op, _| {
                let Some(op) = op else {
                    return Ok(());
                };
                // 安全：同上，事件参数在回调期间有效
                let mut state =
                    webview2_com::Microsoft::Web::WebView2::Win32::COREWEBVIEW2_DOWNLOAD_STATE(0);
                let _ = unsafe { op.State(&mut state) };
                if state != COREWEBVIEW2_DOWNLOAD_STATE_IN_PROGRESS {
                    let ok = state == COREWEBVIEW2_DOWNLOAD_STATE_COMPLETED;
                    let _ = handle_done.emit(
                        "download:completed",
                        serde_json::json!({ "path": path_done.to_string_lossy(), "ok": ok }),
                    );
                }
                Ok(())
            }));
            let mut token: i64 = 0;
            let _ = unsafe { operation.add_StateChanged(&state_changed, &mut token) };

            // 设置保存路径并放行
            let hstr = windows_core::HSTRING::from(path.to_string_lossy().to_string());
            unsafe { args.SetResultFilePath(&hstr) }?;
            unsafe { args.SetHandled(true) }?;
            let _ = handle.emit(
                "download:starting",
                serde_json::json!({ "path": path.to_string_lossy(), "name": name }),
            );
            Ok(())
        }));
        let mut token: i64 = 0;
        let _ = unsafe { wv4.add_DownloadStarting(&handler, &mut token) };
        eprintln!("[lantai-shell] download handler installed");
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn disposition_quoted_filename() {
        assert_eq!(
            parse_disposition_filename(r#"attachment; filename="dsh-session-a.zip""#).as_deref(),
            Some("dsh-session-a.zip")
        );
    }

    #[test]
    fn disposition_unquoted_filename() {
        assert_eq!(
            parse_disposition_filename("attachment; filename=report.zip").as_deref(),
            Some("report.zip")
        );
    }

    #[test]
    fn disposition_rfc5987_utf8_filename() {
        assert_eq!(
            parse_disposition_filename("attachment; filename*=UTF-8''%E6%B5%8B%E8%AF%95.zip")
                .as_deref(),
            Some("测试.zip")
        );
    }

    #[test]
    fn disposition_missing_returns_none() {
        assert_eq!(parse_disposition_filename("attachment"), None);
    }

    #[test]
    fn percent_decode_basic() {
        assert_eq!(percent_decode("%E6%B5%8B"), "测");
        assert_eq!(percent_decode("a%2Fb"), "a/b");
        assert_eq!(percent_decode("plain"), "plain");
    }

    #[test]
    fn sanitize_filename_strips_absolute_path() {
        // S-M7：绝对路径仅保留文件名，防止 join 整体替换基路径
        assert_eq!(sanitize_filename("C:\\Users\\x\\evil.exe"), "evil.exe");
        assert_eq!(sanitize_filename("/etc/passwd"), "passwd");
    }

    #[test]
    fn sanitize_filename_strips_traversal() {
        // `..\` 相对穿越仅保留最后一段
        assert_eq!(sanitize_filename("..\\..\\evil.txt"), "evil.txt");
        assert_eq!(sanitize_filename("../../evil.txt"), "evil.txt");
    }

    #[test]
    fn sanitize_filename_preserves_normal_name() {
        assert_eq!(sanitize_filename("dsh-session-a.zip"), "dsh-session-a.zip");
        assert_eq!(sanitize_filename("测试.zip"), "测试.zip");
    }

    #[test]
    fn sanitize_filename_handles_dot_only() {
        assert_eq!(sanitize_filename("."), "download");
        assert_eq!(sanitize_filename(".."), "download");
        assert_eq!(sanitize_filename(""), "download");
    }
}
