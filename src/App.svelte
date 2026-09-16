<script lang="ts">
 import {onMount} from 'svelte';
 import {loadExif,type ExifData} from './metadata';
 import {renderPhoto,type Settings} from './renderer';
 import {decodePhoto,canvasBlob,type PhotoImage} from './photo';
 import {instantGeometry} from './instant';
 let lang:'zh'|'en'='zh',dark=false;
 $: t=(zh:string,en:string)=>lang==='zh'?zh:en;
 const alignments=['left','center','right'] as const;
 let fileInput:HTMLInputElement;
 let canvas:HTMLCanvasElement;
 let image:PhotoImage|undefined;
 let source:File|undefined,exif:ExifData={};
 let busy=false,saving=false,drag=false,error='',notice='';
 let paper:'light'|'dark'='light';
 let ink:'white'|'gray'|'black'='white';
 let layout='Frame',align:'left'|'center'|'right'='center';
 let showCamera=true,showParameters=true,caption='',fit:'contain'|'cover'='contain';
 let model='',make='',focalLength='',fNumber='',exposureTime='',iso='',lens='',date='';
 let quality='png',termsAccepted=false,creditCopied=false;
 $: creditText=t('使用 Photo Frame Studio 製作','Made with Photo Frame Studio')+' — https://lumitaketime.github.io/photo-frame-studio/';
 async function copyCredit(){try{await navigator.clipboard.writeText(creditText);creditCopied=true;}catch{creditCopied=false;}}

 let settingsDialog:HTMLDialogElement,exportDialog:HTMLDialogElement;
 let thumbnail='',metadataState:'idle'|'reading'|'ready'|'empty'|'error'='idle';
 let photoRequest=0;
 function applyMetadata(data:ExifData){exif=data;model=data.Model??'';make=data.Make??'';focalLength=data.FocalLength??'';fNumber=data.FNumber??'';exposureTime=data.ExposureTime??'';iso=data.ISO??'';lens=data.LensModel??'';date=data.CreateDate?new Date(data.CreateDate).toLocaleString():'';}
 function selectLayout(value:string){layout=value;cropX=cropY=.5;}

 let outputSize='',cropX=.5,cropY=.5;
 let pointer:{id:number,x:number,y:number}|undefined;
 const clamp=(v:number)=>Math.max(0,Math.min(1,v));
 function cropStart(e:PointerEvent){if(!instant||fit!=='cover'||!image||busy||saving)return;e.preventDefault();canvas.setPointerCapture(e.pointerId);pointer={id:e.pointerId,x:e.clientX,y:e.clientY};}
 function cropMove(e:PointerEvent){if(!pointer||pointer.id!==e.pointerId||!image)return;const g=instantGeometry(image.width,image.height,layout==='Instant Square'?'square':'portrait',fit);const scale=canvas.getBoundingClientRect().width/g.width;const factor=Math.max(g.w/image.width,g.h/image.height);const dx=image.width*factor-g.w,dy=image.height*factor-g.h;if(dx>0)cropX=clamp(cropX-(e.clientX-pointer.x)/scale/dx);if(dy>0)cropY=clamp(cropY-(e.clientY-pointer.y)/scale/dy);pointer={id:e.pointerId,x:e.clientX,y:e.clientY};}
 function stageKey(e:KeyboardEvent){if(image&&instant&&fit==='cover'){if(e.key.startsWith('Arrow')){e.preventDefault();if(e.key==='ArrowLeft')cropX=clamp(cropX+.03);if(e.key==='ArrowRight')cropX=clamp(cropX-.03);if(e.key==='ArrowUp')cropY=clamp(cropY+.03);if(e.key==='ArrowDown')cropY=clamp(cropY-.03);}return;}if(e.key==='Enter'||e.key===' '){e.preventDefault();if(!busy&&!saving)fileInput.click();}}
 const layouts=[{id:'Frame',zh:'經典',en:'Classic',shape:'classic'},{id:'Just a Frame',zh:'純框',en:'Border',shape:'border'},{id:'Instant Square',zh:'方形拍立得',en:'Instant Square',shape:'square'},{id:'Instant Portrait',zh:'直式拍立得',en:'Instant Portrait',shape:'portrait'},{id:'In the Photo',zh:'照片內文字',en:'Overlay',shape:'overlay'},{id:'Banner',zh:'資訊橫幅',en:'Banner',shape:'banner'},{id:'None',zh:'原始照片',en:'Unframed',shape:'unframed'}];
 $: instant=layout.startsWith('Instant');
 $: details=['Frame','In the Photo','Banner'].includes(layout);
 $: options={theme:paper,align:layout==='In the Photo'&&align==='center'?'left':align,color:ink,model,make,focalLength,fNumber,exposureTime,iso,lens,date,showCamera,showParameters};
 function render(target:HTMLCanvasElement,preview:boolean){
  if(!image)return;
  const dimensions=renderPhoto(target,image,layout,options as Settings,fit,caption,cropX,cropY,preview?1600:undefined);
  if(preview)outputSize=`${dimensions.width} × ${dimensions.height}`;
 }
 $: if(canvas&&image){options;layout;fit;caption;cropX;cropY;render(canvas,true);}
 onMount(()=>{try{lang=localStorage.getItem('exif-lang')==='en'?'en':'zh';const theme=localStorage.getItem('exif-theme');dark=theme?theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;}catch{} });
 function toggleLanguage(){lang=lang==='zh'?'en':'zh';try{localStorage.setItem('exif-lang',lang)}catch{} }
 function toggleTheme(){dark=!dark;try{localStorage.setItem('exif-theme',dark?'dark':'light')}catch{} }
 $: if(typeof document!=='undefined'){document.documentElement.lang=lang==='zh'?'zh-Hant':'en';document.documentElement.dataset.theme=dark?'dark':'light';}
 async function openPhoto(file?:File){
  if(!file||busy||saving)return;busy=true;error='';notice='';
  const request=++photoRequest;metadataState='reading';applyMetadata({});if(typeof ImageBitmap!=='undefined'&&image instanceof ImageBitmap)image.close();image=undefined;source=undefined;thumbnail='';
  const metadataTimer=setTimeout(()=>{if(request===photoRequest&&metadataState==='reading')metadataState='error';},15000);
  void loadExif(file).then(data=>{if(request!==photoRequest)return;applyMetadata(data);metadataState=Object.keys(data).length?'ready':'empty';}).catch(()=>{if(request===photoRequest)metadataState='error';}).finally(()=>clearTimeout(metadataTimer));
  try{const decoded=await decodePhoto(file);
   image=decoded;source=file;cropX=cropY=.5;
   const thumb=document.createElement('canvas');thumb.width=240;thumb.height=Math.round(240*decoded.height/decoded.width);thumb.getContext('2d')!.drawImage(decoded,0,0,thumb.width,thumb.height);thumbnail=thumb.toDataURL('image/jpeg',.75);thumb.width=thumb.height=1;

  }catch{error='decode';}finally{busy=false;if(fileInput)fileInput.value='';}
 }
 function drop(e:DragEvent){e.preventDefault();drag=false;openPhoto(e.dataTransfer?.files[0]);}
 async function download(original=false){
  if(!image||!source||saving||busy||(!original&&!termsAccepted))return;saving=true;error='';notice='';
  let target:HTMLCanvasElement|undefined;
  try{
   // Give the progress label a paint before full resolution rendering.
   await new Promise(resolve=>setTimeout(resolve,30));
   let blob:Blob,extension:string;
   if(original){blob=source;extension=source.name.split('.').pop()??'jpg';}
   else{target=document.createElement('canvas');render(target,false);extension=quality==='png'?'png':'jpg';blob=await canvasBlob(target,quality==='png'?'image/png':'image/jpeg',.92);}
   const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=original?source.name:source.name.replace(/\.[^.]+$/,'')+'-frame.'+extension;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);notice='saved';
  }catch{error='export';}finally{if(target){target.width=1;target.height=1;}saving=false;}
 }
</script>

<div class="studio" class:dark>
 <header class="topbar">
  <a class="wordmark" href="./" aria-label="Photo Frame Studio">frame<span class="wordmark-dot">.</span></a>
  <div class="top-actions">
   <button class="quiet-button language" on:click={toggleLanguage} aria-label={t('切換為英文','Switch to Chinese')}>{lang==='zh'?'EN':'中文'}</button>
   <span class="divider"></span>
   <button class="quiet-button mode" on:click={toggleTheme} aria-label={t(dark?'切換淺色模式':'切換深色模式',dark?'Switch to light mode':'Switch to dark mode')}>
    {#if dark}<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>{:else}<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M20 15.5A8.8 8.8 0 0 1 8.5 4 8.8 8.8 0 1 0 20 15.5Z"/></svg>{/if}
   </button>
  </div>
 </header>
 <main class="workspace">
  <section class="photo-workspace" aria-label={t('照片預覽','Photo preview')}>

   <div class="stage" class:dragging={drag} class:has-image={!!image} class:cropping={!!image&&instant&&fit==='cover'} role="button" tabindex="0" aria-label={t('選擇或拖曳照片','Choose or drop a photo')} on:click={()=>{if(!image&&!busy&&!saving)fileInput.click()}} on:keydown={stageKey} on:dragover={e=>{e.preventDefault();drag=true}} on:dragleave={()=>drag=false} on:drop={drop}>
    <canvas on:pointerdown={cropStart} on:pointermove={cropMove} on:pointerup={()=>pointer=undefined} on:pointercancel={()=>pointer=undefined} on:lostpointercapture={()=>pointer=undefined} bind:this={canvas} class:visible={!!image} aria-label={t('套用邊框後的照片','Framed photo preview')}></canvas>
    {#if !image}<div class="empty-state"><div class="empty-frame"><span>+</span></div><h1>{t('讓照片成為作品','Make it a photograph.')}</h1><p>{t('拖曳照片至此，或點選開始','Drop a photo here, or click to begin')}</p><span class="file-types">HEIC · JPG · PNG · WEBP</span></div>{/if}
    {#if busy}<div class="loading-overlay"><span class="spinner"></span><p>{t('正在讀取照片…','Opening your photo…')}</p></div>{/if}
   </div>
   <input class="visually-hidden" tabindex="-1" aria-label={t('照片檔案','Photo file')} bind:this={fileInput} type="file" accept="image/*,.heic,.heif" on:change={()=>openPhoto(fileInput.files?.[0])}/>
   <div class="photo-meta"><div><span class="filename">{source?.name??t('選擇一張喜歡的照片','Start with a photo you love')}</span>{#if image}<span>{image.width} × {image.height} px</span>{/if}</div><button class="text-button" disabled={busy||saving} on:click={()=>fileInput.click()}>{source?t('更換照片','Replace photo'):t('選擇照片','Choose photo')}<span aria-hidden="true"> ↗</span></button></div>
  </section>
  <section class="simple-controls" aria-label={t('照片設定','Photo controls')}>
   <h2>{t('畫框','Frame')}</h2>
   <div class="template-grid primary-frames">
    {#each [layouts[0],layouts[1],layouts[2]] as item}
     <button class="template" class:selected={item.id==='Instant Square'?instant:layout===item.id} aria-pressed={item.id==='Instant Square'?instant:layout===item.id} on:click={()=>selectLayout(item.id)}>
      <span class="thumb-wrap"><span class="frame-thumb {item.shape}"><span style:background-image={thumbnail?`url("${thumbnail}")`:undefined}></span>{#if item.id==='Frame'}<i aria-hidden="true" class="mini-exif">Shot on CAMERA<br/>35mm f/2 ISO100</i>{/if}</span></span>
      <span>{item.id==='Instant Square'?t('拍立得','Instant'):lang==='zh'?item.zh:item.en}</span>
     </button>
    {/each}
   </div>
   {#if instant}
    <div class="segmented"><button class:active={layout==='Instant Square'} on:click={()=>selectLayout('Instant Square')}>{t('方形','Square')}</button><button class:active={layout==='Instant Portrait'} on:click={()=>selectLayout('Instant Portrait')}>{t('直式','Portrait')}</button></div>
    <div class="segmented fit-controls"><button class:active={fit==='contain'} on:click={()=>fit='contain'}>{t('完整保留','Fit entire photo')}</button><button class:active={fit==='cover'} on:click={()=>fit='cover'}>{t('填滿裁切','Fill & crop')}</button></div>
    {#if fit==='cover'}<p class="hint">{t('拖曳照片調整位置','Drag the photo to adjust its position')} <button class="inline-link" on:click={()=>cropX=cropY=.5}>{t('重設置中','Recenter')}</button></p>{/if}
   {:else if layout==='Frame'}
    <label class="toggle-row"><span>{t('相機資訊','Camera details')}</span><input type="checkbox" bind:checked={showCamera}/><span class="switch"></span></label>
    <label class="toggle-row"><span>{t('拍攝參數','Exposure settings')}</span><input type="checkbox" bind:checked={showParameters}/><span class="switch"></span></label>
   {:else if !['Just a Frame'].includes(layout)}<p class="hint">{t('目前版型：','Current frame: ')}{lang==='zh'?layouts.find(x=>x.id===layout)?.zh:layouts.find(x=>x.id===layout)?.en}</p>{/if}
   {#if source}<p class="metadata-status" aria-live="polite">{metadataState==='ready'?t('✓ 拍攝資訊已讀取','✓ Photo metadata loaded'):metadataState==='reading'?t('正在讀取拍攝資訊…','Reading photo metadata…'):metadataState==='error'?t('拍攝資訊讀取失敗，可在設定中手動填寫。','Metadata could not be read. You can enter it in Settings.'):t('這張照片沒有可用的拍攝資訊，可在設定中填寫。','No photo metadata found. You can enter it in Settings.')}</p>{/if}
  </section>
    <div class="feedback" aria-live="polite">{#if error}<p class="error" role="alert">{error==='decode'?t('無法讀取這張照片，請確認檔案完整並再試一次。','Could not open this photo. Check the file and try again.'):t('裝置無法輸出這個尺寸，請改用電腦或下載原始檔案。','This device could not export this size. Try a computer or download the original file.')}</p>{:else if notice}<p>{t('照片已準備下載。','Your photo is ready to download.')}</p>{/if}</div>
 </main>
 <footer><span>{t('靈感致敬','Inspired by')} <a href="https://github.com/ssssota/exif.photos" target="_blank" rel="noreferrer">ssssota · exif.photos</a></span><a href="./THIRD-PARTY-NOTICES.txt" target="_blank" rel="noreferrer">{t('第三方授權','Third-party notices')}</a><a href="./terms.html" target="_blank" rel="noreferrer">{t('使用條款與授權','Terms & licenses')}</a></footer>
 <div class="bottom-dock">
  <button class="settings-button" on:click={()=>settingsDialog.showModal()}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 6h18M3 12h18M3 18h18"/><circle cx="8" cy="6" r="2" fill="var(--panel)"/><circle cx="16" cy="12" r="2" fill="var(--panel)"/><circle cx="10" cy="18" r="2" fill="var(--panel)"/></svg>{t('設定','Settings')}</button>
  <button class="download-button" disabled={!image||busy||saving} on:click={()=>exportDialog.showModal()}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M5 16v5h14v-5"/></svg>{saving?t('正在製作…','Preparing…'):t('下載照片','Download photo')}</button>
 </div>
 <dialog bind:this={settingsDialog} aria-labelledby="settings-title">
  <div class="sheet-head"><h2 id="settings-title">{t('設定','Settings')}</h2><button class="text-button" on:click={()=>settingsDialog.close()}>{t('完成','Done')}</button></div>
  <div class="sheet-content"><label class="field-label" for="all-frames">{t('所有版型','All frames')}</label><select id="all-frames" value={layout} on:change={e=>selectLayout(e.currentTarget.value)}>{#each layouts as item}<option value={item.id}>{lang==='zh'?item.zh:item.en}</option>{/each}</select>
    {#if instant}
     <label class="field-label" for="fit">{t('照片呈現','Photo fit')}</label><div class="segmented" id="fit"><button class:active={fit==='contain'} aria-pressed={fit==='contain'} on:click={()=>fit='contain'}>{t('完整保留','Fit entire photo')}</button><button class:active={fit==='cover'} aria-pressed={fit==='cover'} on:click={()=>fit='cover'}>{t('填滿裁切','Fill & crop')}</button></div>
     <p class="hint">{fit==='contain'?t('保留完整構圖，比例不同時在相紙內留白。','Keeps the full composition, with space when ratios differ.'):t('直接在拍立得上拖曳照片，調整裁切位置。','Drag the photo inside the instant frame to adjust the crop.')}</p>
     <label class="field-label" for="caption">{t('相紙題字','Caption')}</label><input id="caption" bind:value={caption} maxlength="100" placeholder={t('留下一句話，也可以留白','A few words, or simply leave it blank')}/>
    {:else if details}
     {#if layout!=='In the Photo'}<div class="inline-control"><span>{t('相框顏色','Frame tone')}</span><div class="swatches"><button class="swatch white" class:chosen={paper==='light'} aria-label={t('白色相框','White frame')} aria-pressed={paper==='light'} on:click={()=>paper='light'}></button><button class="swatch black" class:chosen={paper==='dark'} aria-label={t('黑色相框','Black frame')} aria-pressed={paper==='dark'} on:click={()=>paper='dark'}></button></div></div>{:else}<label class="field-label" for="ink">{t('文字顏色','Text color')}</label><select id="ink" bind:value={ink}><option value="white">{t('白色','White')}</option><option value="gray">{t('灰色','Gray')}</option><option value="black">{t('黑色','Black')}</option></select>{/if}
     {#if layout!=='Banner'}<label class="field-label" for="alignment">{t('文字對齊','Alignment')}</label><div class="segmented" id="alignment">{#each alignments as a}{#if layout!=='In the Photo'||a!=='center'}<button class:active={align===a} aria-pressed={align===a} on:click={()=>align=a}>{a==='left'?t('靠左','Left'):a==='center'?t('置中','Center'):t('靠右','Right')}</button>{/if}{/each}</div>{/if}

     <details class="metadata-editor"><summary>{t('編輯文字與參數','Edit text & metadata')}<span>+</span></summary><div class="fields"><label>{t('相機型號','Camera model')}<input bind:value={model} placeholder="ILCE-7M4"/></label><label>{t('品牌','Make')}<input bind:value={make} placeholder="SONY"/></label><label>{t('焦距','Focal length')}<input bind:value={focalLength} placeholder="35mm"/></label><label>{t('光圈','Aperture')}<input bind:value={fNumber} placeholder="f/2.0"/></label><label>{t('快門','Shutter')}<input bind:value={exposureTime} placeholder="1/200s"/></label><label>ISO<input bind:value={iso} placeholder="ISO100"/></label>{#if layout==='Banner'}<label>{t('鏡頭','Lens')}<input bind:value={lens}/></label><label>{t('日期','Date')}<input bind:value={date}/></label>{/if}</div><p class="hint">{t('自動讀取原始拍攝資訊，可自由修改。','Read from the original file. Yours to edit.')}</p></details>
    {:else}<p class="hint">{t('純粹保留照片，無需其他設定。','Nothing more to add. Just your photograph.')}</p>{/if}
  </div>
 </dialog>
 <dialog bind:this={exportDialog} aria-labelledby="export-title">
  <div class="sheet-head"><h2 id="export-title">{t('下載照片','Download photo')}</h2><button class="text-button" on:click={()=>exportDialog.close()}>{t('關閉','Close')}</button></div>
  <div class="sheet-content">
    <label class="field-label" for="quality">{t('下載畫質','Download quality')}</label><select id="quality" bind:value={quality}><option value="png">{t('無損 PNG','Lossless PNG')}</option><option value="jpg">{t('有損 JPG','Lossy JPG')}</option></select>
    <p class="hint">{quality==='png'?t('原尺寸輸出，不再有損壓縮；檔案較大。','Full resolution, without further lossy compression. Larger files.'):t('原尺寸輸出，適度壓縮；方便儲存與分享。','Full resolution with compression. Smaller files for sharing.')}</p>
    {#if image}<div class="export-size"><span>{t('輸出尺寸','Output size')}</span><span>{outputSize} px</span></div>{/if}
    <div class="usage-terms">
     <p>{t('僅限非商業用途。分享成品時，請在貼文或作品說明附上工具名稱與連結；照片著作權仍屬你。','For noncommercial use only. Credit this tool and link to it when sharing. Your photograph remains yours.')}</p>
     <label class="terms-check"><input type="checkbox" bind:checked={termsAccepted}/><span>{t('我已閱讀並同意','I have read and agree to the')} <a href="./terms.html" target="_blank" rel="noreferrer">{t('使用條款','terms of use')}</a></span></label>
     <label class="field-label" for="photo-credit">{t('分享時的署名文字','Credit for sharing')}</label>
     <textarea id="photo-credit" readonly rows="3" value={creditText}></textarea>
     <button class="text-button" on:click={copyCredit}>{creditCopied?t('已複製','Copied'):t('複製署名文字','Copy credit')}</button>
    </div>
    <button class="download-button" on:click={()=>download()} disabled={!image||busy||saving||!termsAccepted}>{saving?t('正在製作…','Preparing…'):t('下載照片','Download photo')}<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M5 16v5h14v-5"/></svg></button>
    <button class="text-button" disabled={!image||busy||saving} on:click={()=>download(true)}>{t('下載原始檔案（不加框）','Download untouched original')}</button>
    <div class="feedback" aria-live="polite">{#if error}<p class="error" role="alert">{error==='decode'?t('無法讀取這張照片，請確認檔案完整並再試一次。','Could not open this photo. Check the file and try again.'):t('裝置無法輸出這個尺寸，請改用電腦或下載原始檔案。','This device could not export this size. Try a computer or download the original file.')}</p>{:else if notice}<p>{t('照片已準備下載。','Your photo is ready to download.')}</p>{/if}</div>
  </div>
 </dialog>
</div>
