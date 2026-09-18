# AstrBot 俄罗斯轮盘赌插件 (`astrbot_plugin_russian_roulette`)

[![AstrBot Plugin](https://img.shields.io/badge/AstrBot-Plugin-blue.svg)](https://github.com/Soulter/AstrBot)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

面向 **AstrBot** 聊天机器人生态的**俄罗斯轮盘赌 (Russian Roulette)** 主持人与战况展示插件。

群聊成员可以通过 `/rr` 或 `/轮盘` 指令直接在 QQ / 微信等聊天窗口中发起对决、移动走位、瞄准扣动扳机并体验生死悬于一线的刺激博弈！

---

## 🌟 核心特性

- **纯指令驱动 (MVP)**：玩家使用直观的聊天指令（`/rr 开火`、`/rr 移动`、`/rr 步进`）进行对决，不依赖复杂界面或客户端安装；
- **绝对服务器权威**：所有随机数种子、弹巢真假实弹装填、弹道判定、防弹盾击碎、水面涉水溺水与胜负裁决 **100% 由 Rust 游戏引擎权威计算**；
- **智能主持人播报**：
  - 战术地图 Emoji 字符阵列可视化；
  - 玩家血量槽、防弹盾完好度、当前行动方高亮指示；
  - 击毙、防弹盾破裂、掩体贯穿等丰富戏剧性事件流实时播报；
- **会话房间记忆**：自动绑定当前群聊的默认对局房间，省略繁琐的重复房间号输入；
- **标准插件市场规范**：提供严谨的 `metadata.yaml` 与 `_conf_schema.json`，支持 WebUI 界面可视化配置。

---

## 📥 安装方法

### 方式一：通过 AstrBot 插件市场一键安装（推荐）
1. 登录 AstrBot WebUI 管理面板；
2. 进入「插件」页面，在搜索框中输入 `俄罗斯轮盘赌` 或 `astrbot_plugin_russian_roulette`；
3. 点击「安装」即可。

### 方式二：Git 源码安装
进入你的 AstrBot 安装目录下的插件文件夹（`data/plugins/`）：

```bash
cd data/plugins/
git clone https://github.com/akimotokaya/astrbot_plugin_russian_roulette.git
```

然后在 AstrBot WebUI 插件页面中点击「重载插件」即可生效。

---

## ⚙️ 配置说明 (`_conf_schema.json`)

在 AstrBot WebUI 插件配置面板中可自由修改以下参数：

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `server_url` | string | `http://127.0.0.1:8787` | 俄罗斯轮盘游戏后端地址 (如本地 8787 或公网 8080) |
| `mcp_endpoint` | string | `/api/mcp/call` | MCP JSON-RPC 调用端点路径 |
| `default_bots` | int | `3` | 快速创建房间时默认加入的 Bot 席位数 (1-7) |
| `admin_only` | bool | `false` | 是否限制仅管理员可创建或解散房间 |
| `show_visual_board` | bool | `true` | 是否在战况中打印 Emoji 字符战术棋盘 |
| `max_event_records` | int | `5` | 战报中最多附带展示的最新戏剧性事件流水条数 |

---

## 🎮 指令速查手册

所有指令均支持 `/rr` 或 `/轮盘` 别名：

| 指令 | 参数说明 | 示例 |
| :--- | :--- | :--- |
| `/rr 帮助` | 显示完整指令指南 | `/rr 帮助` |
| `/rr 状态` | 检查与 Rust 轮盘后端的连接状态 | `/rr 状态` |
| `/rr 房间` | 查看当前正在进行的轮盘房间列表 | `/rr 房间` |
| `/rr 创建 [名称] [Bot数]` | 创建对局房间并预设 Bot 席位 | `/rr 创建 决战深夜 3` |
| `/rr 开始 [房间号]` | 装填弹巢并正式开局 | `/rr 开始` 或 `/rr 开始 88888` |
| `/rr 战况 [房间号]` | 查看棋盘、所有席位状态与事件流 | `/rr 战况` |
| `/rr 开火 [房间号] <方向>` | 向指定方向扣动扳机（上/下/左/右/北/南/西/东/w/s/a/d） | `/rr 开火 上` |
| `/rr 移动 [房间号] <方向>` | 在地图上移动一格 | `/rr 移动 东` |
| `/rr 等待 [房间号]` | 放弃本轮行动 | `/rr 等待` |
| `/rr 自戕 [房间号]` | 绝望饮弹自戕 | `/rr 自戕` |
| `/rr 步进 [房间号]` | 轮到 Bot 时，推进 Bot 走一步 | `/rr 步进` |
| `/rr 解散 [房间号]` | 强制解散并清空房间 | `/rr 解散 88888` |
| `/rr 规则` | 查询权威规则与特殊地形机制 | `/rr 规则` |

---

## 🛠️ 本地独立开发与测试

本插件内置了单体测试脚本，无需启动整个 AstrBot 守护进程即可验证指令解析与 MCP 联调：

```bash
# 安装依赖
pip install -r requirements.txt

# 运行独立验证套件
python3 test_standalone.py
```

---

## 📄 开源许可

本项目遵循 [MIT License](LICENSE) 开源。
