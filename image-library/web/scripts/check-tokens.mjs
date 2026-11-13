// 檢查介面程式沒有寫死的色碼、字級、圓角、動畫時間與曲線（手冊：全部來自 token），以及兩個語言檔的鍵一致。
// 用法：node scripts/check-tokens.mjs（pnpm check 會一併執行）
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const src = fileURLToPath(new URL("../src", import.meta.url));
// 允許寫數值的地方：設計系統產生的 token、元件樣式，以及 App 自己的變數檔
const ALLOW = ["styles/tokens.css", "styles/bundle.css", "styles/app-tokens.css"];
const RULES = [
  [/#[0-9a-fA-F]{3,8}\b(?![^<]*<\/text>)/, "色碼"],
  [/\brgba?\(/, "色碼（rgb）"],
  [/\bhsla?\(/, "色碼（hsl）"],
  [/font-size:\s*[0-9.]+(px|rem|em|pt)/, "字級"],
  [/border-radius:\s*[0-9.]+(px|rem|em)/, "圓角"],
];
const walk = (dir) => readdirSync(dir).flatMap((n) => {
  const p = join(dir, n);
  return statSync(p).isDirectory() ? walk(p) : [p];
});
let bad = 0;
for (const file of walk(src)) {
  const rel = relative(src, file).replaceAll("\\", "/");
  if (!/\.(svelte|css|js)$/.test(rel) || ALLOW.includes(rel)) continue;
  readFileSync(file, "utf8").split("\n").forEach((line, i) => {
    const code = line.replace(/\/\/.*$|\/\*.*?\*\/|<!--.*?-->/g, ""); // 註解不算
    if (/&#\d+;|href=|url\(|\$\{/.test(code) && !/color|background|border|shadow/.test(code)) return;
    // 動態：時間與曲線只能用 --dur-*、--ease-*、--spring-*（程式裡用 lib/motion.js 的 DUR、EASE）。
    // 例外：不停重複的載入指示（infinite）是固定節奏，不算介面動態；0 與 1ms 是「關掉動畫」。
    const motion = [];
    if (/(transition|animation)[a-z-]*\s*:/.test(code) && !/infinite/.test(code)) {
      const decl = code.replace(/var\([^)]*\)/g, "");
      if (/(^|[^\w.-])(?!0m?s\b|1ms\b)\d*\.?\d+m?s\b/.test(decl)) motion.push("動畫時間");
      if (/cubic-bezier\(/.test(decl)) motion.push("動畫曲線");
    }
    if (rel !== "lib/motion.js") {
      if (/\bduration\s*[:=]\s*\d{2,}/.test(code)) motion.push("動畫時間");
      if (/["'`]cubic-bezier\(/.test(code)) motion.push("動畫曲線");
    }
    for (const what of new Set(motion)) {
      console.error(`${rel}:${i + 1}  寫死的${what}：${line.trim().slice(0, 110)}`);
      bad++;
    }
    for (const [re, what] of RULES) {
      if (re.test(code)) {
        console.error(`${rel}:${i + 1}  寫死的${what}：${line.trim().slice(0, 110)}`);
        bad++;
      }
    }
  });
}
// 樣式與程式兩邊的動態數值要一致
const css = readFileSync(join(src, "styles/app-tokens.css"), "utf8");
const cssVar = (name) => css.match(new RegExp(`${name}:\\s*([^;]+);`))?.[1].trim();
const { DUR, EASE } = await import(new URL("../src/lib/motion.js", import.meta.url));
const PAIRS = [
  ["--dur-fast", `${DUR.fast}ms`], ["--dur-quick", `${DUR.quick}ms`], ["--dur", `${DUR.base}ms`], ["--dur-move", `${DUR.move}ms`], ["--dur-slow", `${DUR.slow}ms`],
  ["--ease", EASE.standard], ["--ease-out", EASE.out], ["--spring-soft", EASE.springSoft], ["--spring", EASE.spring], ["--spring-press", EASE.springPress],
];
for (const [name, js] of PAIRS) {
  if (cssVar(name) !== js) (console.error(`動態：styles/app-tokens.css 的 ${name}（${cssVar(name)}）和 lib/motion.js（${js}）不一致`), bad++);
}

const packs = Object.fromEntries(
  await Promise.all(["zh-Hant", "en"].map(async (id) => [id, (await import(new URL(`../src/i18n/${id}.js`, import.meta.url))).default])),
);
const [a, b] = [Object.keys(packs["zh-Hant"]), Object.keys(packs.en)];
for (const k of a) if (!(k in packs.en)) (console.error(`i18n：en.js 缺少「${k}」`), bad++);
for (const k of b) if (!(k in packs["zh-Hant"])) (console.error(`i18n：zh-Hant.js 缺少「${k}」`), bad++);
for (const [id, pack] of Object.entries(packs)) for (const [k, v] of Object.entries(pack)) if (!String(v).trim()) (console.error(`i18n：${id} 的「${k}」是空的`), bad++);

if (bad) {
  console.error(`\n共 ${bad} 個問題。顏色、字級、圓角請改用 styles/tokens.css 的 token 或 styles/app-tokens.css 的變數；動畫時間與曲線用 --dur-*、--ease-*、--spring-*（程式裡用 lib/motion.js）。`);
  process.exit(1);
}
console.log(`檢查通過：沒有寫死的色碼、字級、圓角、動畫時間與曲線；語言檔 ${a.length} 個鍵，繁體中文與英文一致。`);
