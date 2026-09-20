<script lang="ts">
 import {onMount} from 'svelte';
 export let lang:'zh'|'en'='zh';
 interface InstallEvent extends Event {prompt:()=>Promise<void>;userChoice:Promise<{outcome:string}>}
 let promptEvent:InstallEvent|undefined,installed=true,ios=false,help=false;
 $: t=(zh:string,en:string)=>lang==='zh'?zh:en;
 onMount(()=>{
  const display=matchMedia('(display-mode: standalone)');
  const sync=()=>installed=display.matches||!!(navigator as Navigator&{standalone?:boolean}).standalone;
  sync();ios=/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
  const ready=(e:Event)=>{e.preventDefault();promptEvent=e as InstallEvent;};
  const done=()=>{installed=true;promptEvent=undefined;help=false;};
  window.addEventListener('beforeinstallprompt',ready);window.addEventListener('appinstalled',done);display.addEventListener('change',sync);
  return()=>{window.removeEventListener('beforeinstallprompt',ready);window.removeEventListener('appinstalled',done);display.removeEventListener('change',sync);};
 });
 async function install(){if(!promptEvent){help=!help;return;}const event=promptEvent;promptEvent=undefined;try{await event.prompt();await event.userChoice;}catch{help=true;}}
</script>
{#if !installed}<section class="install-app" aria-label={t('安裝應用程式','Install app')}>
 <button class="text-button" on:click={install}>{t('安裝到裝置','Install app')} ↓</button>
 {#if help}<p role="status">{ios?t('在 Safari 開啟本網站，點選分享 → 加入主畫面；若出現「以網頁 App 開啟」，請保持開啟，再點「加入」。','Open this site in Safari, tap Share → Add to Home Screen. Keep Open as Web App enabled if shown, then tap Add.'):t('請在瀏覽器選單選擇「安裝應用程式」或「加入主畫面」。若沒有此選項，請使用最新版 Chrome 或 Edge 開啟本網站。','Choose Install app or Add to Home Screen in your browser menu. If unavailable, open this site in an up-to-date Chrome or Edge browser.')}</p>{/if}
</section>{/if}
