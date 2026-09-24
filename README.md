# astrbot_plugin_vctniceeeee_new

> VCT CN（无畏契约中国赛区）比赛播报插件 · for [AstrBot](https://github.com/AstrBotDevs/AstrBot)

拉取 vlr.gg 的 VCT 赛程与比分，支持**定时自动播报**、**手动查询**、**比赛详情（地图 / 比分 / 选手数据 / MVP）** 以及**比赛进行中的实时监控播报**。

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

## 更新内容

### v2.0

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

> `monitor_state.json` 为运行期自动生成的状态文件，已加入 `.gitignore`，不会提交。

## 许可

本项目基于 [MIT License](LICENSE) 开源。
