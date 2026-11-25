//! Re'memor 的 Mac App 外殼。
//!
//! - 啟動 App 內建的圖庫伺服器（PyInstaller 打包的 lumilib-server），等它就緒後在視窗中開啟介面。
//! - 關閉視窗時 App 留在選單列繼續執行（手機才能持續連線）；選單列「結束」才會停止伺服器。
//! - 已經有伺服器在執行（例如用命令列版本開的）就直接使用，不重複啟動。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[cfg(target_os = "macos")]
mod spotlight;

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

pub(crate) const PORT: u16 = 8766;
/// App 與內建伺服器的版本一致（Cargo.toml 與 lumilib/__init__.py 一起更新）
const APP_VERSION: &str = env!("CARGO_PKG_VERSION");
const USER_AGENT: &str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15 LumitakeApp/0.4";

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

/// 伺服器是否已在執行（確認回應確實來自 Re'memor）
fn server_alive() -> bool {
    http_get("/api/auth/status").map(|b| b.contains("\"authenticated\"")).unwrap_or(false)
}

/// 從 /api/server 的回應取出某個欄位的字串值
fn server_field(key: &str) -> Option<String> {
    let body = http_get("/api/server")?;
    let key = format!("\"{key}\":\"");
    let start = body.find(&key)? + key.len();
    let end = body[start..].find('"')? + start;
    Some(body[start..end].to_string())
}

/// 正在執行的 Re'memor 版本（舊版沒有回報版本時視為未知）
fn running_version() -> Option<String> {
    server_field("version")
}

/// App 內建的這一份 Re'memor 的建置代號（建置 App 時由 REMEMOR_BUILD 帶入；沒有時只比對版本號碼）
const APP_BUILD: Option<&str> = option_env!("REMEMOR_BUILD");

/// 正在執行的 Re'memor 是不是 App 內建的這一份：版本號碼相同不夠，介面重新建置過也要換
fn running_is_ours() -> bool {
    let version = running_version().unwrap_or_default();
    if version != APP_VERSION {
        return false;
    }
    match APP_BUILD {
        Some(build) if !build.is_empty() => server_field("build").as_deref() == Some(build),
        _ => true,
    }
}

/// 送一個 POST 給本機的 Re'memor（body 是 JSON），回傳整個回應（含標頭）
fn http_post(path: &str, json: &str) -> Option<String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], PORT));
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_millis(400)).ok()?;
    let _ = stream.set_read_timeout(Some(Duration::from_millis(3000)));
    let request = format!(
        "POST {path} HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{json}",
        json.len());
    stream.write_all(request.as_bytes()).ok()?;
    let mut body = String::new();
    let _ = stream.read_to_string(&mut body);
    Some(body)
}

/// 請正在執行的 Re'memor 自己結束（新版才有這個請求；舊版會回 404，改用找程序的方式）
fn ask_server_to_quit() -> bool {
    let Some(body) = http_post("/api/shutdown", "{}") else { return false };
    if !body.starts_with("HTTP/1.1 200") {
        return false;
    }
    let deadline = Instant::now() + Duration::from_secs(10);
    while server_alive() && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(200));
    }
    !server_alive()
}

/// 找出佔用連接埠的 Re'memor 程序（例如之前用終端機安裝的舊版）並請它結束
fn stop_other_server() -> bool {
    let Ok(out) = Command::new("/usr/sbin/lsof").args(["-nP", "-t", &format!("-iTCP:{PORT}"), "-sTCP:LISTEN"]).output() else {
        return false;
    };
    let mut stopped = false;
    for pid in String::from_utf8_lossy(&out.stdout).split_whitespace() {
        let Ok(pid_num) = pid.parse::<i32>() else { continue };
        let cmd = Command::new("/bin/ps").args(["-p", pid, "-o", "command="]).output();
        // App 內建的伺服器（lumilib-server）或用終端機啟動的（rememor serve）
        let is_library = cmd
            .map(|o| { let c = String::from_utf8_lossy(&o.stdout).to_lowercase(); c.contains("lumilib") || c.contains("rememor") })
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
                #[cfg(target_os = "macos")]
                {
                    spotlight::ready(&app); // 從 Spotlight 啟動時點的那一項，介面載入後打開
                    spotlight::start_sync_thread(); // 把硬碟與智慧資料夾放進 Spotlight（只在這台 Mac）
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

/// 背景工作的摘要（選單列用）：（第一個工作的說明, 百分比, 進行中與排隊的工作數）
fn job_summary() -> Option<(String, Option<u32>, usize)> {
    let raw = http_get("/api/jobs")?;
    let body = raw.split_once("\r\n\r\n").map(|(_, b)| b).unwrap_or(&raw);
    let v: serde_json::Value = serde_json::from_str(body).ok()?;
    let active = v["active"].as_array().cloned().unwrap_or_default();
    let queued = v["queued"].as_array().map(|q| q.len()).unwrap_or(0);
    let Some(job) = active.first() else { return Some((String::new(), None, queued)) };
    let label = job["label"].as_str().unwrap_or("工作");
    let message: String = job["message"].as_str().unwrap_or("").chars().take(36).collect();
    let (done, total) = (job["done"].as_f64().unwrap_or(0.0), job["total"].as_f64().unwrap_or(0.0));
    let percent = if total > 0.0 { Some(((done / total) * 100.0).clamp(0.0, 100.0) as u32) } else { None };
    let mut text = match percent { Some(p) => format!("{label} {p}%"), None => label.to_string() };
    if !message.is_empty() {
        text.push_str(&format!("：{message}"));
    }
    Some((text, percent, active.len() + queued))
}

/// 最重要的一則主動提醒（選單列用）：（文字, 共幾則）。只提醒、不動手
fn reminder_top() -> Option<(String, usize)> {
    let raw = http_get("/api/reminders?limit=3")?;
    let body = raw.split_once("\r\n\r\n").map(|(_, b)| b).unwrap_or(&raw);
    let v: serde_json::Value = serde_json::from_str(body).ok()?;
    let items = v["items"].as_array().cloned().unwrap_or_default();
    let first = items.first()?;
    let text: String = first["text"].as_str().unwrap_or("").chars().take(48).collect();
    Some((text, items.len()))
}

/// 在主視窗裡換到某一頁（網頁裡的路由會跟著 popstate 換頁）
fn open_page(app: &AppHandle, path: &str) {
    show_main(app);
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.eval(&format!(
            "history.pushState({{idx:(history.state&&history.state.idx||0)+1}},'','{path}');dispatchEvent(new PopStateEvent('popstate'))"));
    }
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    // 有工作時：選單列圖示旁顯示百分比，選單最上面是目前的工作與「停止」；沒有工作時只有圖示
    let status = MenuItem::with_id(app, "status", "目前沒有進行中的工作", false, None::<&str>)?;
    let activity = MenuItem::with_id(app, "activity", "查看掃描進度…", true, None::<&str>)?;
    let reminder = MenuItem::with_id(app, "reminder", "沒有新的提醒", false, None::<&str>)?;
    let stop = MenuItem::with_id(app, "stop", "停止所有工作", false, None::<&str>)?;
    let open = MenuItem::with_id(app, "open", "打開 Re'memor", true, None::<&str>)?;
    let browser = MenuItem::with_id(app, "browser", "在瀏覽器中開啟", true, None::<&str>)?;
    let autostart_enabled = app.autolaunch().is_enabled().unwrap_or(false);
    let autostart = CheckMenuItem::with_id(app, "autostart", "登入時自動啟動", true, autostart_enabled, None::<&str>)?;
    let about = MenuItem::with_id(app, "about", "關於 Re'memor", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "結束 Re'memor", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &status,
            &activity,
            &stop,
            &PredefinedMenuItem::separator(app)?,
            &reminder,
            &PredefinedMenuItem::separator(app)?,
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
    let tray = TrayIconBuilder::with_id("main")
        .icon(icon)
        .icon_as_template(true)
        .tooltip("Re'memor")
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(move |app, event| match event.id().as_ref() {
            "open" => show_main(app),
            "about" => open_page(app, "/settings/about"),
            "activity" => open_page(app, "/activity"),
            "reminder" => open_page(app, "/overview"),
            "stop" => {
                // 停止後下次可以從中斷的地方繼續（掃描、讀取文字、比對內容都會記錄進度）
                let _ = http_post("/api/jobs/stop", "{}");
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

    // 每兩秒看一次背景工作，有變化才更新選單列
    thread::spawn(move || {
        let mut last: Option<(String, Option<u32>, usize)> = None;
        let mut tick: u32 = 0;
        loop {
            thread::sleep(Duration::from_secs(2));
            // 提醒每半分鐘看一次就好
            if tick % 15 == 0 {
                match reminder_top() {
                    Some((text, n)) => {
                        let line = if n > 1 { format!("提醒：{text}（共 {n} 則）") } else { format!("提醒：{text}") };
                        let _ = reminder.set_text(line.as_str());
                        let _ = reminder.set_enabled(true);
                    }
                    None => {
                        let _ = reminder.set_text("沒有新的提醒");
                        let _ = reminder.set_enabled(false);
                    }
                }
            }
            tick = tick.wrapping_add(1);
            let now = job_summary().unwrap_or((String::new(), None, 0));
            if last.as_ref() == Some(&now) {
                continue;
            }
            let (text, percent, count) = &now;
            if *count == 0 {
                let _ = tray.set_title(None::<&str>);
                let _ = tray.set_tooltip(Some("Re'memor"));
                let _ = status.set_text("目前沒有進行中的工作");
                let _ = stop.set_enabled(false);
            } else {
                let title = percent.map(|p| format!("{p}%")).unwrap_or_else(|| "…".to_string());
                let more = if *count > 1 { format!("（還有 {} 個工作）", count - 1) } else { String::new() };
                let line = if text.is_empty() { format!("{count} 個工作排隊中") } else { format!("{text}{more}") };
                let _ = tray.set_title(Some(title.as_str()));
                let _ = tray.set_tooltip(Some(format!("Re'memor：{line}").as_str()));
                let _ = status.set_text(line.as_str());
                let _ = stop.set_enabled(true);
            }
            last = Some(now);
        }
    });
    Ok(())
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))
        .manage(Server(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            let fs_handle = handle.clone();
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Re'memor")
                .inner_size(1400.0, 900.0)
                .min_inner_size(380.0, 560.0)
                .user_agent(USER_AGENT)
                // 關掉外殼自己的「把檔案拖進視窗」處理：它會把所有拖放都攔下來，網頁裡的拖放（例如拖進「喜好項目」）就失效了。
                // Re'memor 沒有用到外殼的檔案拖放。
                .disable_drag_drop_handler()
                // 看圖的「全螢幕」按鈕：網頁要求前往 lumitake://fullscreen 時，改成切換視窗的系統全螢幕
                .on_navigation(move |url| {
                    if url.scheme() == "lumitake" {
                        if url.host_str() == Some("fullscreen") {
                            let h = fs_handle.clone();
                            thread::spawn(move || {
                                if let Some(w) = h.get_webview_window("main") {
                                    let on = w.is_fullscreen().unwrap_or(false);
                                    let _ = w.set_fullscreen(!on);
                                }
                            });
                        }
                        return false;
                    }
                    true
                });
            // macOS：紅綠燈按鈕疊在畫面左上角，和工具列同一列（介面手冊「Liquid Glass 使用規則」）
            // 拖曳視窗：介面在工具列與側邊欄頂端標了 data-tauri-drag-region，由 Tauri 內建的腳本處理
            // （capabilities/remote-ui.json 允許本機伺服器的頁面使用「拖曳」與「按兩下放大」）。
            // 紅綠燈放進浮動側邊欄的左上角，垂直置中對齊 52pt 高的工具列。
            #[cfg(target_os = "macos")]
            let window = window
                .title_bar_style(tauri::TitleBarStyle::Overlay)
                .hidden_title(true)
                .traffic_light_position(tauri::LogicalPosition::new(22.0, 26.0));
            window.build()?;
            #[cfg(target_os = "macos")]
            spotlight::install(&handle); // 點 Spotlight 的結果：打開 Re'memor 跳到那一頁

            let starter = handle.clone();
            thread::spawn(move || {
                let mut need_start = !server_alive();
                if !need_start {
                    // 已有圖庫服務：版本不同（例如之前用終端機安裝的舊版）就換成 App 內建的新版
                    // （版本號碼相同但建置不同，例如更新後舊的還在跑，也一樣換掉）
                    let version = running_version().unwrap_or_default();
                    if !running_is_ours() {
                        thread::sleep(Duration::from_millis(400));
                        set_message(&starter, &format!("正在關閉舊版圖庫服務（{}），改用 {}…",
                            if version.is_empty() { "版本不明" } else { &version }, APP_VERSION));
                        if ask_server_to_quit() || stop_other_server() {
                            need_start = true;
                        } else {
                            show_error(&starter, &format!(
                                "有另一個 Re'memor（{}）正在使用連接埠 {PORT}，無法自動關閉。請關閉之前開啟的終端機視窗後重新打開 App。",
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
        .expect("無法啟動 Re'memor");

    app.run(|app, event| match event {
        #[cfg(target_os = "macos")]
        RunEvent::Reopen { .. } => show_main(app),
        RunEvent::Exit => stop_server(app),
        _ => {}
    });
}
