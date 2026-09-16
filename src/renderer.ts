import {drawInstant,instantGeometry} from './instant.ts';
import type {PhotoImage} from './photo';
export interface Settings {
 theme:'light'|'dark';align:'left'|'center'|'right';color:'white'|'gray'|'black';
 model:string;make:string;focalLength:string;fNumber:string;exposureTime:string;iso:string;lens:string;date:string;
 showCamera:boolean;showParameters:boolean;
}
export function outputGeometry(width:number,height:number,layout:string,fit:'contain'|'cover'){
 if(layout.startsWith('Instant'))return instantGeometry(width,height,layout==='Instant Square'?'square':'portrait',fit);
 const edge=Math.min(width,height),border=layout==='Frame'||layout==='Just a Frame'?edge*.02:0;
 const footer=layout==='Frame'?edge*.13:layout==='Banner'?edge*.15:border;
 return {width:Math.round(width+border*2),height:Math.round(height+border+footer),border,footer};
}
interface Run {text:string;weight?:number;color:string}
function line(ctx:CanvasRenderingContext2D,runs:Run[],x:number,y:number,size:number,align:CanvasTextAlign,maxWidth:number){
 const face=(weight=400)=>`${weight} ${size}px -apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif`;
 let total=0;for(const run of runs){ctx.font=face(run.weight);total+=ctx.measureText(run.text).width;}
 const shrink=Math.min(1,maxWidth/Math.max(total,1));
 ctx.save();ctx.translate(x,y);ctx.scale(shrink,shrink);ctx.textBaseline='middle';ctx.textAlign='left';
 let pen=align==='center'?-total/2:align==='right'?-total:0;
 for(const run of runs){ctx.font=face(run.weight);ctx.fillStyle=run.color;ctx.fillText(run.text,pen,0);pen+=ctx.measureText(run.text).width;}
 ctx.restore();
}
export function renderPhoto(canvas:HTMLCanvasElement,image:PhotoImage,layout:string,settings:Settings,fit:'contain'|'cover',caption:string,cropX:number,cropY:number,maxEdge?:number){
 if(layout.startsWith('Instant'))return drawInstant(canvas,image,layout==='Instant Square'?'square':'portrait',fit,caption,maxEdge,cropX,cropY);
 const size=outputGeometry(image.width,image.height,layout,fit);
 const scale=maxEdge?Math.min(1,maxEdge/Math.max(size.width,size.height)):1;
 canvas.width=Math.round(size.width*scale);canvas.height=Math.round(size.height*scale);
 const ctx=canvas.getContext('2d');if(!ctx)throw new Error('canvas');
 ctx.scale(scale,scale);ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
 const dark=settings.theme==='dark',ink=dark?'#fafafa':'#191919',muted=dark?'#c2c2c2':'#888888';
 ctx.fillStyle=dark?'#161616':'#ffffff';ctx.fillRect(0,0,size.width,size.height);
 const b='border' in size?size.border:0;
 ctx.drawImage(image,b,b,image.width,image.height);
 if(layout==='None'||layout==='Just a Frame')return size;
 const edge=Math.min(image.width,image.height),align=settings.align;
 const overlay=layout==='In the Photo';
 const mainColor=overlay?({white:'#fff',gray:'#aaa',black:'#111'}[settings.color]):ink;
 const subColor=overlay?mainColor:muted;
 const camera:Run[]=[];
 if(settings.showCamera&&(settings.model.trim()||settings.make.trim())){
  camera.push({text:'Shot on ',color:subColor});
  if(settings.model.trim())camera.push({text:settings.model.trim(),weight:600,color:mainColor});
  if(settings.make.trim())camera.push({text:(settings.model.trim()?' ':'')+settings.make.trim(),color:mainColor});
 }
 const parameters=settings.showParameters?[settings.focalLength,settings.fNumber,settings.exposureTime,settings.iso].map(x=>x.trim()).filter(Boolean).join('  '):'';
 const inset=edge*.035;
 const x=align==='left'?b+inset:align==='right'?size.width-b-inset:size.width/2;
 let y=b+image.height+edge*.052;
 if(overlay){y=image.height-edge*.082;ctx.shadowColor=settings.color==='black'?'#ffffff90':'#000000b0';ctx.shadowBlur=edge*.004;}
 line(ctx,camera,x,y,edge*.025,align,image.width-inset*2);
 line(ctx,[{text:parameters,color:subColor}],x,y+edge*.036,edge*.0175,align,image.width-inset*2);
 if(layout==='Banner'){
  const extra=[settings.lens,settings.date].filter(Boolean).join(' · ');
  line(ctx,[{text:extra,color:muted}],x,y+edge*.066,edge*.013,align,image.width-inset*2);
 }
 return size;
}
