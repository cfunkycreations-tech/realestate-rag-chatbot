"""Unprivileged persistent Playwright browser for one isolated computer session.

Direct external traffic is unavailable. HTTPS is sent only through the
owner-allowlisted, individually approved backend network broker.
"""
import json
import os
import sys
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright

WORKSPACE = Path('/workspace').resolve()
MAX_TEXT = 4000


def allowed_url(value):
    if value == 'about:blank': return True
    try:
        u=urlsplit(value)
        if u.scheme != 'file' or u.netloc not in ('', 'localhost'): return False
        path=Path(unquote(u.path)).resolve()
        return path==WORKSPACE or WORKSPACE in path.parents
    except (ValueError,OSError): return False


def perform(page, action):
    if not isinstance(action,dict) or not isinstance(action.get('type'),str): raise ValueError('Invalid action.')
    kind=action['type']
    if kind=='open_url' and set(action)=={'type','url'}:
        url=action['url']
        if not isinstance(url,str) or len(url)>2048 or not (allowed_url(url) or urlsplit(url).scheme=='https'): raise ValueError('Only workspace file URLs, about:blank and approved HTTPS sites are available.')
        page.goto(url,wait_until='domcontentloaded',timeout=10000)
    elif kind=='click' and set(action)=={'type','x','y'}:
        x,y=action['x'],action['y']
        if type(x) is not int or type(y) is not int or not (0<=x<1024 and 0<=y<768): raise ValueError('Invalid click coordinates.')
        subprocess.run(['xdotool','mousemove','--sync',str(x),str(y),'click','1'],timeout=3,check=True)
    elif kind=='type' and set(action)=={'type','text'}:
        text=action['text']
        if not isinstance(text,str) or not 1<=len(text)<=2000 or '\x00' in text: raise ValueError('Invalid text.')
        page.keyboard.insert_text(text)
    elif kind=='key' and set(action)=={'type','key'}:
        key=action['key']
        if key not in ('Enter','Tab','Escape','Backspace','Delete','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown','Control+A','Control+L','Control+C','Control+V'): raise ValueError('Invalid key.')
        page.keyboard.press(key)
    elif kind=='scroll' and set(action)=={'type','delta_x','delta_y'}:
        x,y=action['delta_x'],action['delta_y']
        if type(x) is not int or type(y) is not int or abs(x)>2000 or abs(y)>2000: raise ValueError('Invalid scroll.')
        page.mouse.wheel(x,y)
    elif kind in ('click_selector','fill'):
        expected={'type','selector'} if kind=='click_selector' else {'type','selector','text'}
        if set(action)!=expected or not isinstance(action['selector'],str) or not 1<=len(action['selector'])<=512: raise ValueError('Invalid selector.')
        if kind=='click_selector': page.locator(action['selector']).first.click(timeout=5000)
        else:
            if not isinstance(action['text'],str) or len(action['text'])>2000 or '\x00' in action['text']: raise ValueError('Invalid text.')
            page.locator(action['selector']).first.fill(action['text'],timeout=5000)
    elif kind=='extract_text' and set(action)=={'type'}:
        return {'text':page.locator('body').inner_text(timeout=5000)[:MAX_TEXT]}
    elif kind=='screenshot' and set(action)=={'type'}: pass
    else: raise ValueError('Invalid action.')
    return {}


def main():
    os.environ.setdefault('HOME','/tmp')
    with sync_playwright() as playwright:
        proxy_port=int(os.environ['FUNK_BROWSER_PROXY_PORT'])
        browser=playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=False,args=['--no-sandbox','--disable-dev-shm-usage','--disable-background-networking','--disable-quic','--disable-http2','--no-first-run',f'--proxy-server=http://127.0.0.1:{proxy_port}','--proxy-bypass-list=<-loopback>'])
        context=browser.new_context(viewport={'width':1024,'height':768},service_workers='block',accept_downloads=False)
        def route_request(route):
            if allowed_url(route.request.url) or urlsplit(route.request.url).scheme=='https': route.continue_()
            else: route.abort()
        context.route('**/*',route_request)
        page=context.new_page();page.goto('about:blank')
        print(json.dumps({'ready':True}),flush=True)
        for line in sys.stdin:
            if len(line)>12000: break
            try:
                action=json.loads(line);result=perform(page,action)
                print(json.dumps({'ok':True,'result':result},ensure_ascii=True),flush=True)
            except Exception as exc:
                print(json.dumps({'ok':False,'error':str(exc)[:1000]},ensure_ascii=True),flush=True)
        browser.close()


if __name__=='__main__': main()
