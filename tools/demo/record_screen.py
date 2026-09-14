"""Record a real local browser workspace running the CLI; cut only the idle wait.

The loopback server exposes a fixed file allowlist and two fixed subprocess commands.
It is a presentation tool, not a general remote shell. No environment file is served.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit

import imageio_ffmpeg
from playwright.async_api import async_playwright

PROJECT = Path(__file__).resolve().parents[2]
OUT = PROJECT / 'demo'
WORK = PROJECT / '.demo-work' / 'screen'
WORK.mkdir(parents=True, exist_ok=True)
HTML = Path(__file__).with_name('screen_workspace.html').read_bytes()
TIMELINE = json.loads((OUT/'screen-timeline.json').read_text(encoding='utf-8'))
TOTAL = sum(s['duration'] for s in TIMELINE)
assert 120 <= TOTAL <= 180
PYTHON = PROJECT / '.venv' / 'Scripts' / 'python.exe'
if not PYTHON.exists():
    PYTHON = Path(sys.executable)
browser_dir = PROJECT/'.venv'/'browsers'
if browser_dir.exists():
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(browser_dir))


class Workspace:
    def __init__(self, run_name: str):
        self.run_dir = 'output/'+run_name
        self.files = ['README.md', 'domains.json', 'main.py']
        self.files += ['company_intel/'+n+'.py' for n in
                       ['crawler','cleaner','extractor','schema','pipeline','nvidia']]
        self.files += ['requirements.txt', 'verify_outputs.py']
        self.files += [self.run_dir+'/'+n for n in
                       ['output.json','postman_com.json','supabase_com.json','vapi_ai.json','summary.md']]
        self.console = 'Ready to execute the Python CLI.\n'
        self.status = 'Ready'
        self.run_started = self.run_complete = self.verify_started = self.verify_complete = False
        self.run_exit = self.verify_exit = None
        self.process = None
        self.active_command = False
        self.lock = threading.Lock()

    def append(self, value: str):
        value = re.sub(r'nvapi-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}', '[REDACTED]', value)
        with self.lock:
            self.console += value

    def execute(self, action: str):
        with self.lock:
            if action == 'run' and not self.run_started:
                self.run_started = True
                args = ['main.py','--provider','nvidia','--free-tier-only',
                        '--domains-file','domains.json','--output-dir',self.run_dir]
            elif action == 'verify' and self.run_complete and self.run_exit == 0 and not self.verify_started:
                self.verify_started = True
                args = ['verify_outputs.py',self.run_dir]
            else:
                raise ValueError('Action is not available in the current process state')
            self.active_command = True
            self.status = 'Running pipeline' if action == 'run' else 'Validating artifacts'

        def worker():
            code = 1
            try:
                self.append('\nPS '+str(PROJECT)+'> .\\.venv\\Scripts\\python.exe '+' '.join(args)+'\n')
                env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
                flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                self.process = subprocess.Popen([str(PYTHON),*args],cwd=PROJECT,env=env,
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',
                    errors='replace',creationflags=flags)
                for line in self.process.stdout:
                    self.append(line)
                code = self.process.wait()
            except Exception as exc:
                self.append(f'Process error: {type(exc).__name__}\n')
            finally:
                self.append(f'\nProcess exited with code {code}\n')
                with self.lock:
                    self.active_command = False
                    if action == 'run':
                        self.run_complete, self.run_exit = True, code
                        self.status = 'Batch completed' if code == 0 else 'Batch incomplete — inspect output'
                    else:
                        self.verify_complete, self.verify_exit = True, code
                        self.status = 'Output validation passed' if code == 0 else 'Validation failed'
                (WORK/(action+'-terminal.txt')).write_text(self.console,encoding='utf-8')
        threading.Thread(target=worker,daemon=True).start()

    def state(self):
        with self.lock:
            return {key:getattr(self,key) for key in ['console','status','active_command','run_started',
                'run_complete','run_exit','verify_started','verify_complete','verify_exit']}


def handler_for(workspace):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):
            pass

        def reply(self, status, value, content_type='application/json'):
            content = value if isinstance(value,bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(content)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == '/':
                return self.reply(200,HTML,'text/html; charset=utf-8')
            if parsed.path == '/api/files':
                return self.reply(200,workspace.files)
            if parsed.path == '/api/status':
                return self.reply(200,workspace.state())
            if parsed.path == '/api/file':
                name = parse_qs(parsed.query).get('path',[''])[0]
                if name not in workspace.files:
                    return self.reply(403,{'error':'File is not in the demonstration allowlist'})
                path = PROJECT/name
                if not path.is_file():
                    return self.reply(404,{'error':'The file has not been generated yet'})
                return self.reply(200,{'text':path.read_text(encoding='utf-8-sig')})
            self.reply(404,{'error':'Not found'})

        def do_POST(self):
            if self.path!='/api/action' or self.headers.get('Content-Type')!='application/json':
                return self.reply(400,{'error':'Unsupported action'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<256: raise ValueError('Invalid body size')
                action=json.loads(self.rfile.read(size)).get('action')
                workspace.execute(action)
                self.reply(200,{'started':action})
            except (ValueError,TypeError):
                self.reply(400,{'error':'Action unavailable'})
    return Handler


async def record(workspace):
    server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(workspace))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    segments=[]
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True)
            context=await browser.new_context(viewport={'width':1920,'height':1080},
                record_video_dir=str(WORK/'raw'),record_video_size={'width':1920,'height':1080})
            page=await context.new_page()
            capture_start=time.monotonic()
            await page.goto(f'http://127.0.0.1:{server.server_port}/')
            await page.wait_for_function('window.ready === true')
            assert (await page.request.get(f'http://127.0.0.1:{server.server_port}/api/file?path=.env')).status==403
            bounds=await page.evaluate('''() => ({source:document.querySelector('#source').clientHeight,
                footer:document.querySelector('footer').getBoundingClientRect().bottom,
                scroll:document.querySelector('#source').scrollHeight})''')
            assert bounds['source'] < 700 and bounds['scroll'] > bounds['source'] and bounds['footer'] <= 1081, bounds
            scene_files = {'intro':('README.md',1), 'structure':('domains.json',1),
                'clean':('company_intel/cleaner.py',132),'schema':('company_intel/schema.py',17),
                'resilience':('company_intel/pipeline.py',91),
                'postman':(workspace.run_dir+'/postman_com.json',1),
                'coverage':(workspace.run_dir+'/output.json',1),'finish':(workspace.run_dir+'/summary.md',1)}
            for index, scene in enumerate(TIMELINE):
                sid=scene['id']
                if sid=='postman':
                    await page.evaluate("narration('Waiting for browser / API responses — this interval will be removed', '', .58)")
                    deadline=time.monotonic()+360
                    while not workspace.run_complete and time.monotonic()<deadline:
                        await asyncio.sleep(.4)
                    if not workspace.run_complete or workspace.run_exit!=0:
                        raise RuntimeError('The captured batch did not complete. Retain its evidence and retry with another --run-name.')
                    final=json.loads((PROJECT/workspace.run_dir/'summary.json').read_text(encoding='utf-8'))
                    assert final['complete'] and len(final['records'])==3
                scene_start=time.monotonic()
                print(f'Recording {sid}; run status: {workspace.status}',flush=True)
                await page.evaluate('terminalFocus(false)')
                if sid in scene_files:
                    path,line=scene_files[sid]
                    await page.locator(f'button[data-path="{path}"]').click()
                    await page.wait_for_function('(path)=>currentFile===path',arg=path)
                    if line>1:
                        await page.evaluate('(line)=>{document.querySelector("#source").scrollTop=(line-1)*32.34}',line)
                if sid in ['run','validation']:
                    await page.evaluate('terminalFocus(true)')
                    await page.locator('#run' if sid=='run' else '#verify').click()
                changed=False
                last_caption=None
                while (elapsed:=time.monotonic()-scene_start)<scene['duration']:
                    if elapsed>scene['duration']*.52 and not changed:
                        if sid=='postman':
                            text=(PROJECT/workspace.run_dir/'postman_com.json').read_text(encoding='utf-8')
                            line=next((i+1 for i,s in enumerate(text.splitlines()) if '"leadership"' in s),1)
                            await page.evaluate('(line)=>{document.querySelector("#source").scrollTop=(line-1)*32.34}',line)
                        elif sid=='coverage':
                            text=(PROJECT/workspace.run_dir/'output.json').read_text(encoding='utf-8')
                            data=json.loads(text)
                            # Navigate actual combined JSON to the next record and then Vapi.
                            line=next((i+1 for i,s in enumerate(text.splitlines()) if '"Supabase' in s),1)
                            await page.evaluate('(line)=>{document.querySelector("#source").scrollTop=(line-1)*32.34}',line)
                        changed=True
                    if sid=='coverage' and elapsed>scene['duration']*.76:
                        text=(PROJECT/workspace.run_dir/'output.json').read_text(encoding='utf-8')
                        line=next((i+1 for i,s in enumerate(text.splitlines()) if '"Vapi' in s),1)
                        await page.evaluate('(line)=>{document.querySelector("#source").scrollTop=(line-1)*32.34}',line)
                    caption=next((c['text'] for c in scene['captions'] if c['start']<=elapsed<c['end']),'')
                    if caption!=last_caption:
                        await page.evaluate('(args)=>narration(...args)',[f'{index+1:02d} / {scene["title"]}',caption,(scene['start']+elapsed)/TOTAL])
                        last_caption=caption
                    await asyncio.sleep(.10)
                if sid=='validation':
                    assert workspace.verify_complete and workspace.verify_exit==0,'Validation did not finish successfully during its scene'
                segments.append({'id':sid,'source_start':scene_start-capture_start,'duration':scene['duration']})
                await page.screenshot(path=str(WORK/f'{index:02d}-{sid}.png'))
            raw_video=page.video
            await page.close()
            await context.close()
            raw_path=await raw_video.path()
            await browser.close()
        info={'captured_at':datetime.now(timezone.utc).isoformat(),'raw_video':str(raw_path),
              'segments':segments,'duration_seconds':TOTAL,'run_directory':workspace.run_dir,
              'run_exit_code':workspace.run_exit,'validation_exit_code':workspace.verify_exit,
              'capture_method':'Playwright browser video of a local workspace with real files and subprocess stdout',
              'editing':'Idle waiting interval removed; scene order retained; synthetic narration added'}
        (OUT/'screen-recording-notes.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
        return Path(raw_path),segments
    finally:
        server.shutdown()
        server.server_close()
        if workspace.process and workspace.process.poll() is None:
            workspace.process.terminate()
            workspace.process.wait(timeout=20)


def finish_video(raw_video,segments):
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    clips=[]
    for i,segment in enumerate(segments):
        path=WORK/f'clip-{i:02d}.mp4'
        command=[ffmpeg,'-hide_banner','-loglevel','error','-y','-ss',str(segment['source_start']),
            '-i',str(raw_video),'-t',str(segment['duration']),'-an','-r','25','-c:v','libx264',
            '-pix_fmt','yuv420p','-preset','fast','-crf','20','-threads','3',str(path)]
        subprocess.run(command,check=True,timeout=90)
        clips.append(path)
        print(f'Encoded scene {i+1}/{len(segments)}',flush=True)
    concat=WORK/'concat.txt'
    concat.write_text('\n'.join("file '"+p.as_posix().replace("'","'\\''")+"'" for p in clips),encoding='utf-8')
    output=OUT/'company-intel-screen-recording.mp4'
    subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),
        '-i',str(WORK/'narration.wav'),'-c:v','copy','-c:a','aac','-b:a','128k','-ar','48000',
        '-af','loudnorm=I=-16:TP=-1.5:LRA=11','-t',str(TOTAL),'-movflags','+faststart',str(output)],check=True,timeout=60)
    cues=[]
    def timestamp(value):
        ms=round(value*1000)
        return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'
    transcript=[]
    for scene in TIMELINE:
        transcript += [f'{timestamp(scene["start"])} — {scene["title"]}',scene['narration'],'']
        for cue in scene['captions']:
            cues += [str(len(cues)//4+1),f'{timestamp(scene["start"]+cue["start"])} --> {timestamp(scene["start"]+cue["end"])}',cue['text'],'']
    (OUT/'company-intel-screen-recording.srt').write_text('\n'.join(cues),encoding='utf-8')
    (OUT/'screen-recording-transcript.txt').write_text('\n'.join(transcript),encoding='utf-8')
    print(f'Saved {output}; SHA256 {hashlib.sha256(output.read_bytes()).hexdigest()}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name',default='screen-demo')
    args=parser.parse_args()
    if not re.fullmatch(r'screen-demo(?:-[a-z0-9]+)?',args.run_name):
        parser.error('Use screen-demo or screen-demo-<suffix>')
    run_directory=PROJECT/'output'/args.run_name
    if run_directory.exists():
        parser.error('Use a new --run-name to preserve earlier run artifacts')
    raw,segments=asyncio.run(record(Workspace(args.run_name)))
    finish_video(raw,segments)
