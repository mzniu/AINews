"""查看最近抓取结果的图片状态"""
import json

with open('data/fetched/358f5179_20260208_000026/metadata.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"总图片数: {data['images_count']}")
print(f"图片列表: {len(data['images'])} 条\n")

for img in data['images']:
    url = img['url'][:100]
    ok = img['success']
    err = img.get('error', '')
    print(f"{'OK' if ok else 'FAIL'}  {url}")
    if err:
        print(f"      错误: {err}")
