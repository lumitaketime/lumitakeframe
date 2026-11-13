// 從設計系統的 tokens.json 產生 src/styles/tokens.css（四個主題）。
// 用法：node scripts/build-tokens.mjs（設計系統更新 tokens.json 後重新執行）
import { readFileSync, writeFileSync } from "node:fs";

const root = new URL("..", import.meta.url);
const t = JSON.parse(readFileSync(new URL("design-system/tokens.json", root), "utf8"));
const themes = t.color.themes.map((x) => x.id); // light, dark, light-hc, dark-hc
const first = themes[0];

const ref = (v) => String(v).replace(/\{([A-Za-z0-9_.-]+)\}/g, "var(--$1)");
const themed = [];
const fixed = [];
for (const [family, group] of Object.entries(t)) {
  if (!group || !Array.isArray(group.tokens)) continue;
  for (const tok of group.tokens) {
    if (tok.value && typeof tok.value === "object") themed.push(tok);
    else if (family === "color") themed.push({ ...tok, value: { [first]: tok.value } });
    else fixed.push(tok);
  }
}
const block = (theme) =>
  themed
    .map((tok) => {
      const v = tok.value[theme];
      // 每個主題都寫出全部的值：多個媒體查詢同時成立時（深色＋增加對比），後面的區塊才能完整蓋過前面的
      return `  --${tok.name}: ${ref(v ?? tok.value[first])};`;
    })
    .filter(Boolean)
    .join("\n");

const out = [`/* ${t.name} — generated from tokens.json. 不要手動修改；改 tokens.json 後執行 node scripts/build-tokens.mjs */`];
out.push(":root {");
for (const [name, stack] of Object.entries(t.type.families)) out.push(`  --font-${name}: ${stack};`);
for (const tok of fixed) out.push(`  --${tok.name}: ${ref(tok.value)};`);
for (const g of t.type.groups)
  for (const s of g.styles) out.push(`  --${s.name}-size: ${s.fontSize};`, `  --${s.name}-line: ${s.lineHeight};`, `  --${s.name}-weight: ${s.fontWeight};`);
out.push(block(first), "  color-scheme: light;", "}");

// 跟隨系統：深色、增加對比
out.push("@media (prefers-color-scheme: dark) {", "  :root {", block("dark").replace(/^/gm, "  "), "    color-scheme: dark;", "  }", "}");
out.push("@media (prefers-contrast: more) {", "  :root {", block("light-hc").replace(/^/gm, "  "), "  }", "}");
out.push("@media (prefers-color-scheme: dark) and (prefers-contrast: more) {", "  :root {", block("dark-hc").replace(/^/gm, "  "), "  }", "}");
// 指定主題（只給元件展示頁與測試截圖用；App 本身一律跟隨系統，不提供外觀開關）
for (const th of themes) {
  const all = themed.map((tok) => `  --${tok.name}: ${ref(tok.value[th] ?? tok.value[first])};`).join("\n");
  out.push(`[data-theme="${th}"] {`, all, `  color-scheme: ${th.startsWith("dark") ? "dark" : "light"};`, "}");
}
// 文字樣式類別（.mac-body、.ios-body…）
for (const g of t.type.groups)
  for (const s of g.styles) {
    const prefix = s.name.split("-")[0];
    const fam = ["mono", "serif", "rounded"].includes(prefix) ? prefix : "sans";
    out.push(`.${s.name} { font-family: var(--font-${fam}); font-size: ${s.fontSize}; line-height: ${s.lineHeight}; font-weight: ${s.fontWeight};${s.letterSpacing ? ` letter-spacing: ${s.letterSpacing};` : ""} }`);
  }
writeFileSync(new URL("src/styles/tokens.css", root), out.join("\n") + "\n");
console.log(`tokens.css：${themed.length} 個主題 token、${fixed.length} 個固定 token、${themes.length} 個主題`);
