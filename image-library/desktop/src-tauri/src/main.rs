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
const USER_AGENT: &str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15 LumitakeApp/0.3";

struct Server(Mutex<Option<Child>>);

fn library_url() -> String {
    format!("http://127.0.0.1:{PORT}/")
}

/// 伺服器是否已在執行（確認回應確實來自 Lumitake Library）
fn server_alive() -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], PORT));
    let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_millis(400)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(1500)));
    let request = format!(
        "GET /api/auth/status HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut body = String::new();
    let _ = stream.read_to_string(&mut body);
    body.contains("\"authenticated\"")
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
    let quit = MenuItem::with_id(app, "quit", "結束 Lumitake Library", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &open,
            &browser,
            &PredefinedMenuItem::separator(app)?,
            &autostart,
            &PredefinedMenuItem::separator(app)?,
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
                .min_inner_size(900.0, 600.0)
                .user_agent(USER_AGENT)
                .build()?;

            if !server_alive() {
                match spawn_server(&handle) {
                    Ok(child) => {
                        *handle.state::<Server>().0.lock().unwrap() = Some(child);
                    }
                    Err(message) => show_error(&handle, &message),
                }
            }
            open_when_ready(handle.clone());
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
