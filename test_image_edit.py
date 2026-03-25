"""测试图片编辑替换功能"""
import requests

# 测试替换编辑后的图片
def test_replace_edited_image():
    """测试图片替换 API"""
    
    # 模拟请求数据
    test_data = {
        "original_path": "static/uploads/test_image.jpg",
        "new_path": "static/uploads/watermark_removed/test_image_clean_123456.jpg"
    }
    
    try:
        response = requests.post(
            "http://localhost:8080/api/replace-edited-image",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        
        result = response.json()
        print(f"响应状态码：{response.status_code}")
        print(f"响应结果：{result}")
        
        if result.get('success'):
            print("✅ 图片替换成功！")
            print(f"最终路径：{result.get('final_path')}")
        else:
            print(f"❌ 图片替换失败：{result.get('message')}")
            
    except Exception as e:
        print(f"测试失败：{e}")

if __name__ == "__main__":
    print("=" * 50)
    print("开始测试图片编辑替换功能")
    print("=" * 50)
    
    # 注意：这个测试需要实际的文件存在
    # 在实际使用前，请确保文件路径正确
    print("\n提示：此测试需要实际的文件存在")
    print("请先上传一张图片并去除水印，然后再运行此测试")
    print("\n按 Ctrl+C 可随时退出测试")
    
    input("\n按 Enter 键开始测试...")
    test_replace_edited_image()
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)
