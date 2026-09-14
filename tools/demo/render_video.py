from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / '.demo-work'
OUT = PROJECT / 'demo'
ROOT.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)
import imageio_ffmpeg

W, H, FPS = 1920, 1080, 15
BG, PANEL, EDGE = '#0a1220', '#111f31', '#284058'
TEXT, MUTED, TEAL, BLUE, AMBER = '#edf4fd', '#9fb1c6', '#62e4c5', '#88b9ff', '#ffd08a'
FONT_DIR = Path(r'C:\Windows\Fonts')
FONT_CACHE = {}

def font(size=26, kind='normal'):
    key = (size, kind)
    if key not in FONT_CACHE:
        name = {'normal': 'segoeui.ttf', 'bold': 'segoeuib.ttf', 'mono': 'consola.ttf'}[kind]
        FONT_CACHE[key] = ImageFont.truetype(str(FONT_DIR / name), size)
    return FONT_CACHE[key]

def label(draw, xy, text, size=26, color=TEXT, kind='normal'):
    draw.text(xy, text, font=font(size, kind), fill=color)

def wrap(draw, text, width, size=26, kind='normal'):
    result = []
    for original in str(text).splitlines() or ['']:
        words = original.split()
        line = ''
        for word in words:
            trial = f'{line} {word}'.strip()
            if line and draw.textlength(trial, font=font(size, kind)) > width:
                result.append(line)
                line = word
            else:
                line = trial
        result.append(line)
    return result

def paragraph(draw, xy, text, width, size=26, color=TEXT, kind='normal', spacing=1.4):
    x, y = xy
    for line in wrap(draw, text, width, size, kind):
        label(draw, (x, y), line, size, color, kind)
        y += size * spacing
    return y

def card(draw, box, fill=PANEL, outline=EDGE, radius=18):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)

def pill(draw, x, y, text, color=TEAL, fill='#173936', size=21):
    width = draw.textlength(text, font=font(size, 'bold')) + 32
    draw.rounded_rectangle((x, y, x+width, y+size+22), radius=12, fill=fill)
    label(draw, (x+16, y+7), text, size, color, 'bold')
    return width

TIMELINE = json.loads((OUT / 'timeline.json').read_text(encoding='utf-8'))
TOTAL = sum(s['duration'] for s in TIMELINE)
assert TOTAL <= 180, TOTAL

candidate = PROJECT / 'output' / 'video-demo-retry'
if not (candidate / 'summary.json').exists() or not json.loads((candidate / 'summary.json').read_text(encoding='utf-8')).get('complete'):
    candidate = PROJECT / 'output'
RUN = candidate
summary = json.loads((RUN / 'summary.json').read_text(encoding='utf-8'))
assert summary['complete']
run_relative = RUN.relative_to(PROJECT).as_posix()
run_date = summary['finished_at'][:10]
records = {record['domain']: record for record in summary['records']}
assert not records['vapi.ai']['leadership'], 'Update coverage narration for changed evidence'
search_evidence = json.loads((RUN/'evidence'/'supabase_com'/'crawl.json').read_text(encoding='utf-8'))
assert any(item['status']=='blocked' for item in search_evidence['linkedin_search']), 'Update search narration for changed evidence'
partial = json.loads((PROJECT / 'output' / 'video-demo' / 'summary.json').read_text(encoding='utf-8'))
assert not partial['complete']

project_python = PROJECT / '.venv' / 'Scripts' / 'python.exe'
if not project_python.exists():
    project_python = Path(sys.executable)
verify = subprocess.run([str(project_python),
                         str(PROJECT / 'verify_outputs.py'), str(RUN)],
                        cwd=PROJECT, capture_output=True, text=True, encoding='utf-8', timeout=60)
(ROOT / 'validation-terminal.txt').write_text(verify.stdout + verify.stderr, encoding='utf-8')
if verify.returncode:
    raise RuntimeError(f'Output validation failed: {verify.stderr[-1500:]}')
validation = json.loads(verify.stdout)[0]
assert validation['all_records_valid'] and len(validation['checks']) == 3

run_log = (RUN / 'run.log').read_text(encoding='utf-8-sig')
partial_log = (PROJECT / 'output' / 'video-demo' / 'run.log').read_text(encoding='utf-8-sig')
for content in [run_log, partial_log, verify.stdout]:
    assert not re.search(r'nvapi-[A-Za-z0-9_-]{15,}|gh[pousr]_[A-Za-z0-9]{20,}', content)

def shell_log_lines(content, limit=10):
    lines = []
    for line in content.splitlines():
        if ' Fetch ' in line or ' completed | ' in line or ' failed | ' in line:
            # Remove only repeated logger name/date, retaining the real timestamp and message.
            line = re.sub(r'^\d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2}),\d+ (INFO|WARNING|ERROR) company_intel\.[a-z]+ ', r'\1  ', line)
            lines.append(line)
    first = lines[:max(0, limit-3)]
    completed = [x for x in lines if ' completed | ' in x or ' failed | ' in x]
    return first + completed[-3:]

def header(scene, number):
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 112), fill='#0d1929')
    d.rounded_rectangle((48, 28, 100, 80), radius=14, fill=TEAL)
    label(d, (60, 34), 'CI', 27, '#09261f', 'bold')
    label(d, (120, 25), 'COMPANY INTEL', 29, TEXT, 'bold')
    label(d, (121, 64), 'Autonomous Lead Enrichment Agent', 18, MUTED)
    label(d, (1265, 29), 'PROJECT DEMONSTRATION', 22, MUTED, 'bold')
    label(d, (1265, 64), 'Synthetic narration  /  actual source and run artifacts', 18, MUTED)
    label(d, (52, 135), f'{number+1:02d}  /  {scene["title"]}', 38, TEXT, 'bold')
    d.line((52, 196, 1868, 196), fill=EDGE, width=2)
    d.rectangle((0, 960, W, H), fill='#070d17')
    return im

def code_panel(im, title, source_lines, start_line=1, box=(540, 228, 1868, 911), size=23, emphasis=()):
    d = ImageDraw.Draw(im)
    left, top, right, bottom = box
    card(d, box, '#0d1928')
    d.line((left, top+58, right, top+58), fill=EDGE, width=2)
    label(d, (left+24, top+14), title, 22, MUTED, 'mono')
    y = top+78
    available = right-left-108
    char_width = d.textlength('M', font=font(size, 'mono'))
    max_chars = math.floor(available / char_width)
    visual_index = 0
    for offset, original in enumerate(source_lines):
        # Wrap on screen without altering the source file.
        pieces = [original[i:i+max_chars] for i in range(0, max(1, len(original)), max_chars)]
        for part_index, line in enumerate(pieces):
            if y + size + 3 > bottom-20:
                raise ValueError(f'Code overflow in {title}, row {offset}, {len(source_lines)} lines')
            if start_line+offset in emphasis:
                d.rectangle((left+7, y-3, right-7, y+size+5), fill='#153d3e')
            line_number = str(start_line+offset) if part_index == 0 else '·'
            label(d, (left+20, y), line_number, size-2, '#627991', 'mono')
            x = left+83
            pattern = r'("[^"\n]*"|\x27[^\x27\n]*\x27|#[^\n]*|\b(?:class|def|return|for|if|else|in|from|import|True|False|None|async|await|with|or|and)\b|\b\d+(?:\.\d+)?\b)'
            previous = 0
            for match in re.finditer(pattern, line):
                before = line[previous:match.start()]
                label(d, (x, y), before, size, TEXT, 'mono')
                x += d.textlength(before, font=font(size, 'mono'))
                tok = match.group()
                color = TEAL if tok.startswith(('"', "'")) else MUTED if tok.startswith('#') else AMBER if tok[0].isdigit() else BLUE
                label(d, (x, y), tok, size, color, 'mono')
                x += d.textlength(tok, font=font(size, 'mono'))
                previous = match.end()
            label(d, (x, y), line[previous:], size, TEXT, 'mono')
            y += size+8
            visual_index += 1
    return y

def note_column(im, title, notes, footer=None):
    d = ImageDraw.Draw(im)
    label(d, (55, 248), title, 34, TEAL, 'bold')
    y = 325
    for heading, body in notes:
        d.rounded_rectangle((55, y+10, 61, y+40), radius=3, fill=TEAL)
        label(d, (81, y), heading, 26, TEXT, 'bold')
        y = paragraph(d, (81, y+46), body, 395, 23, MUTED) + 43
    if footer:
        paragraph(d, (55, 825), footer, 420, 20, MUTED)

def scene_image(scene, number, variant=0):
    im = header(scene, number)
    d = ImageDraw.Draw(im)
    sid = scene['id']
    if sid == 'intro':
        pill(d, 56, 240, 'PYTHON  /  PLAYWRIGHT  /  PYDANTIC')
        label(d, (54, 335), 'Company domains.', 74, TEXT, 'bold')
        label(d, (54, 430), 'Structured intelligence.', 74, TEAL, 'bold')
        paragraph(d, (58, 555), 'Public websites → clean evidence → validated JSON', 1180, 34, MUTED)
        x = 57
        for domain in ['postman.com', 'supabase.com', 'vapi.ai']:
            card(d, (x, 681, x+380, 800))
            label(d, (x+26, 715), domain, 35, TEXT, 'mono')
            x += 406
        label(d, (58, 866), 'Actual project files and captured runs  •  Waiting time removed', 25, MUTED)
    elif sid == 'structure':
        card(d, (55, 228, 597, 919))
        label(d, (82, 250), 'PROJECT  /  pr', 23, MUTED, 'bold')
        tree = ['company_intel/', '    crawler.py', '    cleaner.py', '    extractor.py', '    schema.py', '    pipeline.py', '    nvidia.py', 'main.py', 'domains.json', 'requirements.txt', 'README.md', 'tests/', 'output/']
        y = 312
        for line in tree:
            color = TEAL if line.strip() in ['domains.json', 'main.py'] else TEXT
            label(d, (87, y), line, 27, color, 'mono')
            y += 42
        code_panel(im, 'domains.json  •  actual input file', (PROJECT/'domains.json').read_text(encoding='utf-8').splitlines(), box=(650, 228, 1868, 535), size=31)
        d = ImageDraw.Draw(im)
        roles = [('crawler.py', 'Render and discover pages'), ('cleaner.py', 'Keep useful evidence'), ('extractor.py', 'Validate LLM output'), ('pipeline.py', 'Isolate failures and save results')]
        y = 580
        for filename, role in roles:
            label(d, (682, y), filename, 28, TEAL, 'mono')
            label(d, (1012, y), role, 27, TEXT)
            y += 83
    elif sid == 'run':
        card(d, (55, 228, 1868, 919), '#0a1725')
        label(d, (82, 246), f'POWERSHELL CAPTURE  /  {run_date}  /  excerpts, waiting removed', 24, MUTED)
        label(d, (85, 309), str(PROJECT), 23, MUTED, 'mono')
        command = rf'.\.venv\Scripts\python.exe main.py --provider nvidia --free-tier-only --domains-file domains.json --output-dir {run_relative}'
        y = paragraph(d, (85, 361), '> '+command, 1730, 25, TEAL, 'mono', 1.5)+24
        lines = shell_log_lines(run_log, 9)
        for line in lines[:(5 if variant == 0 else len(lines))]:
            shown = textwrap.wrap(line, width=130, subsequent_indent='          ')
            for part in shown:
                label(d, (86, y), part, 23, TEAL if 'completed' in part else TEXT, 'mono')
                y += 32
        pill(d, 1410, 857, 'FREE-TIER-ONLY')
    elif sid == 'clean':
        note_column(im, 'Before the LLM', [('Render', 'Headless Chromium executes page JavaScript.'), ('Filter', 'Remove scripts, styles, SVGs and navigation boilerplate.'), ('Budget', 'Clean text and contact signals fit within the context budget.')])
        lines = (PROJECT/'company_intel'/'cleaner.py').read_text(encoding='utf-8').splitlines()
        if variant == 0:
            code_panel(im, 'company_intel/cleaner.py  •  source excerpt', lines[131:145], start_line=132, size=23, emphasis=(139, 140, 141))
        else:
            context = (RUN/'evidence'/'postman_com'/'context.txt').read_text(encoding='utf-8')
            # First real evidence block, wrapped only for the video view.
            excerpt = []
            for line in context.splitlines():
                excerpt.extend(textwrap.wrap(line, 88) or [''])
                if len(excerpt) >= 17:
                    break
            code_panel(im, f'{run_relative}/evidence/postman_com/context.txt', excerpt[:17], size=24)
    elif sid == 'schema':
        note_column(im, 'Requested fields', [('Overview', 'Exactly two sentences, validated after extraction.'), ('Contacts and team', 'Public emails, names, roles and supported LinkedIn URLs.'), ('Confidence', 'Bounded from 0.0 to 1.0; reflects evidence completeness.')])
        lines = (PROJECT/'company_intel'/'schema.py').read_text(encoding='utf-8').splitlines()
        code_panel(im, 'company_intel/schema.py  •  actual Pydantic models', lines[15:32], start_line=16, size=24, emphasis=(27, 28, 29, 30, 31))
    elif sid == 'resilience':
        pill(d, 56, 227, 'EARLIER ATTEMPT  /  REAL PROVIDER FAILURE', AMBER, '#3b2d1d')
        card(d, (55, 297, 1868, 560), '#161c27')
        failure_lines = [line for line in partial_log.splitlines() if 'NVIDIA API HTTP 500' in line or 'Domain failed; batch continues' in line]
        label(d, (84, 320), 'Captured error', 23, MUTED, 'bold')
        y = 371
        for line in failure_lines:
            y = paragraph(d, (85, y), line, 1730, 27, AMBER, 'mono')+12
        x = 55
        for row in partial['domains']:
            color = TEAL if row['status'] == 'completed' else AMBER
            card(d, (x, 605, x+584, 839))
            label(d, (x+29, 633), row['domain'], 32, TEXT, 'mono')
            label(d, (x+29, 694), row['status'].upper(), 30, color, 'bold')
            label(d, (x+29, 752), f'{row["pages_crawled"]} pages  /  record saved', 24, MUTED)
            x += 615
        label(d, (58, 878), 'Provider error recorded  •  Other companies complete  •  Bounded retries', 27, MUTED)
    elif sid == 'postman':
        r = records['postman.com']
        note_column(im, 'Postman', [('Public contacts', f'{len(r["contact_points"])} email contacts in this record.'), ('Leadership', f'{len(r["leadership"])} supported team entries.'), ('Traceability', f'{len(r["pages_crawled"])} crawled pages, with errors and usage attached.')], f'Completed batch: {run_date}')
        if variant == 0:
            # This is a field selection, not a fabricated full JSON document.
            selected = {k:r[k] for k in ['company_overview', 'target_audience', 'contact_points']}
        else:
            selected = {k:r[k] for k in ['leadership', 'confidence_score']}
        lines = ['{']
        for field_index, (key, value) in enumerate(selected.items()):
            suffix = ',' if field_index < len(selected)-1 else ''
            if isinstance(value, list):
                lines.append(f'  "{key}": [')
                for item_index, item in enumerate(value):
                    lines.append('    '+json.dumps(item, ensure_ascii=False)+(',' if item_index<len(value)-1 else ''))
                lines.append('  ]'+suffix)
            else:
                lines.append(f'  "{key}": '+json.dumps(value, ensure_ascii=False)+suffix)
        lines.append('}')
        code_panel(im, f'{run_relative}/postman_com.json  •  selected fields', lines, size=23)
    elif sid == 'coverage':
        pill(d, 56, 228, f'COMPLETED BATCH  /  {run_date}')
        x = 55
        for domain in ['postman.com','supabase.com','vapi.ai']:
            r = records[domain]
            card(d, (x, 300, x+584, 733))
            label(d, (x+29, 330), domain, 34, TEXT, 'mono')
            pill(d, x+29, 389, 'COMPLETED')
            label(d, (x+29, 463), f'{len(r["contact_points"])} public contacts', 28, TEXT)
            label(d, (x+29, 512), f'{len(r["leadership"])} team entries', 28, TEXT)
            label(d, (x+29, 574), f'{r["confidence_score"]:.2f}', 67, TEAL, 'bold')
            label(d, (x+215, 611), 'confidence', 25, MUTED)
            x += 615
        card(d, (55, 776, 1868, 917))
        label(d, (86, 799), 'Missing information is preserved', 28, TEXT, 'bold')
        label(d, (86, 851), 'Vapi: no supported leadership  /  Supabase: optional profile search blocked', 28, MUTED)
    elif sid == 'validation':
        note_column(im, 'Checks pass', [('Schema', 'Required fields, strict types and confidence bounds.'), ('Evidence', 'Two-sentence summaries and literal entity evidence.'), ('Accounting', 'Page caps and actual generation token totals.')], 'Verifier executed for this video; no API call needed.')
        code_panel(im, 'TERMINAL  /  captured verifier stdout excerpt', verify.stdout.splitlines()[0:17], size=23)
        d = ImageDraw.Draw(im)
        d.rectangle((557, 834, 1847, 894), fill='#0d1928')
        label(d, (574, 849), f'Exit code: {verify.returncode}   |   All 3 records valid', 27, TEAL, 'mono')
        # The command is a compact footer; full invocation is preserved in video notes.
        label(d, (555, 925), f'python verify_outputs.py {run_relative}', 22, MUTED, 'mono')
    elif sid == 'finish':
        card(d, (55, 228, 1868, 611))
        label(d, (85, 250), f'ACTUAL USAGE  /  completed batch {run_date}', 24, MUTED, 'bold')
        columns = [(86,'Domain'),(580,'Pages'),(835,'Input tokens'),(1190,'Output tokens'),(1580,'Est. USD')]
        for x, heading in columns:
            label(d, (x, 321), heading, 25, MUTED, 'bold')
        for i, row in enumerate(summary['domains']):
            y = 379+i*65
            values = [row['domain'], str(row['pages_crawled']), f'{row["input_tokens"]:,}', f'{row["output_tokens"]:,}', f'${row["estimated_cost_usd"]:.2f}']
            for (x,_), value in zip(columns, values):
                label(d, (x,y), value, 28, TEAL if value.startswith('$') else TEXT, 'mono')
        label(d, (85, 557), 'Zero estimate uses configured NVIDIA free-tier rates; quotas still apply.', 24, MUTED)
        cards = [('SOURCE', 'Modular Python + tests'), ('SETUP', 'README + dependencies'), ('SAMPLE', 'Three-company JSON')]
        x=55
        for eyebrow, text in cards:
            card(d, (x, 652, x+584, 806))
            label(d, (x+26, 674), eyebrow, 21, TEAL, 'bold')
            label(d, (x+26, 721), text, 29, TEXT, 'bold')
            x+=615
        label(d, (56, 856), 'From public evidence to reviewable company intelligence.', 39, TEXT, 'bold')
    return im

def seconds_srt(seconds):
    ms = round(seconds*1000)
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'

def build_assets():
    slides = ROOT/'slides'
    slides.mkdir(exist_ok=True)
    for i, scene in enumerate(TIMELINE):
        variants = 2 if scene['id'] in ['run','clean','postman'] else 1
        for variant in range(variants):
            image = scene_image(scene, i, variant)
            image.save(slides/f'{i:02d}-{scene["id"]}-{variant}.png')
            print(f'Rendered {scene["id"]} variant {variant}', flush=True)
    srt = []
    transcript = ['Autonomous Lead Enrichment Agent — narration transcript', 'Synthetic narration. Actual source and run artifacts; waiting time removed.', '']
    for scene in TIMELINE:
        transcript.extend([f'{seconds_srt(scene["start"])} — {scene["title"]}', scene['narration'], ''])
        for caption in scene['captions']:
            srt.extend([str(len(srt)//4+1), f'{seconds_srt(scene["start"]+caption["start"])} --> {seconds_srt(scene["start"]+caption["end"])}', caption['text'], ''])
    (OUT/'company-intel-demo.srt').write_text('\n'.join(srt), encoding='utf-8')
    (OUT/'company-intel-demo-transcript.txt').write_text('\n'.join(transcript), encoding='utf-8')
    notes = {'duration_seconds':TOTAL, 'resolution':[W,H], 'fps':FPS, 'narration':'Synthetic, local Piper en_US-lessac-medium',
             'visuals':'Rendered source-file views and captured terminal/output excerpts; not a continuous desktop recording.',
             'completed_batch':str(RUN), 'completed_at':summary['finished_at'],
             'earlier_partial_batch':str(PROJECT/'output'/'video-demo'),
             'validation_command':[str(PROJECT/'.venv'/'Scripts'/'python.exe'),'verify_outputs.py',str(RUN)],
             'validation_exit_code':verify.returncode, 'all_records_valid':validation['all_records_valid'],
             'summary_sha256':hashlib.sha256((RUN/'summary.json').read_bytes()).hexdigest(),
             'narration_source':'https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md',
             'voice_model':'https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD'}
    (OUT/'company-intel-demo-notes.json').write_text(json.dumps(notes, indent=2), encoding='utf-8')

def encode():
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    output = OUT/'company-intel-demo.mp4'
    args = [ffmpeg,'-hide_banner','-y','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24',
            '-s',f'{W}x{H}','-r',str(FPS),'-i','-', '-i',str(ROOT/'narration.wav'),
            '-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p','-threads','3',
            '-c:a','aac','-b:a','128k','-af','loudnorm=I=-16:TP=-1.5:LRA=11',
            '-t',f'{TOTAL:.3f}','-movflags','+faststart',str(output)]
    with (ROOT/'ffmpeg-encode.log').open('w',encoding='utf-8') as log:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        last_image = None
        try:
            for index, scene in enumerate(TIMELINE):
                base = Image.open(ROOT/'slides'/f'{index:02d}-{scene["id"]}-0.png').convert('RGB')
                alternative = None
                if scene['id'] in ['run','clean','postman']:
                    alternative = Image.open(ROOT/'slides'/f'{index:02d}-{scene["id"]}-1.png').convert('RGB')
                first_frame = round(scene['start']*FPS)
                last_frame = round((scene['start']+scene['duration'])*FPS)
                print(f'Encoding {scene["id"]}: frames {first_frame}-{last_frame}',flush=True)
                for absolute_frame in range(first_frame,last_frame):
                    elapsed = absolute_frame/FPS-scene['start']
                    local_progress = elapsed/scene['duration']
                    active = alternative if alternative is not None and local_progress > .49 else base
                    im = active.copy()
                    if elapsed < .28 and last_image is not None:
                        im = Image.blend(last_image,im,max(0,min(1,elapsed/.28)))
                    d = ImageDraw.Draw(im)
                    cap = next((c for c in scene['captions'] if c['start'] <= elapsed < c['end']),None)
                    if cap:
                        lines=wrap(d,cap['text'],1700,27)
                        assert len(lines)<=3, lines
                        y = 974 + (3-len(lines))*13
                        for line in lines:
                            width=d.textlength(line,font=font(27))
                            label(d,((W-width)/2,y),line,27,TEXT)
                            y+=34
                    progress = absolute_frame/FPS/TOTAL
                    d.rectangle((0,H-5,round(W*progress),H),fill=TEAL)
                    process.stdin.write(im.tobytes())
                last_image=active.copy()
            process.stdin.close()
            code=process.wait(timeout=120)
            if code:
                raise RuntimeError(f'ffmpeg failed with {code}; inspect ffmpeg-encode.log')
        except BaseException:
            process.kill()
            process.wait()
            raise
    print(f'Saved {output} ({output.stat().st_size/1024/1024:.1f} MiB)',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--encode',action='store_true')
    args=parser.parse_args()
    build_assets()
    if args.encode:
        encode()
