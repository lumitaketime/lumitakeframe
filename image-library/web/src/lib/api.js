import { app } from "./state.svelte.js";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function api(path, { method, body, params, signal } = {}) {
  let url = path;
  if (params) {
    const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""));
    const qs = new URLSearchParams(clean).toString();
    if (qs) url += (url.includes("?") ? "&" : "?") + qs;
  }
  const hasBody = body !== undefined;
  const res = await fetch(url, {
    method: method || (hasBody ? "POST" : "GET"),
    headers: hasBody ? { "Content-Type": "application/json" } : {},
    body: hasBody ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
    signal,
  });
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    app.needLogin = true;
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data.error || data.detail || res.statusText, res.status);
  return data;
}

export const thumbUrl = (a) => `/api/assets/${a.id}/thumb${a.fp ? `?v=${a.fp}` : ""}`;
export const previewUrl = (a, size = 2048) => `/api/assets/${a.id}/preview?size=${size}${a.fp ? `&v=${a.fp}` : ""}`;
export const originalUrl = (a, download = false) => `/api/assets/${a.id}/original${download ? "?download=1" : ""}`;
