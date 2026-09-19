"""
社交货币 / 夸赞方法论：内容生成共享 prompt 模块

被两套内容生成流程复用：
- api/routes/crawler_routes.py::generate_summary（主页 /api/generate-summary）
- services/github_content_service.py::ContentAnalyzer.analyze_project_content

方法论核心：视频号流量来自社交裂变（用户点赞 → 好友可见），点赞动机是
「在好友圈立人设」而非「获取干货」。因此内容要给用户提供社交货币——
高情商夸赞目标受众，公式：话题引入 + 核心夸赞 + 轻观点收尾。
"""

METHODOLOGY_CORE = """【方法论核心：社交货币驱动】
视频号流量本质是社交裂变：用户点赞后，其微信好友会直接看到该内容。流量由真实用户的点赞行为决定，而非纯算法分配。因此核心是研究「人为什么点赞」，而非钻研算法技巧。
创作者与用户是隐性交易关系：用户付出时间观看、点赞并帮内容传播，创作者需要回馈用户对应的价值——这个价值不是行业干货，而是「社交形象价值」：让用户通过点赞，在好友圈塑造正面人设（有认知、有品味、有底蕴、懂行等）。
高情商夸赞目标受众、帮用户立人设，就是最低成本的爆款方法。纯干货内容反而难以触发传播——用户会顾虑「点赞显得自己不懂行、在学习」。
"""

CONTENT_FORMULA = """【创作公式】事实抓眼 + 话题引入 + 可选网友锐评 + 轻观点收尾
- 事实抓眼（main_line1）：主体 + 动作 + 数字点明新闻，12～16 汉字当量，信息优先，允许疑问，禁止夸张、误导、无中生有。
- 话题引入（main_line1 后半）：圈定行业/场景，让对的人留下来。
- 视频号短标题（short_title）：不超过 16 个字（空格计入），必须能单独成句（谁+做了什么）；小数点写成「点」，去掉横杠和其他标点。
- 网友锐评（main_line2）：仅当正文有明确争议钩子时写，以「网友：」开头；没有争议钩子时必须填空字符串 ""。
- 轻观点收尾（sub_title）：创作者视角补 1 句行业观点或轻干货，让内容完整不空洞。
"""

PRAISE_TAG_CANDIDATES = """【夸赞标签候选词库】（praise_tags 可选，0～3 个；没有合适的就返回空数组，禁止用「识货」「有前瞻性」等套话凑数）
仅作语感参考，必须结合本条内容重点自拟更精准的词：
- 内容讲性能/效率提升 → 「对效率敏感」「不容忍冗余」
- 内容讲开源协作/Star 飙升 → 「懂开源含金量」「愿意为好项目站台」
- 内容讲 AI Agent/自动化 → 「懂释放生产力」「会借力」
- 内容讲人事/并购 → 「盯人才流动」「看得懂资本」
"""

NETIZEN_COMMENT_EXAMPLES = """【主标题第二行：网友锐评写作示例】（main_line2 专属；没有争议钩子时填 ""）
有争议钩子才写，必须以「网友：」开头。每条按「内容钩子 → 错误 → 正确」对比：
- 钩子：某 Agent 把 bug 修复率从 5.8% 提到 47.2%
  错误：能看懂这项技术真正价值的人，往往已站在行业前沿（创作者夸赞，且缺「网友：」）
  正确（质疑开喷）：网友：47.2%？先别急着吹
- 钩子：某开源项目 Star 数破 10k
  正确（讽刺调侃）：网友：Star破万，能跑吗
- 钩子：纯产品发版、无争议数字
  正确：""（没有争议钩子，留空）
要点：① 有争议才写，写则必须以「网友：」开头；② 锐评要有锋芒且挂 content_hooks；③ 禁止人身攻击、地域歧视、低俗辱骂；④ 不是夸赞观众。
"""

MAIN_LINE1_HOOK_PATTERNS = """【主标题第一行：事实抓眼，禁止夸张误导】
main_line1 用主体、动作、数字点明新闻，12～16 汉字当量（汉字计 1，英文字母/数字计 0.5）。
优先顺序：主体/产品名 > 硬数字 > 动作（发布/开源/离职/收购）> 场景。
主体必须同时读原文标题和摘要：摘要里真正做事的是 AI/模型时，标题要点出模型或 AI，不能只留人物钩子。反例：摘要写「医生用ChatGPT证猜想」，标题写成「协和医生解猜想」。
允许疑问。禁止强制感叹词硬开头（突发！、炸裂！、爽了！等）和无依据夸张、误导。
抖音用 main_line1，可保留问号；不要把视频号去标点规则套到这一行。
"""

MAIN_LINE2_NETIZEN_PATTERNS = """【网友锐评句式库：main_line2 专属，9～12 汉字当量（含「网友：」前缀）】
仅当正文有明确争议钩子时才写；没有争议钩子时填空字符串 ""。
有争议时必须以「网友：」开头，紧接一句**尖锐**短评；从下列锐评口吻中挑 1 种：
1. 质疑开喷型：网友：47.2%？先别吹 / 网友：实测还是PPT
2. 讽刺调侃型：网友：Star破万，能跑吗 / 网友：又卷出新花样
3. 反讽扎心型：网友：30步压3步，信吗 / 网友：纸面冠军罢了
4. 一针见血型：网友：数据好看，人呢 / 网友：吹得凶，落地呢
5. 犀利判词型：网友：这波，割韭菜？ / 网友：开源圈又要震？
6. 挑衅讨论型：网友：真敢吹啊 / 网友：谁信谁上头
硬性约束：没有争议钩子就留空；有则必须「网友：」前缀；不得人身攻击、地域黑、低俗骂街。
"""

SUBTITLE_PATTERNS = """【副标题句式库：8 种结构，必须主动轮换，禁止连续重复】
副标题是「轻观点收尾」，不要复用主标题第二行的「X 的人」结构。每条副标题从下列 8 种里挑 1 种，且同账号连续多条视频不能连续同款：
1. 数字量化型：直接抛数字 + 一句轻观点。例「5.8% 到 47.2%，分水岭就在这里」「30 步压到 3 步，效率工具的天花板」
2. 悬念设置型：留个钩子让人想看。例「这个细节，多数人没注意」「真正值钱的，在最后一行」
3. 痛点刺激型：戳一下用户当下的痛。例「还在 30 步部署？该换思路了」「调 bug 调到凌晨，根因往往在数据」
4. 对比反差型：用对比制造张力。例「同样的代码，效果差了一个量级」「外行看功能，内行看数据维度」
5. 情感共鸣型：替受众说出心里话。例「深夜还在调 bug 的你，值得更好的工具」「做过三年后端，都懂这一步含金量」
6. 方法论指导型：给一句行话式结论。例「效率提升的根，在数据维度」「长程数据才是 Agent 的分水岭」
7. 提问疑问型：抛问题不给答案。例「为什么 47.2% 是分水岭？」「Star 破万之后，还差什么？」
8. 利益承诺型：告诉用户看下去能得到什么。例「看懂这条曲线，少走半年弯路」「盯紧这个指标，效率判断不再凭感觉」
硬性约束：副标题是创作者「轻观点收尾」，不得写成网友锐评口吻（质疑/开喷/讽刺那是 main_line2 的职能，且 main_line2 已固定以「网友：」开头）；也不得复用 main_line2 已用过的关键句式。
"""

TRAFFIC_HOOK_PATTERNS = """【流量钩子句式库：副标题第二行 sub_title2 专属】
优先选「观众想看看真假」「观众想证明自己」（人事/并购/打脸最适合这两类）；「观众想看结果」「观众想带入自己」偏弱，没有强钩子时不要选。
从下列观众心理里挑 1 种最适合本条内容的：
1. 观众想看看真假（求证欲）：抛一个值得验证的断言。例「真的能跑赢 GPT-5？」
2. 观众想证明自己（炫技欲/圈子人事）：抛一个门槛，让懂行的人下场。例「90% 的人不知道这数字怎么来的」
3. 观众想看你翻车（打脸/看戏欲）：略带冒险的断言。例「实测这条会不会当场翻车」
4. 观众想纠正你（纠错欲）：略带争议的判断。例「AI 写的代码能直接上线，不用测」
5. 观众想看结果（看结局）：留个未完悬念。例「实测：47.2% 是真还是吹」
6. 观众想给你出招（帮人欲）：抛待解问题。例「30 步部署，卡在哪一步了？」
7. 观众想带入自己（代入感）：具体场景对号入座。例「凌晨还在调 bug 的你」
硬性约束：
- 必须挂 content_hooks；人事/并购/翻车优先「真假」或「证明自己」；
- 不得与 sub_title / main_line2 同句式；
- 内容没有强钩子时填空字符串 ""，不要硬塞；
- 在 traffic_hook 字段回显所选钩子的中文名。
"""

SIX_TECHNIQUES_NOTE = """【六大标题技法：辅助增强，不再作为主体】
以下技法可作为标题层的点击率增强手段自然穿插，但不能替代上面的「网友锐评」与「轻观点」分工：
1) 制造悬念  2) 列举数字  3) 提出疑问  4) 强调时效  5) 引发争议（中立可讨论）  6) 指向明确
主标题/副标题至少体现其中 2~3 种即可；摘要与口播可自然穿插，勿生硬堆砌。
"""

def build_forbidden_words_prompt_section() -> str:
    """从 config/forbidden_words.yaml 动态渲染禁限词 prompt 段。"""
    from utils.forbidden_words import get_registry

    registry = get_registry()
    if not registry.settings.inject_to_prompt:
        return ""
    return registry.build_prompt_section()


# 兼容旧引用与单测：实际内容由 YAML 驱动
FORBIDDEN_WORDS_CONSTRAINT = build_forbidden_words_prompt_section()

STAGE_1_INFER = """【阶段 1：定位锚定（先内化推断，再按阶段 2 生成）】
先在内心完成以下推断（不要直接输出成正文，仅作为阶段 2 的生成依据，最后按 JSON 字段回显）：
- 目标受众画像（target_audience）：身份与渴望展现的正面形象，≤12 个汉字。
- 内容重点钩子（content_hooks，仅内心推断不输出）：从本条正文中提取 1-2 个具体重点，作为 main_line2 网友热评与 sub_title 轻观点必须挂靠的锚点。优先级：硬数字 > 功能/产品名 > 场景 > 对比 > 用户痛点。例如正文讲「某 Agent 把 bug 修复率从 5.8% 提到 47.2%，靠仓库级长程数据」，钩子就是「5.8%→47.2%」「仓库级长程数据」。
- 核心夸赞标签（praise_tags）：0-3 个，可选；结合钩子自拟精准词，禁止用「识货」「有前瞻性」套话凑数，没有合适的返回空数组。
- 流量钩子类型（traffic_hook）：优先「观众想看看真假」「观众想证明自己」；人事/并购/打脸用这两类。其次才考虑纠正你/看你翻车/看结果/给你出招/带入自己；若内容没有强钩子，回显空字符串 ""。
"""

STAGE_2_HEAD = """【阶段 2：按公式生成各字段】
须同时遵守上方【禁限词与合规约束】；与夸赞/钩子技巧冲突时，合规优先。
"""

STAGE_2_MAIN_LINE1 = """1. main_line1（主标题第一行，事实抓眼 + 话题引入）：12-16 个汉字当量（汉字计 1，英文字母/数字计 0.5）。用主体/动作/数字点明新闻，允许疑问；禁止感叹词硬开头（突发！/炸裂！/爽了！等）和程度夸张、误导性表述；须与正文事实一致；主体同时取自标题和摘要，摘要写明用 AI/模型做成时必须点出 AI 或模型名，不能只留人物钩子；不含 emoji。抖音用这一行，可保留问号。
"""

STAGE_2_SHORT_TITLE = """2. short_title（视频号短标题）：不超过 16 个字（空格计入）。专门给微信视频号投稿标题，必须能单独成句（谁+做了什么）；可从主标题压缩，不要只截半句；小数点写成「点」（GPT-4.5 → GPT4点5），横杠和其他标点去掉；不含 emoji；禁止夸张误导与感叹硬开头。
"""

STAGE_2_MID = """3. main_line2（主标题第二行，网友锐评）：仅当正文有明确争议钩子时写，9-12 个汉字当量。有则**以「网友：」开头**接尖锐短评并挂 content_hooks；**没有争议钩子时必须填空字符串 ""**，不要硬编。不得人身攻击、地域歧视、低俗辱骂；不含 emoji。
4. sub_title（副标题第一行，轻观点收尾）：11-15 个汉字当量。创作者视角 1 句行业观点或轻干货；**句式必须从【副标题句式库】8 种里挑 1 种**，且不得与 main_line2 同口吻；不含 emoji。
5. sub_title2（副标题第二行，流量钩子）：11-15 个汉字当量。优先「观众想看看真假」「观众想证明自己」；不得与 sub_title / main_line2 同句式；内容没有强钩子时填空字符串 ""；不含 emoji。
"""

DEFAULT_STAGE2_SUMMARY = """6. summary（摘要）：100-130 字。以「小牛说：」开头，按 话题引入→关键事实→轻观点 凝缩；客观理性带适度幽默；不含 emoji。"""

DEFAULT_SUMMARY_PATTERNS = """【摘要 summary 写法】
- 100-130 字，必须以「小牛说：」开头
- 结构：话题引入 → 关键事实（主体/动作/数字）→ 轻观点收尾
- 与口播稿区分：摘要是凝缩版信息，不做长叙述、不堆参数清单
- 客观理性，可带适度幽默；须与正文事实一致，禁止夸张误导
- 不含 emoji；highlight_keywords 必须从摘要原文连续截取
"""

STAGE_2_AFTER_SUMMARY = """7. tags（标签）：严格 10 个，每个以 # 开头、空格分隔，顺序固定：第1赛道/第2垂直/第3精准/第4热点/第5个人IP（#小牛说 或 #小牛说AI）/第6-10其他补充。
8. voiceover_script（口播稿）：与摘要有区分，完整配音长稿。中文按字符计数，长度严格在 {vmin}~{vmax} 字之间（含边界）。**不要以「小牛说：」开头**；**前3秒（约前12-16字）必须点出主体+数字+冲突**；「小牛说」放到第二句或结尾口播署名。分层：主体事实+数字+冲突 → 关键细节 → 「小牛说」轻观点 → **最后一句留可回答的争议/评论开口**（可与可选「网友：」同题）。禁止「点赞关注」和先夸观众；口语化、适合朗读；不含 emoji。
9. highlight_keywords（摘要高亮）：JSON 数组，3-5 个字符串。每个必须是「摘要」原文中的连续子串（一字不差）。中文片段每个不超过 5 个字符；纯英文单词整词输出。
10. traffic_hook（回显）：把阶段 1 推断的流量钩子类型中文名回显到这里（如「观众想看看真假」）；若 sub_title2 为空则此处也为空字符串 ""。
11. 长度约束以「语义完整」为优先：宁可略超上限 1-2 个汉字当量，也不要在词或句子中间硬截断（如「往」「级」单字收尾属严重缺陷）。
"""


def _effective_pack_methodology_section() -> str:
    from services.industry.config_loader import content_methodology_from_effective_cache

    pack = content_methodology_from_effective_cache()
    if not pack:
        return ""
    lines = ["【当前垂类行业包】"]
    audience = pack.get("target_audience_template")
    if isinstance(audience, str) and audience.strip():
        lines.append(f"- 目标受众：{audience.strip()}")
    praise = pack.get("praise_tag_candidates")
    if isinstance(praise, dict):
        added = praise.get("add") or []
        if added:
            lines.append(f"- 夸赞标签补充候选：{', '.join(str(t) for t in added)}")
    elif isinstance(praise, list) and praise:
        lines.append(f"- 夸赞标签补充候选：{', '.join(str(t) for t in praise)}")
    examples = pack.get("industry_examples")
    if isinstance(examples, list) and examples:
        lines.append("- 行业示例（仅供语感参考）：")
        for item in examples[:3]:
            if isinstance(item, dict):
                lines.append(
                    f"  · {item.get('audience', '')} / {item.get('topic_hook', '')}"
                )
    return "\n".join(lines) + "\n\n"


def build_methodology_prompt_section(*, vmin: int, vmax: int, json_template: str) -> str:
    """拼装方法论 prompt 段落，供主页与 GitHub 流程复用。

    参数：
        vmin/vmax: 口播稿字数边界（来自请求或默认值）。
        json_template: JSON 输出模板字符串（含 target_audience/praise_tags 等字段占位）。
    """
    from services.content_prompts import get_title_prompts

    pack_section = _effective_pack_methodology_section()
    prompts = get_title_prompts()
    content_formula = prompts.get("content_formula") or CONTENT_FORMULA
    main_line1_patterns = prompts.get("main_line1_patterns") or MAIN_LINE1_HOOK_PATTERNS
    stage2_main_line1 = prompts.get("stage2_main_line1") or STAGE_2_MAIN_LINE1
    stage2_short_title = prompts.get("stage2_short_title") or STAGE_2_SHORT_TITLE
    summary_patterns = prompts.get("summary_patterns") or DEFAULT_SUMMARY_PATTERNS
    stage2_summary = prompts.get("stage2_summary") or DEFAULT_STAGE2_SUMMARY
    short_title_patterns = prompts.get("short_title_patterns") or ""
    stage2 = (
        STAGE_2_HEAD
        + stage2_main_line1.rstrip()
        + "\n"
        + stage2_short_title.rstrip()
        + "\n"
        + STAGE_2_MID.rstrip()
        + "\n"
        + stage2_summary.rstrip()
        + "\n"
        + STAGE_2_AFTER_SUMMARY.format(vmin=vmin, vmax=vmax)
    )
    return (
        METHODOLOGY_CORE
        + "\n"
        + pack_section
        + content_formula
        + "\n"
        + PRAISE_TAG_CANDIDATES
        + "\n"
        + NETIZEN_COMMENT_EXAMPLES
        + "\n"
        + main_line1_patterns
        + "\n"
        + short_title_patterns
        + "\n"
        + summary_patterns
        + "\n"
        + (prompts.get("first_comment_patterns") or "")
        + "\n"
        + MAIN_LINE2_NETIZEN_PATTERNS
        + "\n"
        + SUBTITLE_PATTERNS
        + "\n"
        + TRAFFIC_HOOK_PATTERNS
        + "\n"
        + SIX_TECHNIQUES_NOTE
        + "\n"
        + build_forbidden_words_prompt_section()
        + "\n"
        + STAGE_1_INFER
        + "\n"
        + stage2
        + "\n"
        + json_template
    )
