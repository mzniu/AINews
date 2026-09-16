# QA review videos

Committed Remotion vs Python comparison outputs for branch review.

| File | Description |
|---|---|
| `qa-venturebeat-gea_remotion_qa.mp4` | Remotion chronicle render with cover intro, GIF clip, BGM |
| `qa-venturebeat-gea_python_qa.mp4` | Python/MoviePy comparison render |
| `cjk-bgm-sample.mp4` | Noto Sans SC + background music sample |

Regenerate:

```bash
PYTHONPATH=/workspace python3 scripts/remotion_visual_qa.py
cd remotion && npm run render:bgm
```
