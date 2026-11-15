'use client';
import {useEffect, useState} from 'react';
export type Placement = {x:number;y:number;zoom:number};
export const defaultPlacement:Placement={x:50,y:50,zoom:1};
// Retain the stored placement for compatibility, but do not crop any image.
export function bannerImageStyle(url:string,placement:Placement):React.CSSProperties {
 void placement;
 return {backgroundImage:`url("${url}")`,backgroundSize:'contain',backgroundPosition:'center',transform:'none'};
}
export default function BannerSettings({initial,hasBanner,version,onUpdate}:{initial:Placement;hasBanner:boolean;version:number;onUpdate:(value:Placement,changedImage:boolean)=>void}){
 const [file,setFile]=useState<File|null>(null),[preview,setPreview]=useState(''),[notice,setNotice]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview)},[preview]);
 const image=preview||(hasBanner?`/api/settings/banner?v=${version}`:'');
 async function imageUpdate(remove=false){setBusy(true);setNotice('');setError('');try{const data=new FormData();if(file)data.append('file',file);const response=await fetch('/api/settings/banner',{method:remove?'DELETE':'PUT',body:remove?undefined:data});const result=await response.json();if(!response.ok)throw Error(result.detail||'Could not save banner.');setNotice(remove?'Banner removed.':'Banner saved.');setFile(null);setPreview('');onUpdate(initial,true)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <div className="settings-body"><div className="gateway"><strong>Command center banner</strong><p className="field-hint">Upload a PNG, JPEG or WebP up to 8 MB. The entire image fits within the banner without cropping; unused space shows the background.</p><label htmlFor="banner-file">Banner image</label><input id="banner-file" type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>{const next=e.target.files?.[0]||null;setFile(next);setPreview(next?URL.createObjectURL(next):'')}}/><div className="gateway-actions"><button className="primary" disabled={!file||busy} onClick={()=>imageUpdate()}>Save banner</button><button className="secondary" disabled={busy||!hasBanner} onClick={()=>imageUpdate(true)}>Remove banner</button></div><div className="banner-preview" aria-label="Banner preview">{image&&<span className="banner-image" style={bannerImageStyle(image,initial)}/>}<span className="banner-shade"/><span className="banner-preview-title">✦ FUNK BOT ✦<small>TEAM COMMAND CENTER</small></span></div>{notice&&<div className="notice">{notice}</div>}{error&&<div className="error">{error}</div>}</div></div>
}
