from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import wave

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / '.demo-work'
OUT = PROJECT / 'demo'
ROOT.mkdir(exist_ok=True)
import imageio_ffmpeg

ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
video = OUT / 'company-intel-demo.mp4'
probe = subprocess.run([ffmpeg, '-hide_banner', '-i', str(video)], capture_output=True, text=True)
metadata = probe.stderr
assert 'Video: h264' in metadata and '1920x1080' in metadata, metadata
assert 'Audio: aac' in metadata, metadata
duration = re.search(r'Duration: (\d+):(\d+):([\d.]+)', metadata)
assert duration, metadata
duration_seconds = int(duration[1])*3600 + int(duration[2])*60 + float(duration[3])
assert 120 <= duration_seconds <= 180, duration_seconds
decode = subprocess.run([ffmpeg, '-v', 'error', '-i', str(video), '-f', 'null', '-'],
                        capture_output=True, text=True, timeout=90)
assert decode.returncode == 0 and not decode.stderr.strip(), decode.stderr
audio = subprocess.run([ffmpeg, '-hide_banner', '-i', str(video), '-vn', '-af', 'volumedetect',
                        '-f', 'null', '-'], capture_output=True, text=True, timeout=45)
mean = re.search(r'mean_volume: ([\d.-]+) dB', audio.stderr)
peak = re.search(r'max_volume: ([\d.-]+) dB', audio.stderr)
assert mean and peak, audio.stderr[-1500:]
assert -40 < float(mean[1]) < -5 and -8 < float(peak[1]) <= 0
timeline = json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
assert abs(duration_seconds-sum(s['duration'] for s in timeline)) < .15
captions = (OUT/'company-intel-demo.srt').read_text(encoding='utf-8')
assert captions.count(' --> ') == sum(len(s['captions']) for s in timeline)
for stamp, name in [(5,'intro'), (77,'schema'), (112,'postman'), (150,'validation'), (166,'finish')]:
    result = subprocess.run([ffmpeg, '-hide_banner', '-loglevel','error','-y','-ss',str(stamp),
                             '-i',str(video),'-frames:v','1',str(ROOT/f'final-{name}.png')],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
report = {'video':str(video), 'duration_seconds':duration_seconds, 'resolution':'1920x1080',
          'video_codec':'H.264', 'audio_codec':'AAC', 'full_decode_passed':True,
          'mean_volume_db':float(mean[1]),'peak_volume_db':float(peak[1]),
          'caption_cues':captions.count(' --> '), 'size_bytes':video.stat().st_size,
          'sha256':hashlib.sha256(video.read_bytes()).hexdigest()}
(OUT/'company-intel-demo-checks.json').write_text(json.dumps(report, indent=2),encoding='utf-8')
print(json.dumps(report, indent=2))
