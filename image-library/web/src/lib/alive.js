/**
 * 讓介面「活起來」的小回饋：
 * - rubberBand：捲到最上面或最下面還繼續拉，內容會被拉開一點，放手後像彈簧一樣彈回去，告訴使用者「到底了」。
 * - installShake：按到不能用的按鈕，按鈕會左右快速搖一下（像搖頭），告訴使用者「這裡現在不能用」。
 * 開啟「減少動態效果」時兩者都不做。
 */
const reduce = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const MAX = 72; // 最多拉開的距離（px）
const SPRING = "cubic-bezier(.3, 1.45, .45, 1)"; // 回彈時稍微超過一點再停，像彈簧

/**
 * 從 target 往上到 root 之間，有沒有其他還能往這個方向捲的區塊（例如選單、面板），有的話交給它自己捲；
 * 在浮動的視窗（幻燈片、對話框）裡也不處理。
 */
function innerCanScroll(target, root, dy) {
  for (let el = target; el && el !== root; el = el.parentElement) {
    const cs = getComputedStyle(el);
    if (cs.position === "fixed") return true;
    if (el.scrollHeight <= el.clientHeight + 1) continue;
    const oy = cs.overflowY;
    if (oy !== "auto" && oy !== "scroll") continue;
    if (dy < 0 ? el.scrollTop > 0 : el.scrollTop + el.clientHeight < el.scrollHeight - 1) return true;
  }
  return false;
}

/**
 * targets：要被拉動的元素（預設是主畫面的 .route）。側邊欄傳入所有子元素（含選取膠囊）。
 * 用 CSS 的 translate 屬性而不是 transform，才不會蓋掉元素本身的 transform（例如側邊欄的選取膠囊）。
 */
export function rubberBand(node, opts = {}) {
  let pull = 0; // 正值＝在頂端往下拉，負值＝在底部往上拉
  let raw = 0;
  let idle = 0;
  let anims = [];
  let touchY = null;
  let touchStartTop = false;
  let touchStartBottom = false;

  const targets = () => (opts.targets ? opts.targets(node) : [node.querySelector(":scope > .route")]).filter(Boolean);
  const atTop = () => node.scrollTop <= 0;
  const atBottom = () => node.scrollTop + node.clientHeight >= node.scrollHeight - 1;
  // 越拉越緊：一開始跟手，接近上限時幾乎拉不動
  const resist = (d) => Math.sign(d) * MAX * (1 - Math.exp(-Math.abs(d) / (MAX * 2.2)));

  function apply() {
    anims.forEach((a) => a.cancel());
    anims = [];
    for (const el of targets()) el.style.translate = pull ? `0 ${pull}px` : "";
  }
  function release() {
    clearTimeout(idle);
    const from = pull;
    pull = 0;
    raw = 0;
    if (!from) return;
    anims = targets().map((el) => {
      el.style.translate = "";
      return el.animate([{ translate: `0 ${from}px` }, { translate: "0 0" }], { duration: 520, easing: SPRING });
    });
  }

  function onWheel(e) {
    if (reduce() || e.ctrlKey || e.metaKey || Math.abs(e.deltaX) > Math.abs(e.deltaY) || !e.deltaY) return;
    if (innerCanScroll(e.target, node, e.deltaY)) return;
    const up = e.deltaY < 0;
    if ((up && !atTop()) || (!up && !atBottom())) {
      if (pull) release();
      return;
    }
    // 滾輪一格的量依裝置不同（行／頁），統一換成像素
    const px = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * node.clientHeight : e.deltaY;
    raw = Math.max(-MAX * 6, Math.min(MAX * 6, raw - px * 0.5));
    if ((up && raw < 0) || (!up && raw > 0)) raw = 0;
    pull = resist(raw);
    apply();
    clearTimeout(idle);
    idle = setTimeout(release, 110);
  }

  function onTouchStart(e) {
    if (e.touches.length !== 1 || reduce()) return;
    touchY = e.touches[0].clientY;
    touchStartTop = atTop();
    touchStartBottom = atBottom();
  }
  function onTouchMove(e) {
    if (touchY === null || e.touches.length !== 1) return;
    const dy = e.touches[0].clientY - touchY;
    if ((dy > 0 && touchStartTop && atTop()) || (dy < 0 && touchStartBottom && atBottom())) {
      if (innerCanScroll(e.target, node, -dy)) return;
      pull = resist(dy * 0.9);
      apply();
    } else if (pull) {
      pull = 0;
      apply();
    }
  }
  function onTouchEnd() {
    touchY = null;
    if (pull) release();
  }

  node.addEventListener("wheel", onWheel, { passive: true });
  node.addEventListener("touchstart", onTouchStart, { passive: true });
  node.addEventListener("touchmove", onTouchMove, { passive: true });
  node.addEventListener("touchend", onTouchEnd, { passive: true });
  node.addEventListener("touchcancel", onTouchEnd, { passive: true });
  return {
    destroy() {
      clearTimeout(idle);
      node.removeEventListener("wheel", onWheel);
      node.removeEventListener("touchstart", onTouchStart);
      node.removeEventListener("touchmove", onTouchMove);
      node.removeEventListener("touchend", onTouchEnd);
      node.removeEventListener("touchcancel", onTouchEnd);
    },
  };
}

/** 讓元素左右搖一下（也可以在程式裡直接呼叫，例如表單還沒填完就按送出） */
export function shake(el) {
  if (!el || reduce()) return;
  el.getAnimations?.().forEach((a) => a.id === "m3-shake" && a.cancel());
  const a = el.animate(
    [
      { transform: "translateX(0)" }, { transform: "translateX(-7px)" }, { transform: "translateX(6px)" },
      { transform: "translateX(-4px)" }, { transform: "translateX(3px)" }, { transform: "translateX(-1px)" },
      { transform: "translateX(0)" },
    ],
    { duration: 380, easing: "cubic-bezier(.36, .07, .19, .97)" },
  );
  a.id = "m3-shake";
  navigator.vibrate?.([12, 40, 12]);
}

const DISABLED = "button:disabled, input:disabled, select:disabled, [aria-disabled='true']";

/**
 * 全域監聽：按到停用的控制項就搖一下。
 * 停用的按鈕在部分瀏覽器不會收到事件，所以用座標找出底下的元素再判斷。
 */
export function installShake() {
  const onDown = (e) => {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    let el = e.target?.closest?.(DISABLED);
    if (!el) {
      for (const hit of document.elementsFromPoint(e.clientX, e.clientY)) {
        if (hit.matches?.(DISABLED)) {
          el = hit;
          break;
        }
        // 只看最上層那個可互動的元素，不往下穿透到後面的東西
        if (hit.matches?.("button, a, input, select, [role=button], [role=link]")) break;
      }
    }
    if (el) shake(el.closest("label") && el.matches("input") ? el.closest("label") : el);
  };
  document.addEventListener("pointerdown", onDown, true);
  return () => document.removeEventListener("pointerdown", onDown, true);
}
