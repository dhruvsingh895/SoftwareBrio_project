from pathlib import Path
import json
import re
import sys
import wave

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / '.demo-work'
OUT = PROJECT / 'demo'
ROOT.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)
from piper import PiperVoice, SynthesisConfig

SCENES = [
    ('intro', 'Autonomous lead enrichment', 13,
     'This is the Autonomous Lead Enrichment Agent. It turns company domains into structured business intelligence. This walkthrough shows actual project files and captured terminal results, with waiting time removed.'),
    ('structure', 'A modular Python pipeline', 14,
     'The project separates crawling, cleaning, extraction, and orchestration. A simple JSON file supplies the three assignment targets: Postman, Supabase, and Vapi. The README documents environment setup and local execution.'),
    ('run', 'Run the three target domains', 17,
     'The command selects NVIDIA and enables the free tier only guard. Playwright renders JavaScript pages and discovers relevant company links. These terminal excerpts come from a real run, with concurrent processing and up to eight attempted pages per company.'),
    ('clean', 'Clean evidence before inference', 16,
     'The cleaner removes scripts, styles, SVG elements, and navigation boilerplate. It extracts readable text while preserving contact signals and profile associations. A bounded context reduces token use. The language model receives clean evidence, rather than raw HTML trees.'),
    ('schema', 'A strict output contract', 16,
     'Pydantic defines the required fields: a two sentence overview, target audience, public emails, leadership details, and confidence between zero and one. The extractor validates the returned schema and checks that names, roles, and contact details have supporting evidence.'),
    ('resilience', 'Failures stay isolated', 17,
     'An earlier attempt encountered an NVIDIA server error for Postman. Supabase and Vapi still completed and saved their results. The pipeline records failures and uses bounded retries. Missing pages, browser timeouts, and bot challenges are also handled without cancelling other companies.'),
    ('postman', 'Inspect the extracted intelligence', 18,
     'Here is the actual Postman output from the completed batch. It contains the company overview, intended audience, public contact emails, and leadership profiles. Source pages and crawl errors remain attached, so a reviewer can inspect where the information came from.'),
    ('coverage', 'Show all three companies', 15,
     'The combined JSON contains records for all three targets. Missing information is left empty. In this evidence, Vapi has no supported leadership entries, and the optional Supabase profile search was blocked. Confidence reflects the completeness of the available evidence.'),
    ('validation', 'Validate the saved artifacts', 16,
     'The saved output verifier is run against this batch. It checks the schema, two sentence summaries, entity evidence, page limits, and token totals. The displayed validation is from an actual terminal execution, and all three records pass.'),
    ('finish', 'Usage, documentation, deliverables', 16,
     'The summary records actual token usage and estimated cost per domain. The zero dollar estimate uses the configured NVIDIA free tier rates. The project includes modular code, dependencies, tests, setup instructions, and a three company sample output. Thank you.'),
]

voice = PiperVoice.load(str(ROOT / 'en_US-lessac-medium.onnx'))
config = SynthesisConfig(length_scale=1.03, noise_scale=0.55, noise_w_scale=0.7)
audio_dir = ROOT / 'audio'
audio_dir.mkdir(exist_ok=True)
rate = 22050
timeline = []
full_audio = bytearray()
cursor = 0.0
for scene_id, title, minimum, narration in SCENES:
    scene_audio = bytearray(b'\0' * round(rate * 0.6) * 2)
    captions = []
    sentences = re.split(r'(?<=[.!?])\s+', narration)
    for sentence_index, sentence in enumerate(sentences):
        path = audio_dir / f'{scene_id}-{sentence_index}.wav'
        with wave.open(str(path), 'wb') as wav_file:
            voice.synthesize_wav(sentence, wav_file, syn_config=config)
        with wave.open(str(path), 'rb') as wav_file:
            assert wav_file.getnchannels() == 1 and wav_file.getsampwidth() == 2
            assert wav_file.getframerate() == rate
            pcm = wav_file.readframes(wav_file.getnframes())
        caption_start = len(scene_audio) / 2 / rate
        scene_audio.extend(pcm)
        captions.append({'start': caption_start, 'end': len(scene_audio) / 2 / rate, 'text': sentence})
        scene_audio.extend(b'\0' * round(rate * 0.12) * 2)
    natural = len(scene_audio) / rate / 2
    duration = max(minimum, natural + 0.8)
    target_bytes = round(duration * rate) * 2
    scene_audio.extend(b'\0' * (target_bytes - len(scene_audio)))
    duration = len(scene_audio) / 2 / rate
    timeline.append({'id': scene_id, 'title': title, 'narration': narration,
                     'start': cursor, 'duration': duration, 'captions': captions})
    full_audio.extend(scene_audio)
    cursor += duration
    print(f'{scene_id}: {duration:.2f}s', flush=True)

with wave.open(str(ROOT / 'narration.wav'), 'wb') as output:
    output.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
    output.writeframes(full_audio)
(OUT / 'timeline.json').write_text(json.dumps(timeline, indent=2), encoding='utf-8')
print(f'Total narration timeline: {cursor:.2f}s', flush=True)
