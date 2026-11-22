//! Spotlight（只在 macOS）：把 Re'memor 的重要項目放進 App 專用的 Spotlight 索引（Core Spotlight）。
//!
//! - 放什麼由引擎決定：每顆硬碟、智慧資料夾、目錄裡的所有資料夾與檔案（含文件的文字）。
//!   引擎記得哪些已經放過，每次只給「新增、改過、不在了的」（GET /api/spotlight/changes，分批），放好後回報（ack）。
//! - 索引只存在這台 Mac，不會上傳（核心原則二）。
//! - 點 Spotlight 的結果：macOS 會叫 App 的「繼續活動」（application:continueUserActivity:restorationHandler:）。
//!   Tauri 底下的 tao 只處理網頁連結，所以這裡在啟動時換掉那個方法：Spotlight 的項目自己處理（打開 Re'memor、
//!   跳到那一頁），其他的照舊交給原本的處理方式。
//! - 每一項的 id 就是「rememor:」加上 Re'memor 裡的頁面路徑，點下去直接照著打開，不用另外記對照表；
//!   App 還沒準備好（例如從 Spotlight 啟動）時先記著，介面載入後再打開。

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::ptr::NonNull;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex, OnceLock};
use std::thread;
use std::time::Duration;

use block2::RcBlock;
use objc2::rc::Retained;
use objc2::runtime::{AnyObject, Bool, Imp, Sel};
use objc2::{sel, AllocAnyThread, MainThreadMarker};
use objc2_app_kit::NSApplication;
use objc2_core_spotlight::{
    CSSearchQuery, CSSearchableIndex, CSSearchableItem, CSSearchableItemActionType, CSSearchableItemActivityIdentifier,
    CSSearchableItemAttributeSet,
};
use objc2_foundation::{NSArray, NSError, NSString, NSUserActivity};
use tauri::AppHandle;

const DOMAIN: &str = "com.lumitake.rememor.catalog";
const PREFIX: &str = "rememor:";

static APP: OnceLock<AppHandle> = OnceLock::new();
static PENDING: Mutex<Option<String>> = Mutex::new(None);
static READY: Mutex<bool> = Mutex::new(false);
static REPORTED: Mutex<bool> = Mutex::new(false); // 這次打開 App 之後回報過狀態了沒
static ORIG_CONTINUE: OnceLock<Imp> = OnceLock::new();
static ORIG_WILL_CONTINUE: OnceLock<Imp> = OnceLock::new();

type ContinueFn =
    unsafe extern "C-unwind" fn(*mut AnyObject, Sel, *mut AnyObject, *mut NSUserActivity, *mut AnyObject) -> Bool;
type WillContinueFn = unsafe extern "C-unwind" fn(*mut AnyObject, Sel, *mut AnyObject, *mut NSString) -> Bool;

/// Spotlight 的項目要打開哪一頁（不是 Spotlight 的活動就回傳 None）
unsafe fn spotlight_path(activity: *mut NSUserActivity) -> Option<String> {
    let activity = activity.as_ref()?;
    if !activity.activityType().isEqualToString(CSSearchableItemActionType) {
        return None;
    }
    let info = activity.userInfo()?;
    let key: &AnyObject = CSSearchableItemActivityIdentifier.as_ref();
    let value = info.objectForKey(key)?;
    let id = value.downcast::<NSString>().ok()?.to_string();
    let path = id.strip_prefix(PREFIX)?;
    // 只接受 Re'memor 自己的頁面路徑（也避免奇怪的字元進到網頁的 JavaScript）
    if !path.starts_with('/') || path.contains('\'') || path.contains('\\') || path.contains('\n') {
        return None;
    }
    Some(path.to_string())
}

fn open(path: String) {
    let ready = *READY.lock().unwrap();
    if !ready {
        *PENDING.lock().unwrap() = Some(path);
        return;
    }
    if let Some(app) = APP.get() {
        let app = app.clone();
        // 換到主執行緒以外再打開，避免卡住 macOS 的回呼
        thread::spawn(move || crate::open_page(&app, &path));
    }
}

unsafe extern "C-unwind" fn continue_activity(
    this: *mut AnyObject,
    cmd: Sel,
    app: *mut AnyObject,
    activity: *mut NSUserActivity,
    handler: *mut AnyObject,
) -> Bool {
    if let Some(path) = spotlight_path(activity) {
        open(path);
        return Bool::YES;
    }
    match ORIG_CONTINUE.get() {
        Some(orig) => {
            let f: ContinueFn = std::mem::transmute(*orig);
            f(this, cmd, app, activity, handler)
        }
        None => Bool::NO,
    }
}

unsafe extern "C-unwind" fn will_continue_activity(
    this: *mut AnyObject,
    cmd: Sel,
    app: *mut AnyObject,
    kind: *mut NSString,
) -> Bool {
    if let Some(kind) = kind.as_ref() {
        if kind.isEqualToString(CSSearchableItemActionType) {
            return Bool::YES;
        }
    }
    match ORIG_WILL_CONTINUE.get() {
        Some(orig) => {
            let f: WillContinueFn = std::mem::transmute(*orig);
            f(this, cmd, app, kind)
        }
        None => Bool::NO,
    }
}

/// 啟動時（主執行緒）呼叫一次：接手「點 Spotlight 的結果」。
pub fn install(app: &AppHandle) {
    let _ = APP.set(app.clone());
    let Some(mtm) = MainThreadMarker::new() else { return };
    let nsapp = NSApplication::sharedApplication(mtm);
    let Some(delegate) = nsapp.delegate() else { return };
    let object: &AnyObject = delegate.as_ref();
    let class = object.class();
    unsafe {
        if let Some(m) = class.instance_method(sel!(application:continueUserActivity:restorationHandler:)) {
            let imp: Imp = std::mem::transmute(continue_activity as ContinueFn);
            let _ = ORIG_CONTINUE.set(m.set_implementation(imp));
        }
        if let Some(m) = class.instance_method(sel!(application:willContinueUserActivityWithType:)) {
            let imp: Imp = std::mem::transmute(will_continue_activity as WillContinueFn);
            let _ = ORIG_WILL_CONTINUE.set(m.set_implementation(imp));
        }
    }
}

/// 介面載入好了：打開等著的頁面（例如從 Spotlight 啟動 App 時點的那一項）。
pub fn ready(app: &AppHandle) {
    *READY.lock().unwrap() = true;
    let pending = PENDING.lock().unwrap().take();
    if let Some(path) = pending {
        let app = app.clone();
        thread::spawn(move || {
            thread::sleep(Duration::from_millis(1500)); // 等網頁的路由準備好
            crate::open_page(&app, &path);
        });
    }
}

struct Item {
    entity: String,
    id: String,
    sig: String,
    title: String,
    description: String,
    keywords: Vec<String>,
    content_type: String,
    text: String,
}

fn parse_items(v: &serde_json::Value) -> Vec<Item> {
    v.as_array()
        .cloned()
        .unwrap_or_default()
        .iter()
        .filter_map(|it| {
            Some(Item {
                entity: it["entity"].as_str().unwrap_or("").to_string(),
                id: it["id"].as_str()?.to_string(),
                sig: it["sig"].as_str().unwrap_or("").to_string(),
                title: it["title"].as_str().unwrap_or("").to_string(),
                description: it["description"].as_str().unwrap_or("").to_string(),
                keywords: it["keywords"]
                    .as_array()
                    .map(|k| k.iter().filter_map(|x| x.as_str().map(String::from)).collect())
                    .unwrap_or_default(),
                content_type: it["type"].as_str().unwrap_or("public.item").to_string(),
                text: it["text"].as_str().unwrap_or("").to_string(),
            })
        })
        .collect()
}

/// 跟引擎要資料／回報（只連這台電腦上的 Re'memor）。
/// 一批裡有文件的文字時，引擎可能要好幾秒才回應，所以這裡最多等 5 分鐘（一般的 http_get 只等 3 秒，
/// 之前就是因為等不到就放棄，Spotlight 只放進去一點點）。
fn engine(method: &str, path: &str, json: &str) -> Result<serde_json::Value, String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], crate::PORT));
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_secs(2)).map_err(|e| format!("連不上 Re'memor：{e}"))?;
    let _ = stream.set_read_timeout(Some(Duration::from_secs(300)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(60)));
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{json}",
        crate::PORT,
        json.len()
    );
    stream.write_all(request.as_bytes()).map_err(|e| format!("送不出去：{e}"))?;
    let mut raw = Vec::new();
    stream.read_to_end(&mut raw).map_err(|e| format!("Re'memor 太久沒有回應：{e}"))?;
    let split = raw.windows(4).position(|w| w == b"\r\n\r\n").ok_or("Re'memor 的回應不完整")?;
    let head = String::from_utf8_lossy(&raw[..split]).to_ascii_lowercase();
    let mut body = raw[split + 4..].to_vec();
    if !head.starts_with("http/1.1 200") {
        return Err(format!("Re'memor 回應錯誤：{}", head.lines().next().unwrap_or("")));
    }
    if head.contains("transfer-encoding: chunked") {
        body = unchunk(&body);
    }
    serde_json::from_slice(&body).map_err(|e| format!("讀不懂 Re'memor 的回應：{e}"))
}

/// 把「分段傳送」的回應接回來
fn unchunk(mut data: &[u8]) -> Vec<u8> {
    let mut out = Vec::new();
    while let Some(end) = data.windows(2).position(|w| w == b"\r\n") {
        let size_text = String::from_utf8_lossy(&data[..end]);
        let size = usize::from_str_radix(size_text.split(';').next().unwrap_or("0").trim(), 16).unwrap_or(0);
        data = &data[end + 2..];
        if size == 0 || data.len() < size {
            break;
        }
        out.extend_from_slice(&data[..size]);
        data = &data[(size + 2).min(data.len())..];
    }
    out
}

/// 向引擎一批一批拿「有變動的項目」，放進 Spotlight（或拿掉），放好再告訴引擎。
/// 第一次會把目錄裡的所有資料夾與檔案放進去（可能要一段時間，設定頁會顯示進度）；之後只處理新增、改過、不在了的。
/// 放完會數一數 Spotlight 裡真的有幾項 Re'memor 的項目，結果顯示在設定頁。
pub fn sync() {
    if !unsafe { CSSearchableIndex::isIndexingAvailable() } {
        report(false, 0, "這台 Mac 的 Spotlight 目前不能讓 App 加入項目（可能 Spotlight 被關掉了）");
        return;
    }
    let mut cursor = String::new();
    let mut changed = false;
    let mut batches = 0usize;
    loop {
        let path = format!("/api/spotlight/changes?limit=200&cursor={}", cursor);
        let v = match engine("GET", &path, "") {
            Ok(v) => v,
            Err(message) => {
                report(false, 0, &format!("沒能從 Re'memor 拿到要放進 Spotlight 的項目：{message}"));
                return; // 下一分鐘再試
            }
        };
        if v["reset"].as_bool().unwrap_or(false) {
            if let Err(message) = unsafe { delete_domain() } {
                report(false, 0, &format!("清掉舊的項目時出錯：{message}"));
                return;
            }
            changed = true;
        }
        let items = parse_items(&v["upsert"]);
        let gone: Vec<(String, String)> = v["delete"]
            .as_array()
            .cloned()
            .unwrap_or_default()
            .iter()
            .filter_map(|d| Some((d["entity"].as_str().unwrap_or("").to_string(), d["id"].as_str()?.to_string())))
            .collect();
        if !items.is_empty() {
            if let Err(message) = unsafe { index_items(&items) } {
                report(false, 0, &message);
                return; // 下一分鐘再試（引擎沒收到「放好了」，會再送一次）
            }
            changed = true;
        }
        if !gone.is_empty() {
            let ids: Vec<String> = gone.iter().map(|(_, id)| id.clone()).collect();
            if let Err(message) = unsafe { delete_ids(&ids) } {
                report(false, 0, &format!("拿掉不在的項目時出錯：{message}"));
                return;
            }
            changed = true;
        }
        let mut synced = v["synced"].as_u64().unwrap_or(0) as usize;
        if !items.is_empty() || !gone.is_empty() {
            let done: Vec<serde_json::Value> = items
                .iter()
                .map(|it| serde_json::json!({ "entity": it.entity, "id": it.id, "sig": it.sig }))
                .collect();
            let deleted: Vec<&str> = gone.iter().filter(|(e, _)| !e.is_empty()).map(|(e, _)| e.as_str()).collect();
            let body = serde_json::json!({ "done": done, "deleted": deleted }).to_string();
            if let Err(message) = engine("POST", "/api/spotlight/ack", &body) {
                report(false, 0, &format!("沒能告訴 Re'memor 哪些已經放好：{message}"));
                return;
            }
            synced = synced + done.len() - deleted.len().min(synced + done.len());
            batches += 1;
            if batches % 5 == 0 {
                report_full(true, synced, "", None, true); // 第一次放很多時：設定頁看得到進度
            }
        }
        match v["cursor"].as_str() {
            Some(next) => cursor = next.to_string(),
            None => {
                let first = !*REPORTED.lock().unwrap();
                if changed || first {
                    *REPORTED.lock().unwrap() = true;
                    // 自我檢查：數一數 Spotlight 裡真的有幾項 Re'memor 的項目
                    let probe = if synced > 0 { Some(unsafe { probe() }) } else { None };
                    report_full(true, synced, "", probe, false);
                }
                return;
            }
        }
    }
}

/// 把結果告訴 Re'memor（設定頁顯示「放進 Spotlight 了沒、有沒有出錯」，方便本人知道狀況）
fn report(ok: bool, count: usize, error: &str) {
    report_full(ok, count, error, None, false);
}

/// probe：Some(Ok(Spotlight 裡有幾項)) 或 Some(Err(錯誤訊息))；None＝沒有檢查。running：還在放
fn report_full(ok: bool, count: usize, error: &str, probe: Option<Result<usize, String>>, running: bool) {
    let (found, probe_error) = match probe {
        Some(Ok(n)) => (serde_json::json!(n), String::new()),
        Some(Err(e)) => (serde_json::Value::Null, e),
        None => (serde_json::Value::Null, String::new()),
    };
    let body = serde_json::json!({ "ok": ok, "count": count, "error": error, "probe": found, "probe_error": probe_error, "running": running })
        .to_string();
    let _ = engine("POST", "/api/spotlight/report", &body);
}

/// 請 Spotlight 在 Re'memor 自己的索引裡把所有項目找一遍，數一數有幾項（最多等 60 秒）。
/// 這個數字和「放進去的項目數」差不多，就代表都進去了；Spotlight 視窗裡看不看得到、排第幾，是 macOS 決定的。
unsafe fn probe() -> Result<usize, String> {
    let query = CSSearchQuery::initWithQueryString_queryContext(
        CSSearchQuery::alloc(),
        &NSString::from_str("title == \"*\""),
        None,
    );
    let count = Arc::new(AtomicUsize::new(0));
    let (tx, rx) = mpsc::channel::<Option<String>>();
    let counter = count.clone();
    let found = RcBlock::new(move |items: NonNull<NSArray<CSSearchableItem>>| {
        counter.fetch_add(items.as_ref().count(), Ordering::Relaxed);
    });
    query.setFoundItemsHandler(Some(&found));
    let done = RcBlock::new(move |err: *mut NSError| {
        let _ = tx.send(describe(err));
    });
    query.setCompletionHandler(Some(&done));
    query.start();
    let out = match rx.recv_timeout(Duration::from_secs(60)) {
        Ok(None) => Ok(count.load(Ordering::Relaxed)),
        Ok(Some(message)) => Err(message),
        Err(_) => Ok(count.load(Ordering::Relaxed)), // 太多了數不完：回報目前數到的
    };
    query.cancel();
    out
}

unsafe fn describe(err: *mut NSError) -> Option<String> {
    let err = err.as_ref()?;
    Some(format!("{}（{} {}）", err.localizedDescription(), err.domain(), err.code()))
}

/// 等 Spotlight 做完（它的回呼在別的執行緒）：回傳錯誤訊息或成功
fn wait(rx: mpsc::Receiver<Option<String>>) -> Result<(), String> {
    match rx.recv_timeout(Duration::from_secs(120)) {
        Ok(None) => Ok(()),
        Ok(Some(message)) => Err(message),
        Err(_) => Err("Spotlight 太久沒有回應".into()),
    }
}

fn done_block(tx: mpsc::Sender<Option<String>>) -> RcBlock<dyn Fn(*mut NSError)> {
    RcBlock::new(move |err: *mut NSError| {
        let _ = tx.send(unsafe { describe(err) });
    })
}

unsafe fn delete_domain() -> Result<(), String> {
    let index = CSSearchableIndex::defaultSearchableIndex();
    let domains = NSArray::from_retained_slice(&[NSString::from_str(DOMAIN)]);
    let (tx, rx) = mpsc::channel();
    index.deleteSearchableItemsWithDomainIdentifiers_completionHandler(&domains, Some(&done_block(tx)));
    wait(rx)
}

unsafe fn delete_ids(ids: &[String]) -> Result<(), String> {
    let index = CSSearchableIndex::defaultSearchableIndex();
    let list: Vec<Retained<NSString>> = ids.iter().map(|i| NSString::from_str(i)).collect();
    let (tx, rx) = mpsc::channel();
    index.deleteSearchableItemsWithIdentifiers_completionHandler(&NSArray::from_retained_slice(&list), Some(&done_block(tx)));
    wait(rx)
}

/// 放進（或更新）一批項目：同一個 id 會蓋掉舊的
unsafe fn index_items(items: &[Item]) -> Result<(), String> {
    let index = CSSearchableIndex::defaultSearchableIndex();
    let domain = NSString::from_str(DOMAIN);
    let mut list: Vec<Retained<CSSearchableItem>> = Vec::with_capacity(items.len());
    for it in items {
        #[allow(deprecated)]
        let attrs = CSSearchableItemAttributeSet::initWithItemContentType(
            CSSearchableItemAttributeSet::alloc(),
            &NSString::from_str(&it.content_type),
        );
        attrs.setTitle(Some(&NSString::from_str(&it.title)));
        attrs.setDisplayName(Some(&NSString::from_str(&it.title)));
        attrs.setContentDescription(Some(&NSString::from_str(&it.description)));
        let words: Vec<Retained<NSString>> = it.keywords.iter().map(|k| NSString::from_str(k)).collect();
        attrs.setKeywords(Some(&NSArray::from_retained_slice(&words)));
        if !it.text.is_empty() {
            attrs.setTextContent(Some(&NSString::from_str(&it.text))); // 文件裡的文字：在 Spotlight 也搜得到
        }
        list.push(CSSearchableItem::initWithUniqueIdentifier_domainIdentifier_attributeSet(
            CSSearchableItem::alloc(),
            Some(&NSString::from_str(&it.id)),
            Some(&domain),
            &attrs,
        ));
    }
    let (tx, rx) = mpsc::channel();
    index.indexSearchableItems_completionHandler(&NSArray::from_retained_slice(&list), Some(&done_block(tx)));
    wait(rx)
}

/// 背景：一開始放一次，之後每分鐘看一下清單有沒有變（例如新增硬碟、改了智慧資料夾）。
pub fn start_sync_thread() {
    thread::spawn(|| loop {
        sync();
        thread::sleep(Duration::from_secs(60));
    });
}
