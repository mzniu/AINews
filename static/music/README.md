# 背景音乐目录 / Background music

## Python pipeline (default)

Place loopable MP3 files here. The ingestion pipeline picks from this directory via `bgm_picker`.

- Recommended: MP3, 30s+ loop
- Default fallback: `static/music/background.mp3`

## Remotion test BGM

Upload a test track for Remotion renders:

```
remotion/public/static/music/test-bgm.mp3
```

(same file as `static/music/test-bgm.mp3` when `remotion/public/static` symlink is present)

Render with audio:

```bash
cd remotion && npm run render:bgm
```

If missing, `scripts/remotion_visual_qa.py` generates a short sine-wave MP3 via ffmpeg.
