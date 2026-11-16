'use client';
import {useState} from 'react';
export const THEMES=[{"id": "emerald", "name": "Obsidian Emerald", "c": "#12e68f", "a": "#1fa2ff", "s": "#030907", "l": "18,230,143", "n": "#eef7ff"}, {"id": "violet", "name": "Ultraviolet", "c": "#a56bff", "a": "#ff4df0", "s": "#07040d", "l": "165,107,255", "n": "#f3eeff"}, {"id": "crimson", "name": "Crimson Noir", "c": "#ff3355", "a": "#ff9a3d", "s": "#0b0305", "l": "255,51,85", "n": "#fff0f2"}, {"id": "ice", "name": "Arctic Ice", "c": "#7fdcff", "a": "#e6f9ff", "s": "#030a0e", "l": "127,220,255", "n": "#f4fbff"}, {"id": "gold", "name": "Solar Gold", "c": "#ffc933", "a": "#ff7a1a", "s": "#0a0702", "l": "255,201,51", "n": "#fff8e6"}, {"id": "magenta", "name": "Neon Magenta", "c": "#ff3df0", "a": "#35e8ff", "s": "#0a030a", "l": "255,61,240", "n": "#fff0fd"}, {"id": "lime", "name": "Toxic Lime", "c": "#b8ff1f", "a": "#00e0c6", "s": "#060a02", "l": "184,255,31", "n": "#f6ffe6"}, {"id": "ocean", "name": "Deep Ocean", "c": "#2d9bff", "a": "#00e5ff", "s": "#02060d", "l": "45,155,255", "n": "#eaf5ff"}, {"id": "rose", "name": "Rose Quartz", "c": "#ff94bd", "a": "#ffe0ee", "s": "#0a0508", "l": "255,148,189", "n": "#fff2f7"}, {"id": "chrome", "name": "Mirror Chrome", "c": "#cfd8e3", "a": "#ffffff", "s": "#050607", "l": "207,216,227", "n": "#ffffff"}] as const;
export const THEME_KEY='funkbot-theme';
export function applyTheme(id:string){
  try{document.documentElement.dataset.theme=id;localStorage.setItem(THEME_KEY,id)}catch{document.documentElement.dataset.theme=id}
}
export default function ThemePicker(){
  const [active,setActive]=useState(()=>{try{return document.documentElement.dataset.theme||localStorage.getItem(THEME_KEY)||'emerald'}catch{return 'emerald'}});
  return <div className="settings-body" style={{maxHeight:'none',overflow:'visible'}}>
    <strong>Theme</strong>
    <p className="field-hint">Every theme is black glass catching a light source. Pick one and it applies instantly and is remembered on this device.</p>
    <div className="theme-grid" role="radiogroup" aria-label="Theme">
      {THEMES.map(t=><button key={t.id} role="radio" aria-checked={active===t.id} className={`theme-tile ${active===t.id?'active':''}`} onClick={()=>{applyTheme(t.id);setActive(t.id)}}
        style={{'--tc':t.c,'--ta':t.a,'--ts':t.s,'--tl':t.l,'--tn':t.n} as React.CSSProperties}>
        <span className="theme-preview"><b/><i/></span><strong>{t.name}</strong>
      </button>)}
    </div>
  </div>;
}
