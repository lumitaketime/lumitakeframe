import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";

try {
  const theme = localStorage.getItem("theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch {
  /* 無法使用 localStorage 時跟隨系統 */
}

mount(App, { target: document.getElementById("app") });

// Service worker 只在安全環境（本機 127.0.0.1 或 HTTPS）可用
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
