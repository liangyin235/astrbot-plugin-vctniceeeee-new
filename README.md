# astrbot_plugin_vct_cn

> VCT CN（无畏契约中国赛区）比赛播报插件 · for [AstrBot](https://github.com/AstrBotDevs/AstrBot)

拉取 VCT 中国赛区的赛程与比分，支持**定时自动播报**、**手动查询**、**比赛详情（地图 / 比分 / 选手数据 / MVP）** 以及**比赛进行中的实时监控播报**。

## 功能特性

- 🗓️ 赛程查询：今日赛程、全部赛程
- 🏆 比分结果：已结束比赛的比分汇总
- 🔍 比赛详情：每张地图比分、双方攻防、选手 KDA、MVP
- 📢 定时播报：按间隔自动检查并推送新赛程 / 新结果
- ⚡ 实时监控：比赛进行中时按较短间隔播报详情，比赛结束后自动停止
- 🛡️ 数据源降级：主数据源不可用时自动切换到备用数据源
- 🇨🇳 中文输出：队名、地图、英雄（Agent）名称均已中文化

## 安装

### 方式一：插件市场

在 AstrBot WebUI → 插件市场 中搜索 `vct` 安装。

### 方式二：手动安装

1. 将本仓库放入 AstrBot 的插件目录：

   ```
   data/plugins/astrbot_plugin_vct_cn/
   ```

   > 注意：目录名必须是 `astrbot_plugin_vct_cn`，且该目录下直接是 `main.py`、`metadata.yaml` 等文件。

2. 安装依赖（AstrBot 通常会自动安装 `requirements.txt`；如未自动安装可手动执行）：

   ```bash
   pip install -r data/plugins/astrbot_plugin_vct_cn/requirements.txt
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
- `pycryptodome` —— 备用数据源的响应解密（缺失时该数据源不可用，会自动走主数据源）

## 数据来源

数据来源于公开赛事页面 / 接口，仅用于赛事信息播报；如相关页面结构或接口变更，播报内容可能暂时失效，请提交 Issue。

## 目录结构

```
astrbot_plugin_vct_cn/
├── main.py             # 插件入口、命令、定时调度、渲染
├── match_parser.py     # 比赛详情解析
├── haojiao.py          # 备用数据源
├── translations.py     # 中文映射（队名 / 地图 / 英雄）
├── metadata.yaml       # 插件元信息
├── _conf_schema.json   # 插件配置 Schema
├── requirements.txt
└── README.md
```

> `monitor_state.json` 为运行期自动生成的状态文件，已加入 `.gitignore`，不会提交。

## 许可

本项目基于 [MIT License](LICENSE) 开源。
