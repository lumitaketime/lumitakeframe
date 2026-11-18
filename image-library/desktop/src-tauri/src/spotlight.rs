//! Spotlight（只在 macOS）：把 Re'memor 的重要項目放進 App 專用的 Spotlight 索引（Core Spotlight）。
//!
//! - 放什麼由引擎決定（GET /api/spotlight/items）：試驗版是每顆硬碟（包括沒接上的）與智慧資料夾。
//! - 索引只存在這台 Mac，不會上傳（核心原則二）。清單有變才重新放（version 不同）。
//! - 點 Spotlight 的結果：macOS 會叫 App 的「繼續活動」（application:continueUserActivity:restorationHandler:）。
//!   Tauri 底下的 tao 只處理網頁連結，所以這裡在啟動時換掉那個方法：Spotlight 的項目自己處理（打開 Re'memor、
//!   跳到那一頁），其他的照舊交給原本的處理方式。
//! - 每一項的 id 就是「rememor:」加上 Re'memor 裡的頁面路徑，點下去直接照著打開，不用另外記對照表；
//!   App 還沒準備好（例如從 Spotlight 啟動）時先記著，介面載入後再打開。

use std::sync::{Mutex, OnceLock};
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
static LAST_VERSION: Mutex<String> = Mutex::new(String::new());
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
    id: String,
    title: String,
    description: String,
    keywords: Vec<String>,
    content_type: String,
}

/// 向引擎要清單；有變才重新放進 Spotlight。
pub fn sync() {
    let Some(raw) = crate::http_get("/api/spotlight/items") else { return };
    let body = raw.split_once("\r\n\r\n").map(|(_, b)| b).unwrap_or(&raw);
    let Ok(v) = serde_json::from_str::<serde_json::Value>(body) else { return };
    let version = v["version"].as_str().unwrap_or("").to_string();
    {
        let mut last = LAST_VERSION.lock().unwrap();
        if *last == version {
            return;
        }
        *last = version;
    }
    let items: Vec<Item> = v["items"]
        .as_array()
        .cloned()
        .unwrap_or_default()
        .iter()
        .filter_map(|it| {
            Some(Item {
                id: it["id"].as_str()?.to_string(),
                title: it["title"].as_str().unwrap_or("").to_string(),
                description: it["description"].as_str().unwrap_or("").to_string(),
                keywords: it["keywords"]
                    .as_array()
                    .map(|k| k.iter().filter_map(|x| x.as_str().map(String::from)).collect())
                    .unwrap_or_default(),
                content_type: it["type"].as_str().unwrap_or("public.item").to_string(),
            })
        })
        .collect();
    unsafe { replace_all(&items) };
}

/// 先清掉 Re'memor 放過的項目，再放入新的清單（清單是空的就只清掉，例如在設定裡關掉）。
unsafe fn replace_all(items: &[Item]) {
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
        attrs.setContentDescription(Some(&NSString::from_str(&it.description)));
        let words: Vec<Retained<NSString>> = it.keywords.iter().map(|k| NSString::from_str(k)).collect();
        attrs.setKeywords(Some(&NSArray::from_retained_slice(&words)));
        list.push(CSSearchableItem::initWithUniqueIdentifier_domainIdentifier_attributeSet(
            CSSearchableItem::alloc(),
            Some(&NSString::from_str(&it.id)),
            Some(&domain),
            &attrs,
        ));
    }
    let array = NSArray::from_retained_slice(&list);
    let domains = NSArray::from_retained_slice(&[domain]);
    let target = index.clone();
    let after = RcBlock::new(move |_err: *mut NSError| {
        if array.count() > 0 {
            target.indexSearchableItems_completionHandler(&array, None);
        }
    });
    index.deleteSearchableItemsWithDomainIdentifiers_completionHandler(&domains, Some(&after));
}

/// 背景：一開始放一次，之後每分鐘看一下清單有沒有變（例如新增硬碟、改了智慧資料夾）。
pub fn start_sync_thread() {
    thread::spawn(|| loop {
        sync();
        thread::sleep(Duration::from_secs(60));
    });
}
