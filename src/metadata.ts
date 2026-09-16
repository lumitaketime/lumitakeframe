import exifr from 'exifr';

export interface ExifData {
 Make?:string; Model?:string; FocalLength?:string; FNumber?:string;
 ExposureTime?:string; ISO?:string; LensModel?:string; CreateDate?:string;
}
interface Header {byteLength:number;getUint32(n:number):number;getString(n:number,count:number):string}
const heifBrands=new Set(['heic','heix','hevc','hevx','heim','heis','hevm','hevs']);
export function supportsHeif(header:Header):boolean {
 if(header.byteLength<16||header.getString(4,4)!=='ftyp')return false;
 const size=header.getUint32(0);
 if(size<16||size%4)return false;
 if(heifBrands.has(header.getString(8,4)))return true;
 for(let position=16;position+4<=Math.min(size,header.byteLength);position+=4){
  if(heifBrands.has(header.getString(position,4)))return true;
 }
 return false;
}
// Keep exifr's licensed parser, but replace its obsolete 50-byte ftyp limit.
const LibraryParser=exifr.fileParsers.get('heic');
class ModernHeifParser extends LibraryParser {static canHandle(header:Header){return supportsHeif(header)}}
exifr.fileParsers.set('heic',ModernHeifParser);
const positive=(v:unknown)=>{const n=Number(v);return Number.isFinite(n)&&n>0?n:undefined};
const text=(v:unknown)=>typeof v==='string'&&v.trim()?v.trim():undefined;
const rounded=(n:number)=>Math.round(n*100)/100;
export function formatMetadata(raw:Record<string,unknown>|undefined):ExifData {
 if(!raw)return {};
 const result:ExifData={};
 const make=text(raw.Make),model=text(raw.Model),lens=text(raw.LensModel);
 if(make)result.Make=make;if(model)result.Model=model;if(lens)result.LensModel=lens;
 const focal=positive(raw.FocalLength),aperture=positive(raw.FNumber),speed=positive(raw.ExposureTime),iso=positive(raw.ISO);
 if(focal)result.FocalLength=`${rounded(focal)}mm`;
 if(aperture)result.FNumber=`f/${Number.isInteger(aperture)?aperture.toFixed(1):rounded(aperture)}`;
 if(speed)result.ExposureTime=speed<1?`1/${Math.round(1/speed)}s`:`${rounded(speed)}s`;
 if(iso)result.ISO=`ISO${Math.round(iso)}`;
 const date=raw.DateTimeOriginal??raw.CreateDate;
 if(date instanceof Date&&!Number.isNaN(date.getTime()))result.CreateDate=date.toISOString();
 return result;
}
export async function loadExif(input:File|Uint8Array):Promise<ExifData> {
 const tags=await exifr.parse(input);
 return formatMetadata(tags);
}
