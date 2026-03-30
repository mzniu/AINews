"""Split static/js/index/_full.js into state + main + modal + init. Run: python scripts/split_index_js.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
full = (ROOT / "static/js/index/_full.js").read_text(encoding="utf-8")
lines = full.splitlines(keepends=True)

# Remove edited* + dragSrcEl block (original lines 19-26, 0-based 18-26)
del lines[18:26]

text = "".join(lines)
text = text.replace("path: gifPath,", "path: imgObj.path,")

# Fix createVideo() catch: progressInterval undefined here
old_catch = """            } catch (error) {
                // 隐藏进度条
                clearInterval(progressInterval);
                if (document.getElementById('videoProgress')) {
                    document.body.removeChild(document.getElementById('videoProgress'));
                }
                
                console.error('视频生成错误:', error);
                showToast('视频生成失败: ' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '🎬 合成视频 (带背景音乐)';
            }
        }

        async function oneClickGenerate()"""
new_catch = """            } catch (error) {
                console.error('视频生成错误:', error);
                showToast('视频生成失败: ' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '🎬 合成视频 (带背景音乐)';
            }
        }

        async function oneClickGenerate()"""
if old_catch in text:
    text = text.replace(old_catch, new_catch)
else:
    print("WARN: createVideo catch pattern not found")

lines = text.splitlines(keepends=True)

# Split indices (after removal): main ends after urlInput keypress (inclusive through line with `});` after keypress)
# Find "// ===== 图片查看器"
join_main = None
join_modal = None
for i, ln in enumerate(lines):
    if ln.strip().startswith("// ===== 图片查看器"):
        join_main = i
        break
if join_main is None:
    raise SystemExit("split marker not found")

# Find "// 页面加载完成后初始化" after modal block
for i, ln in enumerate(lines):
    if i > join_main and ln.strip() == "// 页面加载完成后初始化":
        join_modal = i
        break
if join_modal is None:
    raise SystemExit("init marker not found")

main_lines = lines[:join_main]
modal_lines = lines[join_main:join_modal]
init_lines = lines[join_modal:]

state = """        let currentData = null;
        let selectedImages = [];
        let generatedTitle = '';
        let generatedSummary = '';
        let editedMainTitle = '';
        let editedSubTitle = '';
        let editedSummary = '';
        let editedTags = '';
        let dragSrcEl = null;

"""

(ROOT / "static/js/index/state.js").write_text(state, encoding="utf-8")
(ROOT / "static/js/index/main.js").write_text("".join(main_lines), encoding="utf-8")
(ROOT / "static/js/index/modal.js").write_text("".join(modal_lines), encoding="utf-8")
(ROOT / "static/js/index/init.js").write_text("".join(init_lines), encoding="utf-8")
print("main", len(main_lines), "modal", len(modal_lines), "init", len(init_lines))
