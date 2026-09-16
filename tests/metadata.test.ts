import {test} from 'node:test';
import assert from 'node:assert/strict';
import {formatMetadata,supportsHeif} from '../src/metadata.ts';
import {outputGeometry} from '../src/renderer.ts';
function header(size:number,major:string,compatible:string[]){
 const bytes=new Uint8Array(Math.max(16,size));const view=new DataView(bytes.buffer);
 view.setUint32(0,size);bytes.set(new TextEncoder().encode('ftyp'),4);bytes.set(new TextEncoder().encode(major),8);
 compatible.forEach((brand,i)=>bytes.set(new TextEncoder().encode(brand),16+i*4));
 return {byteLength:bytes.length,getUint32:(n:number)=>view.getUint32(n),getString:(n:number,count:number)=>new TextDecoder().decode(bytes.subarray(n,n+count))};
}
test('modern iPhone ftyp > 50 bytes is supported',()=>{
 assert.equal(supportsHeif(header(52,'heic',['mif1','MiHB','MiHA','heix','MiHE','MiPr','miaf','heic','tmap'])),true);
 assert.equal(supportsHeif(header(24,'mif1',['heic','mif1'])),true);
 assert.equal(supportsHeif(header(24,'mp42',['mp42','isom'])),false);
});
test('metadata has finite, legible values and preserves iPhone aperture',()=>{
 assert.deepEqual(formatMetadata({Make:'Apple',Model:'iPhone 17',FNumber:1.6,FocalLength:5.960000038,ExposureTime:1/5814,ISO:32}),{Make:'Apple',Model:'iPhone 17',FocalLength:'5.96mm',FNumber:'f/1.6',ExposureTime:'1/5814s',ISO:'ISO32'});
 assert.deepEqual(formatMetadata(undefined),{});
 assert.deepEqual(formatMetadata({ExposureTime:0,ISO:'bad',FNumber:-1}),{});
});
test('full resolution geometry preserves pixels, and instant cover crops without upscaling',()=>{
 assert.deepEqual(outputGeometry(4000,3000,'None','contain'),{width:4000,height:3000,border:0,footer:0});
 assert.equal(outputGeometry(4000,3000,'Frame','contain').width,4120);
 const fill=outputGeometry(4000,3000,'Instant Square','cover');assert.equal('w' in fill&&fill.w,3000);
 const fit=outputGeometry(4000,3000,'Instant Square','contain');assert.equal('w' in fit&&fit.w,4000);
});
