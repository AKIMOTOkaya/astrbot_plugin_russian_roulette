# 更新日志 (Changelog)

本项目遵循 [Semantic Versioning (语义化版本)](https://semver.org/lang/zh-CN/) 规范。
注意：AstrBot 插件市场要求每次提交或重新审核发布时**必须递增版本号**，即使历史版本被驳回或撤回也不得复用。

## [1.0.2] - 2026-09-20

### 新增与优化 (Features & Improvements)
- **接入规则矢量战术图形渲染引擎**：在 MCP 客户端中新增 `render_room_image` 端点调用，对战中自动调用后端 `referee_render_room_image` 工具生成高清战术 PNG 战况板，以图片消息直观呈现战场地形、弹孔、弹道与血条；
- **智能双显与容错降级**：若图片渲染因网络或引擎原因异常，自动降级为字符棋盘；支持通过 `render_image` 与 `show_visual_board_with_image` 自定义配置是否发送图片或与文本棋盘混排；
- **配置项扩展**：在 `_conf_schema.json` 中增加 `render_image`、`image_view_mode`、`show_visual_board_with_image` 配置项，支持全景模式、观战视角及玩家迷雾视角切换。

---

## [1.0.1] - 2026-09-19

### 修复 (Fixes)
- **合规日志改造**：彻底移除 Python 内置 `logging` 模块和 `logging.getLogger`，全面使用 `from astrbot.api import logger`，满足插件市场安全审核要求；
- **纯异步网络请求**：移除 `urllib.request` 同步 HTTP 备用逻辑，全面统一为 `aiohttp.ClientSession` 异步调用；
- **规范模块导入**：消除函数内部局域动态 `import re`，所有依赖统一定义于文件顶部；
- **异常捕获留痕**：移除裸 `except Exception: pass` 静默吞噬，精准捕获 `McpError`、`AttributeError` 等具体类型并记录日志；
- **消除代码重复 (DRY)**：提炼 `_extract_command_parts` 辅助函数统一解析指令前缀；清理 `_dispatch_command` 中重复的多余 `except` 块；
- **元数据匹配**：修正 `metadata.yaml` 仓库 URL 大小写为 `AKIMOTOkaya`。

### 新增与优化 (Features & Improvements)
- **战报符号压缩**：将原始状态与动作提炼为极简 Emoji 标签（如 `P1🤖 🚶↑`、`P2🤖 🔫→`、`P3🤖 ⏳跳过`），席位流采用单行徽章流显示；
- **多消息分块独立推送**：通过 AstrBot 异步生成器机制，将原本长报文拆解为 4 个独立气泡（高优先级公告、裁判裁定、战术棋盘、专属轮次呼叫），大幅提升手机端阅读体验；
- **真人玩家专属强提醒**：轮到真人行动时，单独一条气泡通过 `At` 组件呼叫玩家，并提供走位与射击语法提示。

---

## [1.0.0] - 2026-09-19

### 初始发布 (Initial Release)
- 提供基础指令框架：`/rr 帮助`、`/rr 状态`、`/rr 规则`、`/rr 房间`、`/rr 创建`、`/rr 开始`、`/rr 战况`、`/rr 开火`、`/rr 移动`、`/rr 等待`、`/rr 自戕`、`/rr 步进`、`/rr 解散`；
- 通过 MCP JSON-RPC 协议与 Rust 游戏引擎权威协同；
- 支持 ASCII/Emoji 字符战术棋盘渲染。
