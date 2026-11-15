<script>
  /** 檔案類型圖示：用手冊規定的類型色；顏色不是唯一線索，圖形也各不相同。 */
  import { Icon } from "../ui/index.js";

  let { kind = "other", size = 16 } = $props();
  const ICONS = { folder: "folder", drive: "external-drive-fill", "drive-offline": "external-drive", photo: "photo", raw: "photo", video: "video", audio: "music-note", document: "document", archive: "archive", package: "file", other: "file" };
  const COLOR = { raw: "raw", package: "other", drive: "folder", "drive-offline": "other" };
</script>

<span class="kind" style:color="var(--kind-{COLOR[kind] || kind})"><Icon name={ICONS[kind] || "file"} {size} weight="medium" /></span>

<style>
  .kind { display: inline-flex; flex: none; }
</style>
