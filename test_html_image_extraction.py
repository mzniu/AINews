from src.utils.github_parser import ReadmeImageExtractor

# 测试包含HTML img标签的README内容
test_content = '''# Test Project

This is a test README with different image formats:

![Markdown Image](https://example.com/image1.png)

<img src="https://example.com/image2.jpg" alt="HTML Image" width="200">

Some text here...

![Another Markdown](images/local_image.gif "With title")

<img src="./assets/image3.svg" alt="Local SVG">
'''

print('测试内容包含:')
print('- 2个Markdown图片语法')
print('- 2个HTML img标签')
print()

# 创建提取器
extractor = ReadmeImageExtractor(
    'https://github.com/test/user', 
    'test', 'user', 'main'
)

# 提取图片
images = extractor.extract_images_from_markdown(test_content)

print(f'总共提取到 {len(images)} 张图片:')
for i, img in enumerate(images):
    print(f'{i+1}. ID: {img.id}')
    print(f'   URL: {img.url}')
    print(f'   Alt: {img.alt_text}')
    print(f'   Source: {img.source}')
    print()

# 验证提取结果
expected_count = 4
actual_count = len(images)

print('验证结果:')
if actual_count == expected_count:
    print(f'✅ 成功提取 {actual_count} 张图片!')
    print('✅ 支持Markdown和HTML两种图片格式')
else:
    print(f'❌ 期望提取 {expected_count} 张图片，实际提取 {actual_count} 张')