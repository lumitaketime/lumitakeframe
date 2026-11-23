/**
 * 助理回答的簡單排版（不用 {@html}，不會執行任何 HTML）：
 * 標題（# …）、清單（- …、* …、1. …）、段落、**粗體**，以及引用 [1]（只有真的對到來源時才變成可以按的編號，否則拿掉）。
 * 回傳 [{type: "h"|"p"|"ul"|"ol", items?: [[片段…]], inline?: [片段…]}]；片段是 {text, bold} 或 {ref}。
 */
function inline(text, refs) {
  const out = [];
  const re = /\*\*(.+?)\*\*|\[(\d{1,2})\]/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push({ text: text.slice(last, m.index) });
    if (m[1] != null) out.push({ text: m[1], bold: true });
    else if (refs(Number(m[2]))) out.push({ ref: Number(m[2]) });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out.map((p) => (p.text != null ? { ...p, text: p.text.replace(/\*\*/g, "") } : p));
}

export function blocks(text, refs = () => false) {
  const out = [];
  let para = [];
  const flush = () => {
    if (para.length) out.push({ type: "p", inline: inline(para.join("\n"), refs) });
    para = [];
  };
  for (const raw of (text || "").split("\n")) {
    const line = raw.replace(/\s+$/, "");
    const h = line.match(/^#{1,4}\s+(.*)$/);
    const ul = line.match(/^\s*[-*•]\s+(.*)$/);
    const ol = line.match(/^\s*(\d{1,3})[.)、]\s+(.*)$/);
    if (!line.trim()) {
      flush();
    } else if (h) {
      flush();
      out.push({ type: "h", inline: inline(h[1], refs) });
    } else if (ul || ol) {
      flush();
      const type = ul ? "ul" : "ol";
      const item = inline(ul ? ul[1] : ol[2], refs);
      const prev = out[out.length - 1];
      if (prev && prev.type === type) prev.items.push(item);
      else out.push({ type, items: [item], start: ol ? Number(ol[1]) : 1 });
    } else {
      para.push(line);
    }
  }
  flush();
  return out;
}
