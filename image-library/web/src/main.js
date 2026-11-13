import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";
import { isMacApp, isAndroidApp } from "./lib/state.svelte.js";
import { installRangeFill } from "./lib/range.js";

// 外觀一律跟隨系統（淺色、深色、增加對比），不提供 App 專屬的外觀開關
try {
  localStorage.removeItem("theme"); // 舊版留下的設定
} catch {
  /* 無法使用 localStorage 時略過 */
}

mount(App, { target: document.getElementById("app") });
installRangeFill();

// Mac App 的視窗不能開新分頁：外部連結改用預設瀏覽器開啟
if (isMacApp) {
  document.addEventListener("click", (e) => {
    const a = e.target.closest?.("a[href]");
    if (!a) return;
    const url = new URL(a.href, location.href);
    if (url.origin === location.origin) return;
    e.preventDefault();
    fetch("/api/open-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url.href }),
    });
  });
}

// Service worker 只在瀏覽器的安全環境（本機 127.0.0.1 或 HTTPS）使用；App 外殼不需要
if ("serviceWorker" in navigator && window.isSecureContext && !isMacApp && !isAndroidApp) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
