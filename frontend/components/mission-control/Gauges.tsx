'use client';
import type {GaugeModel} from './model';

// Reusable instruments. Pure SVG/CSS: no chart library, no data fetching.
const R=26,C=2*Math.PI*R,ARC=0.75;
export const clamp=(v:number)=>Math.max(0,Math.min(1,v));
const label=(m:GaugeModel)=>`${m.label}: ${m.display}. ${m.sub}. ${m.tip} Opens ${m.target}.`;

export function ArcGauge({m,compact,onOpen}:{m:GaugeModel;compact?:boolean;onOpen:(m:GaugeModel)=>void}){
 const frac=m.value==null?0:clamp(m.value),angle=-135+270*frac;
 return <button type="button" className={`hud-instrument hud-arc tone-${m.tone}${compact?' compact':''}`} title={m.tip} aria-label={label(m)} onClick={()=>onOpen(m)}>
  <svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">
   <circle className="hud-track" cx="32" cy="32" r={R} strokeDasharray={`${C*ARC} ${C}`} transform="rotate(135 32 32)"/>
   <circle className="hud-fill" cx="32" cy="32" r={R} strokeDasharray={`${C*ARC*frac} ${C}`} transform="rotate(135 32 32)"/>
   {m.value!=null&&<g className="hud-needle" style={{transform:`rotate(${angle}deg)`,transformOrigin:'32px 32px'}}><line x1="32" y1="32" x2="32" y2="10"/><circle cx="32" cy="32" r="2.5"/></g>}
  </svg>
  <span className="hud-text"><small>{m.label}</small><strong>{m.display}</strong>{!compact&&<em>{m.sub}</em>}</span>
 </button>;
}

export function BarMeter({m,compact,onOpen}:{m:GaugeModel;compact?:boolean;onOpen:(m:GaugeModel)=>void}){
 const frac=m.value==null?0:clamp(m.value);
 return <button type="button" className={`hud-instrument hud-bar tone-${m.tone}${compact?' compact':''}`} title={m.tip} aria-label={label(m)} onClick={()=>onOpen(m)}>
  <span className="hud-text"><small>{m.label}</small><strong>{m.display}</strong>{!compact&&<em>{m.sub}</em>}</span>
  <span className="hud-bar-track" aria-hidden="true"><span className="hud-bar-fill" style={{width:`${Math.round(frac*100)}%`}}/></span>
 </button>;
}

export function StatusLight({m,compact,onOpen}:{m:GaugeModel;compact?:boolean;onOpen:(m:GaugeModel)=>void}){
 return <button type="button" className={`hud-instrument hud-light tone-${m.tone}${compact?' compact':''}`} title={m.tip} aria-label={label(m)} onClick={()=>onOpen(m)}>
  <span className={`hud-lamp${m.tone==='bad'||m.tone==='warn'?' pulse':''}`} aria-hidden="true"/>
  <span className="hud-text"><small>{m.label}</small><strong>{m.display}</strong>{!compact&&<em>{m.sub}</em>}</span>
 </button>;
}
