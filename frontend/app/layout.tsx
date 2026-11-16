import '@fontsource/audiowide/400.css';
import '@fontsource-variable/orbitron';
import '@fontsource-variable/jetbrains-mono';
import './globals.css';
import type { Metadata } from 'next';
export const metadata: Metadata = { title: 'Funk Bot', description: 'A little more room to think.', manifest: '/manifest.webmanifest' };
const themeScript = "try{var t=localStorage.getItem('funkbot-theme');if(t)document.documentElement.dataset.theme=t}catch(e){}";
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{__html:themeScript}}/></head><body>{children}</body></html>; }
