/** 「關於」頁的資料。版本號由伺服器回報（跟著每次發佈自動更新）。 */
export const ABOUT = {
  name: "Re'memor",
  tagline: "硬碟目錄、去重與全文檢索",
  author: "Lumi taketime",
  year: "2026",
  email: "lumitaketime@gmail.com",
  license: {
    name: "創用 CC 姓名標示－非商業性－相同方式分享 4.0 國際（CC BY-NC-SA 4.0）",
    short: "CC BY-NC-SA 4.0",
    url: "https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hant",
    summary: [
      "姓名標示：轉載、分享或改作時，必須標示原作者 Lumi taketime，並附上授權條款連結。",
      "非商業性：不得用於商業目的。",
      "相同方式分享：改作後的作品必須以相同的條款釋出。",
    ],
  },
};

// 內含或會下載的第三方元件與資料（各自依原授權）
export const THIRD_PARTY = [
  ["Svelte、Vite", "MIT"],
  ["Tauri（Mac App 外殼）", "MIT / Apache-2.0"],
  ["Python、FastAPI、Uvicorn", "PSF / MIT / BSD"],
  ["Pillow、NumPy", "MIT-CMU / BSD"],
  ["ONNX Runtime", "MIT"],
  ["ExifTool（Phil Harvey）", "Artistic License / GPL"],
  ["GeoNames 離線地名資料", "CC BY 4.0"],
  ["Material Design Icons、Roboto 字型", "Apache-2.0"],
  ["Manrope 字型（文字標誌）", "SIL Open Font License 1.1"],
  ["Ollama 與所選的 AI 模型（例如 Gemma）", "MIT／各模型自己的授權條款"],
  ["InsightFace 人臉模型", "僅限非商業研究用途"],
  ["CLIP 圖像搜尋模型（多語言）", "MIT 等，依所選模型"],
];
