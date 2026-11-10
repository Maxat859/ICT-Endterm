# Content Shield: Parser + Streamlit demo (team integration draft)

This update is for **Role 1 (Data Engineer)** and a **provisional** UI intended for Role 6 review. It does not replace the team's eventual final `app.py`, text classifier, or vision module.

## Supported inputs

- YouTube videos and Shorts — metadata, optional public comments, optional video download
- TikTok public video links — accessible video/metadata (no comments)
- Instagram public Reels/posts — accessible video/metadata (no comments)
- Local video files — MP4/MOV/MKV/WEBM/M4V

Some public posts may still be blocked by platform restrictions. Does not bypass logins, private accounts, CAPTCHAs or rate limits. Obtain permissions and respect platform terms and content licenses.

## Quick start (Windows, Python 3.12)

From the project root:

```cmd
python -m pip install -U yt-dlp streamlit
python parser.py demo.mp4
python parser.py "https://www.youtube.com/watch?v=jNQXAC9IVRw" --comments 3
python parser.py "https://www.youtube.com/watch?v=jNQXAC9IVRw" --download
streamlit run app.py
```

To download/convert videos, [FFmpeg](https://ffmpeg.org/) must be on PATH (`ffmpeg -version`). For voice/OCR, install the team dependencies (`requirements.txt`) and `av==18.1.0` if the installed Whisper/PyAV combination reports the previous `metadata_errors` error. The ML models download on first use.

## Function contract

```python
from parser import parse_url
result = parse_url(url_or_path, download_video=False, max_comments=0)
```

Returns dict keys: `source`, `source_url`, `title`, `description`, `text`, `comments`, `video_path`, `profile_data`, `metadata`, `warnings`.

`profile_data.has_avatar` and `profile_data.account_age_days` are **None** when unknown; these must not be treated as proof of fraud. For TikTok/Instagram, comments are not obtained via this parser. The current standalone app explicitly skips bot scoring for accounts with unknown age/avatar.

## Offline tests

```cmd
python -m unittest -v test_parser.py
python -m py_compile parser.py app.py
```

The tests use **synthetic mocked platform responses**, not real datasets; they establish interface correctness, not classification accuracy. Three real examples and ML metrics/confusion matrices must still be documented by the team before academic submission.

## Integration status

- `parser.py` → `video_to_text.video_to_text(path)` — designed to pass converted MP4 path, was also manually checked on a local MP4 before this update.
- `parser.py` → `antifraud.check_links(text)` — called in UI. Account scoring is deliberately skipped when inputs are unavailable.
- `text_check.py` and `vision_check.py` — **not in `main` at time this draft was prepared**; integration pending.
- `app.py` — **draft, not final team deliverable**, should be reviewed by Role 6.

## Module ownership

Role 1: parser.py and its parser tests. Role 6: app.py ownership/review. Do not upload copyrighted videos, large models, caches, or private user data to GitHub. Document source/license for any data included in submission.
