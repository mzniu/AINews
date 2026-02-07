from PIL import Image, ImageDraw

# 创建默认背景图（渐变紫色）
width, height = 1080, 1920
img = Image.new('RGB', (width, height), color=(102, 126, 234))

# 创建渐变效果
draw = ImageDraw.Draw(img)
for y in range(height):
    # 从紫色(102, 126, 234)渐变到深紫色(118, 75, 162)
    r = int(102 + (118 - 102) * y / height)
    g = int(126 + (75 - 126) * y / height)
    b = int(234 + (162 - 234) * y / height)
    draw.line([(0, y), (width, y)], fill=(r, g, b))

# 保存
img.save('static/imgs/bg.png')
print("✅ 默认背景图已创建: static/imgs/bg.png")
