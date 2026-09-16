export type InstantKind = 'square' | 'portrait';
export function instantGeometry(iw:number,ih:number,kind:InstantKind,fit:'contain'|'cover') {
 const ratio=kind==='square'?1:3/4;
 // Keep source pixels at 1:1. Fitting adds room; filling crops instead of upscaling.
 const w=fit==='contain'?Math.max(iw,ih*ratio):Math.min(iw,ih*ratio),h=w/ratio;
 const side=w*(kind==='square'?.105:.085),top=w*(kind==='square'?.125:.15),bottom=w*(kind==='square'?.265:.335),outer=w*.055;
 return {w,h,side,top,bottom,outer,width:Math.ceil(w+2*side+2*outer),height:Math.ceil(h+top+bottom+2*outer)};
}
export function drawInstant(canvas:HTMLCanvasElement,img:HTMLImageElement|ImageBitmap,kind:InstantKind,fit:'contain'|'cover',caption:string,maxEdge?:number,cropX=.5,cropY=.5,background:'white'|'transparent'='white'){
 const g=instantGeometry(img.width,img.height,kind,fit);
 const scale=maxEdge?Math.min(1,maxEdge/Math.max(g.width,g.height)):1;
 canvas.width=Math.round(g.width*scale);canvas.height=Math.round(g.height*scale);
 const c=canvas.getContext('2d');if(!c)throw new Error('canvas');
 c.scale(scale,scale); if(background==='white'){c.fillStyle='#fff';c.fillRect(0,0,g.width,g.height);}
 const x=g.outer,y=g.outer,pw=g.w+2*g.side,ph=g.h+g.top+g.bottom,r=g.w*(kind==='square'?.008:.016);
 c.save();if(background==='white'){c.shadowColor='rgba(0,0,0,.22)';c.shadowBlur=g.w*.025;c.shadowOffsetY=g.w*.014;}
 c.fillStyle='#f8f8f6';c.beginPath();c.roundRect(x,y,pw,ph,r);c.fill();c.restore();
 const paper=c.createLinearGradient(x,y,x+pw,y+ph);paper.addColorStop(0,'#fdfdfb');paper.addColorStop(.55,'#f6f6f3');paper.addColorStop(1,'#ededeb');
 c.fillStyle=paper;c.beginPath();c.roundRect(x,y,pw,ph,r);c.fill();
 c.strokeStyle='rgba(255,255,255,.85)';c.lineWidth=g.w*.002;c.stroke();
 const ix=x+g.side,iy=y+g.top;
 c.fillStyle='#fafaf8';c.fillRect(ix,iy,g.w,g.h);
 c.save();c.beginPath();c.rect(ix,iy,g.w,g.h);c.clip();
 const factor=fit==='cover'?Math.max(g.w/img.width,g.h/img.height):Math.min(g.w/img.width,g.h/img.height);
 const dw=img.width*factor,dh=img.height*factor;
 c.drawImage(img,ix+(g.w-dw)*cropX,iy+(g.h-dh)*cropY,dw,dh);c.restore();
 c.strokeStyle='rgba(0,0,0,.12)';c.lineWidth=g.w*.003;c.strokeRect(ix,iy,g.w,g.h);
 if(kind==='square') {c.strokeStyle='rgba(0,0,0,.06)';c.lineWidth=g.w*.007;c.strokeRect(ix-g.w*.003,iy-g.w*.003,g.w+g.w*.006,g.h+g.w*.006);}
 if(caption){c.textAlign='center';c.textBaseline='middle';c.fillStyle='#454545';c.font=`${g.w*.034}px -apple-system, BlinkMacSystemFont, sans-serif`;c.fillText(caption,x+pw/2,iy+g.h+g.bottom*.48,g.w*.92);}
 return {width:g.width,height:g.height};
}
