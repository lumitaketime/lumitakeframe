//! Lumitake Library 的 Mac App 外殼。
//!
//! - 啟動 App 內建的圖庫伺服器（PyInstaller 打包的 lumilib-server），等它就緒後在視窗中開啟介面。
//! - 關閉視窗時 App 留在選單列繼續執行（手機才能持續連線）；選單列「結束」才會停止伺服器。
//! - 已經有伺服器在執行（例如用命令列版本開的）就直接使用，不重複啟動。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

const PORT: u16 = 8765;
/// App 與內建伺服器的版本一致（Cargo.toml 與 lumilib/__init__.py 一起更新）
const APP_VERSION: &str = env!("CARGO_PKG_VERSION");
const USER_AGENT: &str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15 LumitakeApp/0.3";

struct Server(Mutex<Option<Child>>);

fn library_url() -> String {
    format!("http://127.0.0.1:{PORT}/")
}

fn http_get(path: &str) -> Option<String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], PORT));
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_millis(400)).ok()?;
    let _ = stream.set_read_timeout(Some(Duration::from_millis(3000)));
    let request = format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nConnection: close\r\n\r\n");
    stream.write_all(request.as_bytes()).ok()?;
    let mut body = String::new();
    let _ = stream.read_to_string(&mut body);
    Some(body)
}

/// 伺服器是否已在執行（確認回應確實來自 Lumitake Library）
fn server_alive() -> bool {
    http_get("/api/auth/status").map(|b| b.contains("\"authenticated\"")).unwrap_or(false)
}

/// 正在執行的 Lumitake Library 版本（舊版沒有回報版本時視為未知）
fn running_version() -> Option<String> {
    let body = http_get("/api/server")?;
    let key = "\"version\":\"";
    let start = body.find(key)? + key.len();
    let end = body[start..].find('"')? + start;
    Some(body[start..end].to_string())
}

/// 找出佔用連接埠的 Lumitake Library 程序（例如之前用終端機安裝的舊版）並請它結束
fn stop_other_server() -> bool {
    let Ok(out) = Command::new("/usr/sbin/lsof").args(["-nP", "-t", &format!("-iTCP:{PORT}"), "-sTCP:LISTEN"]).output() else {
        return false;
    };
    let mut stopped = false;
    for pid in String::from_utf8_lossy(&out.stdout).split_whitespace() {
        let Ok(pid_num) = pid.parse::<i32>() else { continue };
        let cmd = Command::new("/bin/ps").args(["-p", pid, "-o", "command="]).output();
        let is_library = cmd
            .map(|o| String::from_utf8_lossy(&o.stdout).contains("lumilib"))
            .unwrap_or(false);
        if is_library {
            unsafe {
                libc::kill(pid_num, libc::SIGTERM);
            }
            stopped = true;
        }
    }
    if stopped {
        let deadline = Instant::now() + Duration::from_secs(10);
        while server_alive() && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(200));
        }
    }
    stopped && !server_alive()
}

fn set_message(app: &AppHandle, message: &str) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.eval(&format!(
            "document.getElementById('msg') && (document.getElementById('msg').textContent = {})",
            serde_json_string(message)
        ));
    }
}

fn spawn_server(app: &AppHandle) -> Result<Child, String> {
    let resources = app.path().resource_dir().map_err(|e| e.to_string())?;
    let server_dir = resources.join("server");
    let exe = server_dir.join("lumilib-server");
    if !exe.exists() {
        return Err(format!("找不到內建伺服器：{}", exe.display()));
    }
    let log_dir = app.path().app_log_dir().map_err(|e| e.to_string())?;
    let _ = fs::create_dir_all(&log_dir);
    let log = fs::File::create(log_dir.join("server.log")).map_err(|e| e.to_string())?;
    let log_err = log.try_clone().map_err(|e| e.to_string())?;

    // 從 Finder 開啟的 App 沒有 Homebrew 的 PATH，補上常見位置（Ollama 等）
    let path = std::env::var("PATH").unwrap_or_default();
    let path = format!("/opt/homebrew/bin:/usr/local/bin:{path}");

    Command::new(&exe)
        .args(["serve", "--port", &PORT.to_string()])
        .current_dir(&server_dir)
        .env("PATH", path)
        .env("LUMILIB_TOOLS", server_dir.join("tools"))
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(log_err))
        .spawn()
        .map_err(|e| format!("無法啟動伺服器：{e}"))
}

fn stop_server(app: &AppHandle) {
    let state = app.state::<Server>();
    let mut guard = state.0.lock().unwrap();
    if let Some(mut child) = guard.take() {
        // 先請它正常結束（讓資料庫寫完），三秒後仍在就強制結束
        unsafe {
            libc::kill(child.id() as i32, libc::SIGTERM);
        }
        let deadline = Instant::now() + Duration::from_secs(3);
        while Instant::now() < deadline {
            if let Ok(Some(_)) = child.try_wait() {
                return;
            }
            thread::sleep(Duration::from_millis(100));
        }
        let _ = child.kill();
    }
}

fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn show_error(app: &AppHandle, message: &str) {
    if let Some(window) = app.get_webview_window("main") {
        let log = app
            .path()
            .app_log_dir()
            .map(|p| p.join("server.log").display().to_string())
            .unwrap_or_default();
        let script = format!(
            "window.showError && window.showError({}, {})",
            serde_json_string(message),
            serde_json_string(&log)
        );
        let _ = window.eval(&script);
    }
}

fn serde_json_string(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// 等伺服器就緒後把視窗導向圖庫介面
fn open_when_ready(app: AppHandle) {
    thread::spawn(move || {
        let started = Instant::now();
        loop {
            if server_alive() {
                if let Some(window) = app.get_webview_window("main") {
                    if let Ok(url) = Url::parse(&library_url()) {
                        let _ = window.navigate(url);
                    }
                }
                return;
            }
            let exited = {
                let state = app.state::<Server>();
                let mut guard = state.0.lock().unwrap();
                match guard.as_mut() {
                    Some(child) => matches!(child.try_wait(), Ok(Some(_))),
                    None => false,
                }
            };
            if exited {
                show_error(&app, "圖庫伺服器啟動失敗。");
                return;
            }
            if started.elapsed() > Duration::from_secs(120) {
                show_error(&app, "等待圖庫伺服器逾時。");
                return;
            }
            thread::sleep(Duration::from_millis(400));
        }
    });
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "打開 Lumitake Library", true, None::<&str>)?;
    let browser = MenuItem::with_id(app, "browser", "在瀏覽器中開啟", true, None::<&str>)?;
    let autostart_enabled = app.autolaunch().is_enabled().unwrap_or(false);
    let autostart = CheckMenuItem::with_id(app, "autostart", "登入時自動啟動", true, autostart_enabled, None::<&str>)?;
    let about = MenuItem::with_id(app, "about", "關於 Lumitake Library", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "結束 Lumitake Library", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &open,
            &browser,
            &PredefinedMenuItem::separator(app)?,
            &autostart,
            &PredefinedMenuItem::separator(app)?,
            &about,
            &quit,
        ],
    )?;
    let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/tray.png"))?;
    let autostart_item = autostart.clone();
    TrayIconBuilder::with_id("main")
        .icon(icon)
        .icon_as_template(true)
        .tooltip("Lumitake Library")
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(move |app, event| match event.id().as_ref() {
            "open" => show_main(app),
            "about" => {
                show_main(app);
                if let Some(window) = app.get_webview_window("main") {
                    // 網頁裡的路由會跟著 popstate 換頁
                    let _ = window.eval(
                        "history.pushState({idx:(history.state&&history.state.idx||0)+1},'','/settings/about');dispatchEvent(new PopStateEvent('popstate'))",
                    );
                }
            }
            "browser" => {
                let _ = Command::new("open").arg(library_url()).spawn();
            }
            "autostart" => {
                let launcher = app.autolaunch();
                let enabled = launcher.is_enabled().unwrap_or(false);
                let _ = if enabled { launcher.disable() } else { launcher.enable() };
                let _ = autostart_item.set_checked(launcher.is_enabled().unwrap_or(false));
            }
            "quit" => {
                stop_server(app);
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;
    Ok(())
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))
        .manage(Server(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Lumitake Library")
                .inner_size(1400.0, 900.0)
                .min_inner_size(380.0, 560.0)
                .user_agent(USER_AGENT)
                .build()?;

            let starter = handle.clone();
            thread::spawn(move || {
                let mut need_start = !server_alive();
                if !need_start {
                    // 已有圖庫服務：版本不同（例如之前用終端機安裝的舊版）就換成 App 內建的新版
                    let version = running_version().unwrap_or_default();
                    if version != APP_VERSION {
                        thread::sleep(Duration::from_millis(400));
                        set_message(&starter, &format!("正在關閉舊版圖庫服務（{}），改用 {}…",
                            if version.is_empty() { "版本不明" } else { &version }, APP_VERSION));
                        if stop_other_server() {
                            need_start = true;
                        } else {
                            show_error(&starter, &format!(
                                "有另一個 Lumitake Library（{}）正在使用連接埠 {PORT}，無法自動關閉。請關閉之前開啟的終端機視窗後重新打開 App。",
                                if version.is_empty() { "舊版" } else { &version }));
                            return;
                        }
                    }
                }
                if need_start {
                    match spawn_server(&starter) {
                        Ok(child) => {
                            *starter.state::<Server>().0.lock().unwrap() = Some(child);
                        }
                        Err(message) => {
                            show_error(&starter, &message);
                            return;
                        }
                    }
                }
                open_when_ready(starter.clone());
            });
            build_tray(&handle)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            // 關閉視窗只是隱藏，App 留在選單列繼續提供服務
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("無法啟動 Lumitake Library");

    app.run(|app, event| match event {
        #[cfg(target_os = "macos")]
        RunEvent::Reopen { .. } => show_main(app),
        RunEvent::Exit => stop_server(app),
        _ => {}
    });
}
