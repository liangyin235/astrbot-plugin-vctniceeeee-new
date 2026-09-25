# astrbot_plugin_vctniceeeee_new

https://github.com/user-attachments/assets/970449cc-5488-4173-8085-69561ed3144d

> VCT CN（无畏契约中国赛区）比赛播报插件 · for [AstrBot](https://github.com/AstrBotDevs/AstrBot)

拉取 vlr.gg 的 VCT 赛程与比分，支持**定时自动播报**、**手动查询**、**比赛详情（地图 / 比分 / 选手数据 / MVP）** 以及**比赛进行中的实时监控播报**。

ps:astrbot插件商店有一个和这个一模一样的，那个是旧版，作者都是我

## 功能特性

- 🗓️ 赛程查询：今日赛程、全部赛程
- 🏆 比分结果：已结束比赛的比分汇总
- 🔍 比赛详情：每张地图比分、双方攻防、选手 KDA、MVP
- 📢 定时播报：按间隔自动检查并推送新赛程 / 新结果
- ⚡ 实时监控：比赛进行中时按较短间隔播报详情，比赛结束后自动停止
- 🌏 国际赛事：全球冠军赛 / Masters 的淘汰赛、决赛也会播报（不限中国队场次）
- 🇨🇳 中文输出：队名、地图、赛段、英雄（Agent）名称均已中文化

## 播报范围

| 范围 | 是否播报 |
| --- | --- |
| 含**中国队**的比赛（不限赛事） | ✅ |
| **国际赛事**（VCT 全球冠军赛 / Masters）的全部比赛 | ✅ |
| 地区联赛中不含中国队的比赛（如 Champions Tour 各赛区） | ❌ |

判定依据：vlr.gg 赛程页比赛条目中的队伍国旗（`mod-cn`）与赛事名称。因此即使中国队被淘汰，冠军赛的淘汰赛与决赛仍会照常播报。

**"国际赛事"按赛事名精确匹配**，以避免误伤：

| 赛事名 | 判定 |
| --- | --- |
| `Valorant Champions 2026` | ✅ 全球冠军赛 |
| `Valorant Masters Toronto 2026` / `VCT 2026: Masters Toronto` / `Champions Tour 2023: Masters Tokyo` | ✅ 大师赛 |
| `Champions Tour 2026: China / Americas / EMEA / Pacific Stage X` | ❌ 地区联赛（仅播含中国队的场次） |
| `KOV Masters 2026`（第三方）、`Game Changers 2026: …`（女子赛）、`Valorant Challengers 2026: …`（次级联赛） | ❌ 不属于国际赛事 |

## 更新内容

### v2.0.2

- 🏷️ **队伍标记**：比赛详情中队伍名加 `▍` 前缀，便于与选手行区分
- ⚙️ **选手战绩可配置**：新增 `show_player_rating` 开关（默认关闭）。关闭只显示 KDA（`siufatbb（黑梦）13-12-2`）；开启则额外显示评分与 ACS（`1.23 / 250 / 13-12-2`），MVP 行同样跟随该开关。开启后每行变长，可能影响观感
- 🚫 **TBD 不报选手信息**：队伍未确定时不展示选手数据与 MVP（比赛详情 / 单图播报 / 整场播报三处）

### v2.0.1

- ⚡ **不再阻塞事件循环**：赛程 / 详情的网络抓取改为通过 `asyncio.to_thread` 在线程池执行（含正则解析），不再阻塞 AstrBot 事件循环、影响其他插件与平台并发
- 📁 **运行期数据位置规范化**：状态文件改存 `data/plugin_data/astrbot_plugin_vctniceeeee_new/`，不再写入插件自身目录；旧位置的同名文件会在首次加载时自动迁移
- 🔁 **详情抓取增加退避重试**：vlr.gg 偶发连接截断（`IncompleteRead` / `RemoteDisconnected` / SSL EOF）时最多重试 3 次，减少详情播报丢失

### v2.0.0

- 🌏 **支持国际赛事**：全球冠军赛（Valorant Champions）与 Masters 的**全部**比赛都会播报，不再只播含中国队的场次；即使中国队被淘汰，淘汰赛与决赛也能照常推送
- 🏷️ **显示真实赛事名**：播报标题与赛程列表改为显示赛事名（如 `Valorant Champions 2026`），不再统一显示 `VCT CN`
- 🇨🇳 **赛段名中文化增强**：支持组合赛段名，如 `Group Stage–Opening (C)` → `小组赛·揭幕战 (C)`、`Playoffs–Upper Semifinals` → `季后赛·半区半决赛`
- 🗑️ **移除号角（haojiao）兜底源**：该数据源的比赛 ID 体系与 vlr.gg 不同，详情兜底无法命中，且不覆盖国际赛事；同时移除 `pycryptodome` 依赖
- 🧹 移除重复的死代码 `parse_page`

### v1.0

- 首个正式版本：赛程查询 / 比分结果 / 比赛详情 / 定时播报 / 实时监控
- 插件标识改为 `astrbot_plugin_vctniceeeee_new`，与仓库名保持一致

## 安装

### 方式一：插件市场

在 AstrBot WebUI → 插件市场 中搜索 `vct` 安装。

### 方式二：手动安装

1. 将本仓库放入 AstrBot 的插件目录：

   ```
   data/plugins/astrbot_plugin_vctniceeeee_new/
   ```

   > 注意：目录名必须是 `astrbot_plugin_vctniceeeee_new`，且该目录下直接是 `main.py`、`metadata.yaml` 等文件。

2. 安装依赖（AstrBot 通常会自动安装 `requirements.txt`；如未自动安装可手动执行）：

   ```bash
   pip install -r data/plugins/astrbot_plugin_vctniceeeee_new/requirements.txt
   ```

3. 重载插件 / 重启 AstrBot。

## 使用

| 命令 | 说明 |
| --- | --- |
| `/vct today` | 今日赛程与即将开始的比赛 |
| `/vct all` | 全部赛程 |
| `/vct result` | 比赛结果 |
| `/vct match <比赛ID 或链接>` | 查看比赛详情（比分 / 地图 / 选手数据 / MVP） |
| `/vct bind` | 把当前会话设为定时播报目标 |
| `/vct unbind` | 取消当前会话的定时播报 |
| `/vct list` | 查看已绑定的播报目标 |
| `/vct sid` | 显示当前会话 ID（排查用） |

## 配置

在 AstrBot WebUI → 插件配置 中设置：

| 配置项 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `target_sessions` | list | `[]` | 定时播报的目标会话列表（如 `qq/123456`），可用 `/vct bind` 动态添加；留空则仅手动查询 |
| `poll_interval_min` | int | `30` | 定时自动播报的检查间隔（分钟） |
| `live_poll_min` | int | `5` | 比赛进行中实时播报详情的间隔（分钟） |
| `show_player_rating` | bool | `false` | 选手战绩是否显示详细评分与 ACS。开启为「评分 / ACS / K-D-A」，关闭（默认）只显示 K-D-A。**开启后每行变长，可能会影响观感** |

## 依赖

- `apscheduler` —— 定时任务（缺失时定时播报不可用，手动查询仍可用）

## 数据来源

数据来源于 [vlr.gg](https://www.vlr.gg/matches) 公开赛事页面，仅用于赛事信息播报；如页面结构变更，播报内容可能暂时失效，请提交 Issue。

## 目录结构

```
astrbot_plugin_vctniceeeee_new/
├── main.py             # 插件入口、命令、定时调度、渲染
├── match_parser.py     # 比赛详情解析
├── translations.py     # 中文映射（队名 / 地图 / 英雄）
├── metadata.yaml       # 插件元信息
├── _conf_schema.json   # 插件配置 Schema
├── requirements.txt
└── README.md
```

> 运行期状态文件（`monitor_state.json`）保存在 AstrBot 的 `data/plugin_data/astrbot_plugin_vctniceeeee_new/` 目录下，不会写进插件目录；旧版本遗留在插件目录内的同名文件会在首次加载时自动迁移。

## 许可

本项目基于 [MIT License](LICENSE) 开源。
