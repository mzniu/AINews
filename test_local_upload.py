"""
测试本地图片上传功能
"""

import requests
import os
from pathlib import Path

def test_local_image_upload():
    """测试本地图片上传功能"""
    print("🔍 测试本地图片上传功能")
    print("=" * 40)
    
    # 准备测试图片
    test_image_path = "test_upload_image.jpg"
    
    # 创建一个简单的测试图片
    try:
        from PIL import Image, ImageDraw
        # 创建一个红色的测试图片
        img = Image.new('RGB', (200, 200), color='red')
        draw = ImageDraw.Draw(img)
        draw.text((50, 90), "Test Image", fill='white')
        img.save(test_image_path)
        print(f"✅ 创建测试图片: {test_image_path}")
    except ImportError:
        print("❌ PIL库未安装，跳过图片创建")
        return False
    except Exception as e:
        print(f"❌ 创建测试图片失败: {e}")
        return False
    
    # 测试上传API
    try:
        url = "http://localhost:8080/api/upload-local-image"
        
        with open(test_image_path, 'rb') as f:
            files = {'image': (test_image_path, f, 'image/jpeg')}
            response = requests.post(url, files=files)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ 上传API测试成功")
                print(f"   上传路径: {result.get('image_path')}")
                print(f"   文件名: {result.get('filename')}")
                print(f"   文件大小: {result.get('size')} bytes")
                
                # 验证文件是否存在
                uploaded_path = result.get('image_path', '').lstrip('/')
                if os.path.exists(uploaded_path):
                    print("✅ 上传文件存在")
                    return True
                else:
                    print("❌ 上传文件不存在")
                    return False
            else:
                print(f"❌ 上传失败: {result.get('message')}")
                return False
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            print(f"   响应: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器，请确保服务正在运行")
        return False
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        return False
    finally:
        # 清理测试文件
        if os.path.exists(test_image_path):
            os.remove(test_image_path)
            print(f"🧹 已删除测试文件: {test_image_path}")

def test_frontend_integration():
    """测试前端集成"""
    print("\n🔍 测试前端集成")
    print("=" * 40)
    
    try:
        response = requests.get("http://localhost:8080/")
        if response.status_code == 200:
            content = response.text
            # 检查关键元素是否存在
            checks = [
                ('上传本地图片按钮', '上传本地图片' in content),
                ('文件输入控件', 'localImageInput' in content),
                ('上传状态显示', 'uploadStatus' in content),
                ('本地上传标记', 'local-upload-badge' in content),
                ('上传处理函数', 'handleLocalImageUpload' in content)
            ]
            
            all_passed = True
            for check_name, passed in checks:
                status = "✅" if passed else "❌"
                print(f"   {status} {check_name}")
                if not passed:
                    all_passed = False
            
            return all_passed
        else:
            print(f"❌ 无法访问主页: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 前端测试失败: {e}")
        return False

if __name__ == "__main__":
    print("🧪 本地图片上传功能测试")
    print("=" * 50)
    
    # 测试API功能
    api_success = test_local_image_upload()
    
    # 测试前端集成
    frontend_success = test_frontend_integration()
    
    print(f"\n🏁 最终结果:")
    print(f"   API功能: {'✅ 成功' if api_success else '❌ 失败'}")
    print(f"   前端集成: {'✅ 成功' if frontend_success else '❌ 失败'}")
    
    if api_success and frontend_success:
        print("\n🎉 所有测试通过！本地图片上传功能已就绪。")
        print("现在可以在网页中上传本地图片作为视频素材了。")
    else:
        print("\n⚠️  部分测试失败，请检查相关配置。")