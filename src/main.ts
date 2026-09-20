import {mount} from 'svelte';
import App from './App.svelte';
import './studio.css';
mount(App,{target:document.getElementById('app')!});

if(import.meta.env.PROD&&'serviceWorker' in navigator){window.addEventListener('load',()=>{navigator.serviceWorker.register('./sw.js').catch(()=>{/* Installation still works online when offline caching is unavailable. */});});}
