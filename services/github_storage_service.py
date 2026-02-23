"""
GitHub项目本地存储管理器
负责项目数据的本地持久化存储和管理
"""
import json
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger
from src.models.github_models import GitHubProject, ProjectImage


class StorageConfig:
    """存储配置"""
    def __init__(self, base_path: Path = Path("data/github_projects")):
        self.base_path = base_path
        self.projects_dir = base_path / "projects"
        self.temp_dir = base_path / "temp"
        self.cache_dir = base_path / "cache"
        
        # 创建必要的目录
        self._create_directories()
    
    def _create_directories(self):
        """创建存储目录结构"""
        directories = [
            self.base_path,
            self.projects_dir,
            self.temp_dir,
            self.cache_dir
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


class ProjectStorageManager:
    """项目存储管理器"""
    
    def __init__(self, config: StorageConfig):
        self.config = config
        self.metadata_file = "metadata.json"
        self.images_dir = "images"
        self.screenshots_dir = "screenshots"
    
    def save_project(self, project: GitHubProject) -> bool:
        """
        保存项目数据到本地存储
        返回: 是否保存成功
        """
        try:
            project_dir = self._get_project_directory(project.id)
            project_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存元数据
            metadata_path = project_dir / self.metadata_file
            self._save_metadata(project, metadata_path)
            
            # 更新项目存储路径
            project.local_storage_path = project_dir
            
            logger.info(f"项目 {project.id} 已保存到 {project_dir}")
            return True
            
        except Exception as e:
            logger.error(f"保存项目 {project.id} 失败: {e}")
            return False
    
    def load_project(self, project_id: str) -> Optional[GitHubProject]:
        """
        从本地存储加载项目数据
        返回: GitHubProject对象或None
        """
        try:
            project_dir = self._get_project_directory(project_id)
            metadata_path = project_dir / self.metadata_file
            
            if not metadata_path.exists():
                logger.warning(f"项目 {project_id} 的元数据文件不存在")
                return None
            
            # 加载元数据
            metadata = self._load_metadata(metadata_path)
            
            # 创建项目对象
            project = GitHubProject(**metadata)
            project.local_storage_path = project_dir
            
            # 加载图片信息
            project.images = self._load_project_images(project_id)
            
            # 设置截图路径
            screenshot_path = project_dir / self.screenshots_dir / "project_homepage.jpg"
            if screenshot_path.exists():
                project.screenshot_path = screenshot_path
            
            return project
            
        except Exception as e:
            logger.error(f"加载项目 {project_id} 失败: {e}")
            return None
    
    def delete_project(self, project_id: str) -> bool:
        """
        删除项目及其所有数据
        返回: 是否删除成功
        """
        try:
            project_dir = self._get_project_directory(project_id)
            if project_dir.exists():
                shutil.rmtree(project_dir)
                logger.info(f"项目 {project_id} 已删除")
                return True
            else:
                logger.warning(f"项目 {project_id} 不存在")
                return True
                
        except Exception as e:
            logger.error(f"删除项目 {project_id} 失败: {e}")
            return False
    
    def list_projects(self) -> List[Dict[str, Any]]:
        """
        列出所有已保存的项目
        返回: 项目基本信息列表
        """
        projects = []
        
        if not self.config.projects_dir.exists():
            return projects
        
        for project_dir in self.config.projects_dir.iterdir():
            if project_dir.is_dir():
                try:
                    metadata_path = project_dir / self.metadata_file
                    if metadata_path.exists():
                        metadata = self._load_metadata(metadata_path)
                        projects.append({
                            'id': metadata.get('id'),
                            'name': metadata.get('name'),
                            'full_name': metadata.get('full_name'),
                            'created_at': metadata.get('created_at'),
                            'storage_path': str(project_dir)
                        })
                except Exception as e:
                    logger.warning(f"读取项目 {project_dir.name} 信息失败: {e}")
                    continue
        
        # 按创建时间排序
        projects.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return projects
    
    def get_project_stats(self, project_id: str) -> Dict[str, Any]:
        """
        获取项目存储统计信息
        """
        project_dir = self._get_project_directory(project_id)
        if not project_dir.exists():
            return {}
        
        stats = {
            'total_size': 0,
            'image_count': 0,
            'screenshot_exists': False,
            'created_date': None
        }
        
        # 统计总大小
        for file_path in project_dir.rglob("*"):
            if file_path.is_file():
                stats['total_size'] += file_path.stat().st_size
        
        # 统计图片数量
        images_dir = project_dir / self.images_dir
        if images_dir.exists():
            stats['image_count'] = len(list(images_dir.glob("*")))
        
        # 检查截图是否存在
        screenshot_path = project_dir / self.screenshots_dir / "project_homepage.jpg"
        stats['screenshot_exists'] = screenshot_path.exists()
        
        # 获取创建日期
        metadata_path = project_dir / self.metadata_file
        if metadata_path.exists():
            try:
                metadata = self._load_metadata(metadata_path)
                stats['created_date'] = metadata.get('created_at')
            except Exception:
                pass
        
        return stats
    
    def _get_project_directory(self, project_id: str) -> Path:
        """获取项目存储目录"""
        return self.config.projects_dir / project_id
    
    def _save_metadata(self, project: GitHubProject, metadata_path: Path):
        """保存项目元数据"""
        # 转换为可序列化的字典
        metadata = project.model_dump()
        
        # 转换Path对象为字符串
        if metadata.get('local_storage_path'):
            metadata['local_storage_path'] = str(metadata['local_storage_path'])
        if metadata.get('screenshot_path'):
            metadata['screenshot_path'] = str(metadata['screenshot_path'])
        
        # 转换图片列表中的Path对象
        for image in metadata.get('images', []):
            if image.get('local_path'):
                image['local_path'] = str(image['local_path'])
        
        # 保存到JSON文件
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2, default=str)
    
    def _load_metadata(self, metadata_path: Path) -> Dict[str, Any]:
        """加载项目元数据"""
        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_project_images(self, project_id: str) -> List[ProjectImage]:
        """加载项目图片信息"""
        images = []
        project_dir = self._get_project_directory(project_id)
        images_dir = project_dir / self.images_dir
        
        if not images_dir.exists():
            return images
        
        # 从元数据中重建图片对象
        metadata_path = project_dir / self.metadata_file
        if metadata_path.exists():
            try:
                metadata = self._load_metadata(metadata_path)
                image_data_list = metadata.get('images', [])
                for image_data in image_data_list:
                    # 转换字符串路径回Path对象
                    if image_data.get('local_path'):
                        image_data['local_path'] = Path(image_data['local_path'])
                    images.append(ProjectImage(**image_data))
            except Exception as e:
                logger.error(f"加载图片信息失败: {e}")
        
        return images


class CacheManager:
    """缓存管理器"""
    
    def __init__(self, cache_dir: Path, max_size_mb: int = 100):
        self.cache_dir = cache_dir
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{key}.cache"
    
    def save_to_cache(self, key: str, data: bytes) -> bool:
        """保存数据到缓存"""
        try:
            cache_path = self.get_cache_path(key)
            with open(cache_path, 'wb') as f:
                f.write(data)
            
            self._cleanup_if_needed()
            return True
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
            return False
    
    def load_from_cache(self, key: str) -> Optional[bytes]:
        """从缓存加载数据"""
        try:
            cache_path = self.get_cache_path(key)
            if cache_path.exists():
                with open(cache_path, 'rb') as f:
                    return f.read()
            return None
        except Exception as e:
            logger.error(f"加载缓存失败: {e}")
            return None
    
    def _cleanup_if_needed(self):
        """如果缓存过大则清理"""
        total_size = sum(f.stat().st_size for f in self.cache_dir.glob("*") if f.is_file())
        
        if total_size > self.max_size_bytes:
            # 删除最老的文件
            files = [(f, f.stat().st_mtime) for f in self.cache_dir.glob("*") if f.is_file()]
            files.sort(key=lambda x: x[1])  # 按修改时间排序
            
            # 删除直到大小合适
            current_size = total_size
            for file_path, _ in files:
                if current_size <= self.max_size_bytes:
                    break
                current_size -= file_path.stat().st_size
                file_path.unlink()


# 使用示例
def demo_storage_manager():
    """演示存储管理器的使用"""
    # 初始化存储管理器
    config = StorageConfig(Path("data/demo_github"))
    storage_manager = ProjectStorageManager(config)
    
    # 列出已有项目
    projects = storage_manager.list_projects()
    print(f"找到 {len(projects)} 个项目:")
    for project in projects:
        print(f"  - {project['name']} ({project['id']})")
    
    # 获取项目统计信息
    if projects:
        project_id = projects[0]['id']
        stats = storage_manager.get_project_stats(project_id)
        print(f"\n项目 {project_id} 统计信息:")
        print(f"  总大小: {stats['total_size'] / (1024*1024):.2f} MB")
        print(f"  图片数量: {stats['image_count']}")
        print(f"  截图存在: {stats['screenshot_exists']}")


if __name__ == "__main__":
    demo_storage_manager()