# Project demonstration

[Watch or download the demonstration video](company-intel-demo.mp4).

The MP4 runs for **2 minutes 51 seconds**, at **1920 × 1080** with H.264 video,
AAC audio and 33 caption cues. Narration is synthetic, generated locally with Piper.
The visuals are rendered views of real source files and captured terminal/output
excerpts, with waiting time removed. This is an edited walkthrough, not a continuous
desktop recording or a hosted Loom link.

## Included files

| File | Purpose |
| --- | --- |
| [company-intel-demo.mp4](company-intel-demo.mp4) | Finished video with narration and visible captions |
| [company-intel-demo.srt](company-intel-demo.srt) | Separate subtitles for editors and players |
| [company-intel-demo-transcript.txt](company-intel-demo-transcript.txt) | Spoken narration and chapter times |
| [loom-demo-script.md](loom-demo-script.md) | Earlier guide for recording a walkthrough yourself |
| [company-intel-demo-notes.json](company-intel-demo-notes.json) | Source-run provenance and video construction notes |
| [company-intel-demo-checks.json](company-intel-demo-checks.json) | Duration, codecs, audio levels, full decode check and SHA-256 |
| [validation-terminal.txt](validation-terminal.txt) | Actual saved-output verifier stdout used for the video |
| [timeline.json](timeline.json) | Scene and caption timing for generation and validation |

The copied provenance/check files retain the original machine paths where the
recording was generated. In this repository, the video is in `demo/` and its
evidence is under the two run directories linked below.

## Run evidence shown in the video

- [Completed three-company batch](../output/video-demo-retry/summary.json): generated
  on 2026-09-14, with Postman, Supabase and Vapi all completed. Its
  [combined JSON](../output/video-demo-retry/output.json) contains the actual records.
- [Earlier partial attempt](../output/video-demo/summary.json): NVIDIA returned
  HTTP 500 for Postman while Supabase and Vapi completed. This is the failure-isolation
  example in the video; the error is retained in the [log](../output/video-demo/run.log).

The complete video batch recorded 7,770 input tokens and 758 output tokens, with
$0 estimated API cost using the configured NVIDIA free-tier rates. This does not
imply unlimited quota or permanent free access. Missing fields remain empty.

From the project root, validate the completed batch without a browser or API call:

```powershell
.\.venv\Scripts\python.exe verify_outputs.py output/video-demo-retry
```

## Optional video regeneration on Windows

The generation sources are in [`tools/demo/`](../tools/demo/). These are optional
presentation tools; the enrichment application needs only the main project setup.
The renderer uses Windows Segoe UI and Consolas fonts. Generation was exercised on
Windows with Python 3.14.2. It uses the bundled run evidence and does not call NVIDIA.

From the project root, after installing the main runtime requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r tools/demo/requirements.txt
New-Item -ItemType Directory -Path .demo-work -Force | Out-Null
Push-Location .demo-work
..\.venv\Scripts\python.exe -m piper.download_voices en_US-lessac-medium
Pop-Location
.\.venv\Scripts\python.exe tools/demo/make_narration.py
.\.venv\Scripts\python.exe tools/demo/render_video.py --encode
.\.venv\Scripts\python.exe tools/demo/check_video.py
```

Downloading dependencies and the voice model needs internet access. Synthesis and
rendering run locally. Temporary audio, frames and the voice model stay under
Git-ignored `.demo-work/`. The scripts regenerate the published files in `demo/`.
Speech timing may differ slightly between runs; the timeline is generated alongside
the narration. The renderer rejects a timeline over three minutes and checks that
the recorded evidence still matches statements in the narration.

To validate the existing MP4 without downloading a voice model or regenerating it:

```powershell
.\.venv\Scripts\python.exe -m pip install imageio-ffmpeg==0.6.0
.\.venv\Scripts\python.exe tools/demo/check_video.py
```

The standalone recording guide predates the edited MP4, so its narration and command
output directory differ. Follow the transcript and timeline to reproduce this MP4.

Voice tooling: [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)
and [voice model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD).
