# DeepSeek API集成设计

## DeepSeek简介
DeepSeek（深度求索）是国内优秀的大语言模型，具有强大的中文理解和生成能力，特别适合AI资讯总结任务。

## API配置

### 获取API Key
1. 注册DeepSeek账号：https://platform.deepseek.com
2. 创建API Key
3. 配置环境变量：`DEEPSEEK_API_KEY`

### API端点
```
https://api.deepseek.com/v1/chat/completions
```

## 功能设计

### 1. 单篇资讯总结
**输入**: 原始文章内容  
**输出**: 200-300字的精炼摘要

**Prompt模板**:
```
你是一个专业的AI资讯分析师。请对以下AI新闻进行总结：

新闻标题：{title}
新闻内容：{content}

要求：
1. 提炼核心要点（3-5条）
2. 总结字数控制在200-300字
3. 使用简洁专业的语言
4. 突出技术创新点和影响力

输出格式：
【核心要点】
- 要点1
- 要点2
- 要点3

【详细总结】
（具体内容）
```

### 2. 多篇资讯汇总
**输入**: 多篇文章摘要  
**输出**: 今日AI资讯综述

**Prompt模板**:
```
请基于以下今日AI资讯，生成一份3分钟视频脚本：

{summaries}

要求：
1. 按重要性排序top 5资讯
2. 每条资讯30-40字描述
3. 加入串场话术
4. 总字数约500字
5. 风格轻松但专业

脚本格式：
【开场】（50字）
【资讯1】（80字）
【资讯2】（80字）
...
【结尾】（50字）
```

### 3. 视频脚本生成
**输入**: 精选资讯摘要  
**输出**: 可直接用于TTS的视频脚本

**特点**:
- 口语化表达
- 添加停顿标记
- 控制语速和节奏

## 调用策略

### API参数配置
```python
{
    "model": "deepseek-chat",
    "messages": [...],
    "temperature": 0.7,      # 创造性 vs 准确性
    "max_tokens": 1000,      # 输出长度限制
    "top_p": 0.95,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0
}
```

### 成本控制
- **单次总结成本**: 约0.001-0.005元
- **每日预算**: 1元（可处理200-1000篇）
- **缓存策略**: 相同内容避免重复调用

### 速率限制
- 并发请求：3-5个
- 请求间隔：100ms
- 错误重试：指数退避

## 质量保障

### 1. Prompt优化
- 持续迭代Prompt模板
- A/B测试不同Prompt效果
- 收集优质输出案例

### 2. 输出验证
```python
def validate_summary(summary):
    """验证摘要质量"""
    checks = {
        "长度检查": 200 <= len(summary) <= 300,
        "关键词检查": has_ai_keywords(summary),
        "格式检查": has_proper_structure(summary)
    }
    return all(checks.values())
```

### 3. 降级策略
- DeepSeek API不可用时，使用备用方案
- 本地模型（如Qwen）作为备份
- 简单规则提取前N句作为兜底

## 数据流处理

```
爬取的文章列表
    ↓
内容预处理（清洗、分词）
    ↓
批量调用DeepSeek API
    ↓
解析和验证输出
    ↓
存储总结结果
    ↓
生成视频脚本
```

## 示例代码结构

```python
class DeepSeekService:
    """DeepSeek API服务"""
    
    def summarize_article(self, article):
        """总结单篇文章"""
        pass
    
    def generate_daily_digest(self, summaries):
        """生成每日综述"""
        pass
    
    def create_video_script(self, digest):
        """创建视频脚本"""
        pass
    
    def validate_output(self, output):
        """验证输出质量"""
        pass
```

## 监控和日志

### 记录内容
- API调用次数和成本
- 响应时间统计
- 错误率和失败原因
- 输出质量评分

### 告警机制
- API额度不足
- 错误率超过阈值
- 响应时间过长
