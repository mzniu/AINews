# AI News — Remotion Video Renderer

Remotion replaces the Python/MoviePy slideshow path for ingested article videos.

## Prerequisites

- Node.js 18+
- `npm install` in this directory
- Chrome/Chromium (system `google-chrome` works in cloud VMs with sandbox flags)

## BGM

Built-in featured track: `static/music/Memories.mp3` (tracked in Git).

`remotion/public/static` symlinks to repo `static/`, so Remotion reads the same path.
QA and `npm run render:bgm` use `test-bgm.mp3` → `Memories.mp3`.

```bash
cd remotion && npm run render:bgm
```

## Quick start

```bash
cd remotion
npm install
export REMOTION_CHROME_ARGS="--no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage"

# Preview in Remotion Studio
npm start

# Render sample chronicle composition
npm run render:sample
# output: remotion/out/sample.mp4
```

## Compositions

| ID | Layout | Python equivalent |
|---|---|---|
| `ChronicleVideo` | `chronicle_frame` | `services/ingestion/chronicle_render.py` |
| `ClassicOverlayVideo` | `classic_overlay` | `api/routes/video_routes.py` `_create_animated_video_blocking` |

## Props

Pass JSON via `--props=path/to/props.json`. See `sample-props.json`.

Image paths should be repo-relative (`static/imgs/...`) or are staged automatically by
`services/ingestion/remotion_render_service.py` into `public/runtime/<article_id>/`.

## Ingestion pipeline (production default)

Remotion is the **default** renderer for `render_ingested_video()`.

Override to Python/MoviePy:

```bash
export VIDEO_RENDERER=python
# or pass renderer="python" to render_ingested_video()
```

If Remotion dependencies are missing or a render fails, the pipeline falls back to Python automatically.
