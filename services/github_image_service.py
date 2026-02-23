"""
GitHub图片处理服务
负责下载、验证和管理从GitHub项目中提取的图片
"""
import os
import requests
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image
from io import BytesIO
from loguru import logger
from src.models.github_models import ProjectImage


class ImageDownloader:
    """图片下载器"""
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AINews-GitHub-Image-Downloader'
        })
    
    def download_image(self, image: ProjectImage, save_path: Path) -> bool:
        """
        下载单张图片
        返回: 是否下载成功
        """
        try:
            # 确保保存目录存在
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 下载图片
            for attempt in range(self.max_retries):
                try:
                    response = self.session.get(
                        str(image.url), 
                        timeout=self.timeout,
                        stream=True
                    )
                    response.raise_for_status()
                    
                    # 保存图片
                    with open(save_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    # 验证图片完整性
                    if self._validate_image(save_path):
                        # 获取图片信息
                        img_info = self._get_image_info(save_path)
                        image.local_path = save_path
                        image.width = img_info['width']
                        image.height = img_info['height']
                        image.size = img_info['size']
                        return True
                    else:
                        # 图片损坏，删除文件
                        save_path.unlink(missing_ok=True)
                        
                except requests.RequestException as e:
                    logger.warning(f"下载图片失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                    if attempt == self.max_retries - 1:
                        raise
                        
        except Exception as e:
            logger.error(f"下载图片失败 {image.url}: {e}")
            
        return False
    
    def _validate_image(self, image_path: Path) -> bool:
        """验证图片文件是否完整"""
        try:
            # 检查文件是否存在且不为空
            if not image_path.exists() or image_path.stat().st_size == 0:
                return False
            
            # 对于SVG文件，只需要检查是否能被解析
            if image_path.suffix.lower() == '.svg':
                try:
                    with open(image_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # 简单检查是否包含SVG标签
                        return '<svg' in content.lower()
                except:
                    return False
            
            # 对于其他图片格式，使用PIL验证
            with Image.open(image_path) as img:
                img.verify()
            return True
        except Exception:
            return False
    
    def _get_image_info(self, image_path: Path) -> dict:
        """获取图片详细信息"""
        try:
            # 处理SVG文件
            if image_path.suffix.lower() == '.svg':
                try:
                    with open(image_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # 简单解析SVG尺寸（如果存在）
                        import re
                        width_match = re.search(r'width=["\']?(\d+)', content)
                        height_match = re.search(r'height=["\']?(\d+)', content)
                        
                        width = int(width_match.group(1)) if width_match else 0
                        height = int(height_match.group(1)) if height_match else 0
                        
                        return {
                            'width': width,
                            'height': height,
                            'format': 'SVG',
                            'size': image_path.stat().st_size
                        }
                except Exception:
                    # SVG解析失败时返回基本信息
                    return {
                        'width': 0,
                        'height': 0,
                        'format': 'SVG',
                        'size': image_path.stat().st_size
                    }
            
            # 处理常规图片格式
            with Image.open(image_path) as img:
                return {
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'size': image_path.stat().st_size
                }
        except Exception as e:
            logger.error(f"获取图片信息失败: {e}")
            return {
                'width': 0,
                'height': 0,
                'format': None,
                'size': 0
            }


class ImageProcessor:
    """图片处理器"""
    
    @staticmethod
    def resize_image(image_path: Path, max_width: int = 1920, max_height: int = 1080) -> Optional[Path]:
        """
        调整图片尺寸
        返回: 处理后的图片路径
        """
        try:
            # 对于SVG文件，先转换为PNG再调整尺寸
            if image_path.suffix.lower() == '.svg':
                try:
                    import cairosvg
                    # 先转换为PNG
                    png_path = image_path.with_suffix('.png')
                    cairosvg.svg2png(url=str(image_path), write_to=str(png_path))
                    logger.info(f"SVG转PNG用于尺寸调整: {image_path.name} -> {png_path.name}")
                    image_path = png_path
                except ImportError:
                    logger.warning(f"cairosvg未安装，无法调整SVG尺寸: {image_path.name}")
                    return image_path
                except Exception as e:
                    logger.error(f"SVG转换失败: {e}")
                    return image_path
            
            # 对于PNG或其他图片格式，进行尺寸调整
            with Image.open(image_path) as img:
                # 如果图片尺寸合适，直接返回原路径
                if img.width <= max_width and img.height <= max_height:
                    return image_path
                
                # 计算新的尺寸，保持宽高比
                ratio = min(max_width / img.width, max_height / img.height)
                new_width = int(img.width * ratio)
                new_height = int(img.height * ratio)
                
                # 调整尺寸
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # 保存调整后的图片
                resized_path = image_path.with_name(f"resized_{image_path.name}")
                resized_img.save(resized_path, optimize=True, quality=85)
                
                return resized_path
                
        except Exception as e:
            logger.error(f"调整图片尺寸失败: {e}")
            return None
    
    @staticmethod
    def convert_format(image_path: Path, target_format: str = 'JPEG') -> Optional[Path]:
        """
        转换图片格式
        """
        try:
            # SVG文件特殊处理：转换为PNG
            if image_path.suffix.lower() == '.svg':
                try:
                    import cairosvg
                    # 转换为PNG格式
                    png_path = image_path.with_suffix('.png')
                    cairosvg.svg2png(url=str(image_path), write_to=str(png_path))
                    logger.info(f"SVG转PNG成功: {image_path.name} -> {png_path.name}")
                    return png_path
                except ImportError:
                    logger.warning(f"cairosvg未安装，SVG文件 {image_path.name} 保持原格式")
                    return image_path
                except Exception as e:
                    logger.error(f"SVG转换失败: {e}")
                    return image_path
            
            with Image.open(image_path) as img:
                # 如果已经是目标格式
                if img.format == target_format:
                    return image_path
                
                # 转换格式
                converted_path = image_path.with_suffix(f'.{target_format.lower()}')
                
                # 处理RGBA模式（JPEG不支持透明度）
                if target_format == 'JPEG' and img.mode in ('RGBA', 'LA'):
                    # 创建白色背景
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'RGBA':
                        background.paste(img, mask=img.split()[-1])
                    else:
                        background.paste(img)
                    background.save(converted_path, 'JPEG', quality=85)
                else:
                    img.save(converted_path, target_format, quality=85)
                
                return converted_path
                
        except Exception as e:
            logger.error(f"转换图片格式失败: {e}")
            return None


class ImageManager:
    """图片管理器"""
    
    def __init__(self, base_storage_path: Path):
        self.base_path = base_storage_path
        self.downloader = ImageDownloader()
        self.processor = ImageProcessor()
    
    def download_project_images(self, project_id: str, images: List[ProjectImage]) -> List[ProjectImage]:
        """
        下载项目的所有图片
        返回: 下载成功的图片列表
        """
        project_image_dir = self.base_path / project_id / "images"
        successful_images = []
        
        logger.info(f"开始下载 {len(images)} 张图片到 {project_image_dir}")
        
        for i, image in enumerate(images):
            try:
                # 生成保存路径
                filename = f"{image.id}_{os.path.basename(image.url.path)}"
                save_path = project_image_dir / filename
                
                # 下载图片
                if self.downloader.download_image(image, save_path):
                    # 处理图片（调整尺寸和格式）
                    processed_path = self._process_image(save_path)
                    if processed_path:
                        image.local_path = processed_path
                        successful_images.append(image)
                        logger.info(f"图片下载成功: {filename}")
                    else:
                        # 处理失败，使用原始图片
                        successful_images.append(image)
                        
            except Exception as e:
                logger.error(f"处理图片 {image.id} 失败: {e}")
                continue
        
        logger.info(f"图片下载完成，成功 {len(successful_images)}/{len(images)} 张")
        return successful_images
    
    def _process_image(self, image_path: Path) -> Optional[Path]:
        """处理单张图片"""
        try:
            # 调整尺寸
            resized_path = self.processor.resize_image(image_path, 1920, 1080)
            if not resized_path:
                return None
            
            # 转换格式为JPEG（减小文件大小）
            if resized_path.suffix.lower() not in ['.jpg', '.jpeg']:
                final_path = self.processor.convert_format(resized_path, 'JPEG')
                # 删除中间文件
                if final_path and final_path != resized_path:
                    resized_path.unlink(missing_ok=True)
                return final_path
            else:
                return resized_path
                
        except Exception as e:
            logger.error(f"处理图片失败: {e}")
            return None
    
    def cleanup_failed_downloads(self, project_id: str):
        """清理下载失败的临时文件"""
        project_dir = self.base_path / project_id
        if project_dir.exists():
            for temp_file in project_dir.rglob("*"):
                if temp_file.is_file() and temp_file.name.startswith("temp_"):
                    temp_file.unlink(missing_ok=True)
    
    def get_image_stats(self, project_id: str) -> dict:
        """获取项目图片统计信息"""
        project_dir = self.base_path / project_id
        if not project_dir.exists():
            return {}
        
        image_files = list(project_dir.rglob("*.jpg")) + list(project_dir.rglob("*.png"))
        total_size = sum(f.stat().st_size for f in image_files)
        
        return {
            'total_images': len(image_files),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2)
        }