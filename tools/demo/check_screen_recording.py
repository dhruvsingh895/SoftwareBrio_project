"""Validate the submitted screen recording, timing and the run it demonstrates."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

import imageio_ffmpeg

PROJECT = Path(__file__).resolve().parents[2]
OUT = PROJECT/'demo'
WORK = PROJECT/'.demo-work'/'screen'
WORK.mkdir(parents=True,exist_ok=True)
video = OUT/'company-intel-screen-recording.mp4'
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
probe = subprocess.run([ffmpeg,'-hide_banner','-i',str(video)],capture_output=True,text=True)
metadata = probe.stderr
assert 'Video: h264' in metadata and '1920x1080' in metadata and 'Audio: aac' in metadata, metadata
match = re.search(r'Duration: (\d+):(\d+):([\d.]+)',metadata)
assert match, metadata
duration = int(match[1])*3600+int(match[2])*60+float(match[3])
assert 120 <= duration <= 180
timeline=json.loads((OUT/'screen-timeline.json').read_text(encoding='utf-8'))
assert abs(duration-sum(s['duration'] for s in timeline))<.2
notes=json.loads((OUT/'screen-recording-notes.json').read_text(encoding='utf-8'))
assert notes['run_exit_code']==notes['validation_exit_code']==0
summary=json.loads((PROJECT/notes['run_directory']/'summary.json').read_text(encoding='utf-8'))
assert summary['complete'] and {r['domain'] for r in summary['records']}=={'postman.com','supabase.com','vapi.ai'}
assert summary['provider']=='nvidia' and summary['free_tier_only'] and summary['total_estimated_cost_usd']==0
decoded=subprocess.run([ffmpeg,'-v','error','-i',str(video),'-f','null','-'],capture_output=True,text=True,timeout=90)
assert decoded.returncode==0 and not decoded.stderr.strip(),decoded.stderr
audio=subprocess.run([ffmpeg,'-hide_banner','-i',str(video),'-vn','-af','volumedetect','-f','null','-'],
                      capture_output=True,text=True,timeout=45)
mean=re.search(r'mean_volume: ([\d.-]+) dB',audio.stderr)
peak=re.search(r'max_volume: ([\d.-]+) dB',audio.stderr)
assert mean and peak and -40<float(mean[1])<-5 and -8<float(peak[1])<=0
captions=(OUT/'company-intel-screen-recording.srt').read_text(encoding='utf-8')
assert captions.count(' --> ')==sum(len(s['captions']) for s in timeline)
for scene in timeline:
    if scene['id'] in {'run','schema','postman','coverage','validation','finish'}:
        stamp=scene['start']+scene['duration']*.6
        subprocess.run([ffmpeg,'-v','error','-y','-ss',str(stamp),'-i',str(video),'-frames:v','1',
                        str(WORK/f'final-{scene["id"]}.png')],check=True,timeout=20)
report={'video':'demo/'+video.name,'duration_seconds':duration,'resolution':'1920x1080',
        'video_codec':'H.264','audio_codec':'AAC','full_decode_passed':True,
        'mean_volume_db':float(mean[1]),'peak_volume_db':float(peak[1]),
        'caption_cues':captions.count(' --> '),'run_directory':notes['run_directory'],
        'run_complete':True,'run_and_validation_exit_codes':[0,0],
        'size_bytes':video.stat().st_size,'sha256':hashlib.sha256(video.read_bytes()).hexdigest()}
(OUT/'screen-recording-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
