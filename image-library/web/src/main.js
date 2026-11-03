import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";
import { isMacApp, isAndroidApp } from "./lib/state.svelte.js";

try {
  const theme = localStorage.getItem("theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch {
  /* 無法使用 localStorage 時跟隨系統 */
}

mount(App, { target: document.getElementById("app") });

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
