export async function isHeicFile(file: Blob & {name?: string}): Promise<boolean> {
 const head = new Uint8Array(await file.slice(0,64).arrayBuffer());
 const text = String.fromCharCode(...head);
 return /image\/hei[cf]/i.test(file.type) || /\.hei[cf]$/i.test(file.name ?? '') || (text.slice(4,8)==='ftyp' && /heic|heix|hevc|hevx|mif1|msf1/.test(text));
}
export type PhotoImage = HTMLImageElement | ImageBitmap;
export function loadImage(blob: Blob): Promise<HTMLImageElement> {
 return new Promise((resolve,reject)=>{
  const url=URL.createObjectURL(blob),img=new Image();
  const finish=(ok:boolean)=>{clearTimeout(timer);img.onload=null;img.onerror=null;URL.revokeObjectURL(url);if(ok)resolve(img);else{img.src='';reject(new Error('decode'));}};
  const timer=setTimeout(()=>finish(false),15000);
  img.onload=()=>finish(true);img.onerror=()=>finish(false);img.src=url;
 });
}
export async function decodePhoto(file: File): Promise<PhotoImage> {
 try { return await loadImage(file); } catch {
  if (!await isHeicFile(file)) throw new Error('decode');
  const {heicTo}=await import('heic-to/csp');
  return await heicTo({blob:file,type:'bitmap'}) as ImageBitmap;
 }
}
export function canvasBlob(canvas: HTMLCanvasElement,type:string,quality?:number):Promise<Blob> {
 return new Promise((resolve,reject)=>{try{canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('export')),type,quality)}catch{reject(new Error('export'))}});
}
