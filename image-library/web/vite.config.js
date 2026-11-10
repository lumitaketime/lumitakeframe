import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// 建置結果放進 Python 套件，安裝時不需要 Node.js
export default defineConfig({
  plugins: [svelte()],
  build: {
    outDir: "../lumilib/web",
    emptyOutDir: true,
    chunkSizeWarningLimit: 800,
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8766" },
  },
});
