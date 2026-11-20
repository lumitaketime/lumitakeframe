//! Spotlight（只在 macOS）：把 Re'memor 的重要項目放進 App 專用的 Spotlight 索引（Core Spotlight）。
//!
//! - 放什麼由引擎決定：每顆硬碟、智慧資料夾、外接硬碟上的所有資料夾與檔案（含文件開頭的文字）。
//!   引擎記得哪些已經放過，每次只給「新增、改過、不在了的」（GET /api/spotlight/changes，分批），放好後回報（ack）。
//! - 索引只存在這台 Mac，不會上傳（核心原則二）。
//! - 點 Spotlight 的結果：macOS 會叫 App 的「繼續活動」（application:continueUserActivity:restorationHandler:）。
//!   Tauri 底下的 tao 只處理網頁連結，所以這裡在啟動時換掉那個方法：Spotlight 的項目自己處理（打開 Re'memor、
//!   跳到那一頁），其他的照舊交給原本的處理方式。
//! - 每一項的 id 就是「rememor:」加上 Re'memor 裡的頁面路徑，點下去直接照著打開，不用另外記對照表；
//!   App 還沒準備好（例如從 Spotlight 啟動）時先記著，介面載入後再打開。

use std::sync::{mpsc, Mutex, OnceLock};
use std::thread;
use std::time::Duration;

use block2::RcBlock;
use objc2::rc::Retained;
use objc2::runtime::{AnyObject, Bool, Imp, Sel};
use objc2::{sel, AllocAnyThread, MainThreadMarker};
use objc2_app_kit::NSApplication;
use objc2_core_spotlight::{
    CSSearchableIndex, CSSearchableItem, CSSearchableItemActionType, CSSearchableItemActivityIdentifier,
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

fn body_of(raw: &str) -> &str {
    raw.split_once("\r\n\r\n").map(|(_, b)| b).unwrap_or(raw)
}

/// 向引擎一批一批拿「有變動的項目」，放進 Spotlight（或拿掉），放好再告訴引擎。
/// 第一次會把外接硬碟上的所有資料夾與檔案放進去（可能要一段時間）；之後只處理新增、改過、不在了的。
pub fn sync() {
    if !unsafe { CSSearchableIndex::isIndexingAvailable() } {
        report(false, 0, "這台 Mac 的 Spotlight 目前不能讓 App 加入項目（可能 Spotlight 被關掉了）");
        return;
    }
    let mut cursor = String::new();
    let mut changed = false;
    loop {
        let path = format!("/api/spotlight/changes?limit=500&cursor={}", cursor);
        let Some(raw) = crate::http_get(&path) else { return };
        let Ok(v) = serde_json::from_str::<serde_json::Value>(body_of(&raw)) else { return };
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
        if !items.is_empty() || !gone.is_empty() {
            let done: Vec<serde_json::Value> = items
                .iter()
                .map(|it| serde_json::json!({ "entity": it.entity, "id": it.id, "sig": it.sig }))
                .collect();
            let deleted: Vec<&str> = gone.iter().filter(|(e, _)| !e.is_empty()).map(|(e, _)| e.as_str()).collect();
            let _ = crate::http_post("/api/spotlight/ack", &serde_json::json!({ "done": done, "deleted": deleted }).to_string());
        }
        match v["cursor"].as_str() {
            Some(next) => cursor = next.to_string(),
            None => {
                let first = !*REPORTED.lock().unwrap();
                if changed || first {
                    *REPORTED.lock().unwrap() = true;
                    report(true, v["synced"].as_u64().unwrap_or(0) as usize, "");
                }
                return;
            }
        }
    }
}

/// 把結果告訴 Re'memor（設定頁顯示「放進 Spotlight 了沒、有沒有出錯」，方便本人知道狀況）
fn report(ok: bool, count: usize, error: &str) {
    let body = serde_json::json!({ "ok": ok, "count": count, "error": error }).to_string();
    let _ = crate::http_post("/api/spotlight/report", &body);
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
