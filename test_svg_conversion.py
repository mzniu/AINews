import tempfile
from pathlib import Path

# 创建测试SVG文件
svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="200" height="100" xmlns="http://www.w3.org/2000/svg">
  <rect width="200" height="100" fill="#4CAF50"/>
  <text x="100" y="55" font-family="Arial" font-size="20" 
        fill="white" text-anchor="middle">Test SVG</text>
</svg>'''

with tempfile.NamedTemporaryFile(suffix='.svg', delete=False) as tmp:
    svg_path = Path(tmp.name)
    tmp.write(svg_content.encode('utf-8'))

print(f'创建测试SVG文件: {svg_path}')

# 测试转换
from services.github_image_service import ImageProcessor
result_path = ImageProcessor.convert_format(svg_path, 'PNG')

if result_path and result_path.exists():
    print(f'✅ SVG转PNG成功!')
    print(f'   原文件: {svg_path.name}')
    print(f'   新文件: {result_path.name}')
    print(f'   文件大小: {result_path.stat().st_size} bytes')
    
    # 清理测试文件
    svg_path.unlink()
    result_path.unlink()
else:
    print('❌ 转换失败')