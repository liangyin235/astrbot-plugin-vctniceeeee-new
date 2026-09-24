from __future__ import annotations

import html as _html
import json
import os
import re
import time
import urllib.request
from datetime import datetime

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain

try:
    from .match_parser import fetch_match_details
    from .translations import _cn_agent
except ImportError:  # 本地直接运行 main.py 时退化为顶层导入
    from match_parser import fetch_match_details
    from translations import _cn_agent

_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11,
    "December": 12,
}

MATCHES_URL = "https://www.vlr.gg/matches"
EVENT_NAME = "VCT CN"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
FETCH_TIMEOUT = 30
TRIGGER_MINUTES = 60  # 开赛前 60 分钟内视为"即将开始"

# 赛事筛选策略（数据源 vlr.gg/matches）：
#   1) 含中国队的比赛 —— 一律保留；
#   2) 国际赛事（VCT 全球冠军赛 / Masters）—— 保留该赛事的全部比赛，
#      这样即使中国队被淘汰，淘汰赛/决赛也能照常播报。
# 注意：地区联赛名形如 "Champions Tour 2026: China Stage 2"，含 "champions tour"，
# 必须排除，否则会把国内联赛的非中国队场次也一起播报。
INTERNATIONAL_EVENT_EXCLUDE = ("champions tour",)
INTERNATIONAL_EVENT_INCLUDE = ("champions", "masters")

_now = lambda: datetime.now()  # noqa: E731


def _date_sort_key(date_str: str):
    m = re.match(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", date_str or "")
    if m:
        return datetime(int(m.group(3)), _MONTHS.get(m.group(1), 1), int(m.group(2)))
    m2 = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str or "")
    if m2:
        return datetime(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
    return datetime(9999, 1, 1)


def _cn_date(date_str: str) -> str:
    m = re.match(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", date_str or "")
    if m:
        month, day, year = m.group(1), int(m.group(2)), int(m.group(3))
        return f"{year}年{_MONTHS.get(month, 0)}月{day}日"
    m2 = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str or "")
    if m2:
        return f"{int(m2.group(1))}年{int(m2.group(2))}月{int(m2.group(3))}日"
    return date_str or ""


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "")
    return _html.unescape(s).strip()


def _fetch_page(url: str) -> str:
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    last_err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                data = resp.read()
            return data.decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2)
    raise last_err


def _is_cn_match(body: str) -> bool:
    """比赛条目里是否含中国队（vlr.gg 用队伍国旗 <span class="flag mod-cn"> 标记）。"""
    return "mod-cn" in body


def _is_international_event(event: str) -> bool:
    """是否为国际赛事（VCT 全球冠军赛 / Masters），而非地区联赛。"""
    e = _clean(event).lower()
    if not e:
        return False
    if any(k in e for k in INTERNATIONAL_EVENT_EXCLUDE):
        return False
    return any(k in e for k in INTERNATIONAL_EVENT_INCLUDE)


def _event_label(match: dict | None) -> str:
    """该场比赛的赛事名；取不到时回退到 EVENT_NAME。"""
    return ((match or {}).get("event") or "").strip() or EVENT_NAME


def _events_header(matches: list[dict], suffix: str) -> str:
    """列表标题：只有一项赛事时显示赛事名，多项时并列显示。"""
    evs = sorted({_event_label(m) for m in matches})
    title = " / ".join(evs) if evs else EVENT_NAME
    return f"{title} · {suffix}"


def _parse_cn_matches(html: str) -> list[dict]:
    raw_matches = list(
        re.finditer(
            r'<a href="([^"]+)" class="wf-module-item match-item[^"]*"[^>]*>(.*?)</a>',
            html,
            re.S,
        )
    )
    if not raw_matches:
        return []

    dates: list[tuple[int, str]] = []
    for m in re.finditer(
        r">\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),"
        r"\s*([A-Z][a-z]+ \d{1,2}, \d{4})\s*<",
        html,
    ):
        dates.append((m.start(), m.group(1)))

    order: list[tuple[str, int, str]] = []
    for pos, d in dates:
        order.append(("D", pos, d))
    for m in raw_matches:
        order.append(("M", m.start(), m.group(1)))
    order.sort(key=lambda x: x[1])

    cur_date = None
    date_of: dict[str, str] = {}
    for kind, _pos, val in order:
        if kind == "D":
            cur_date = val
        else:
            date_of[val] = cur_date

    items = []
    for m in raw_matches:
        href, body = m.group(1), m.group(2)
        series_m = re.search(
            r'match-item-event-series[^"]*">\s*(.*?)\s*<', body, re.S
        )
        # 赛事名紧跟在 series 的 </div> 之后：
        #   <div class="match-item-event-series ...">Group Stage–Opening (C)</div>
        #   Valorant Champions 2026 </div>
        event_m = re.search(
            r'match-item-event-series[^"]*">.*?</div>\s*([^<]*?)\s*</div>',
            body,
            re.S,
        )
        event = _clean(event_m.group(1)) if event_m else ""
        # 保留规则：含中国队，或属于国际赛事（全球冠军赛 / Masters）
        if not (_is_cn_match(body) or _is_international_event(event)):
            continue
        time_m = re.search(r'match-item-time">\s*(.*?)\s*</div>', body, re.S)
        status_m = re.search(r'ml-status">\s*(.*?)\s*<', body, re.S)
        eta_m = re.search(r'ml-eta[^"]*">\s*(.*?)\s*<', body, re.S)
        teams = []
        for tm in re.finditer(
            r'match-item-vs-team([^"]*)"[^>]*>\s*'
            r'<div class="match-item-vs-team-name">.*?'
            r'text-of">\s*(?:<span[^>]*></span>\s*)?([^<]+?)\s*</div>',
            body,
            re.S,
        ):
            cls, name = tm.group(1), tm.group(2)
            teams.append({"name": _clean(name), "winner": "mod-winner" in cls})
        scores = [
            _clean(s)
            for s in re.findall(
                r'match-item-vs-team-score[^>]*>\s*([^<]*?)\s*<', body
            )
        ]
        items.append(
            {
                "href": href,
                "match_id": re.search(r"^/(\d+)/", href).group(1)
                if re.search(r"^/(\d+)/", href)
                else "",
                "date": date_of.get(href),
                "time": _clean(time_m.group(1)) if time_m else "",
                "status": _clean(status_m.group(1)) if status_m else "",
                "eta": _clean(eta_m.group(1)) if eta_m else "",
                "series": _clean(series_m.group(1)) if series_m else "",
                "event": event,
                "teams": teams,
                "scores": scores,
            }
        )
    return items


def _eta_hours(eta: str) -> float | None:
    """把 vlr 的相对时间(如 9h 30m / 2d 4h / 1mo)换算为小时数。"""
    if not eta:
        return None
    eta = eta.lower()
    weeks = re.search(r"(\d+)\s*w", eta)
    days = re.search(r"(\d+)\s*d", eta)
    hours = re.search(r"(\d+)\s*h", eta)
    mins = re.search(r"(\d+)\s*m", eta)
    total = 0.0
    if weeks:
        total += float(weeks.group(1)) * 24 * 7
    if days:
        total += float(days.group(1)) * 24
    if hours:
        total += float(hours.group(1))
    if mins:
        total += float(mins.group(1)) / 60
    return total if total > 0 else None


_TEAMS = {
    "Wolves Esports": ("WOL", "Wolves Esports"),
    "Titan Esports Club": ("TEC", "Titan Esports Club"),
    "Dragon Ranger Gaming": ("DRG", "Dragon Ranger Gaming"),
    "Bilibili Gaming": ("BLG", "Bilibili Gaming"),
    "FunPlus Phoenix": ("FPX", "FunPlus Phoenix"),
    "Trace Esports": ("TE", "Trace Esports"),
    "JD Gaming": ("JDG", "JD Gaming"),
    "JD Esports": ("JDG", "JD Esports"),
    "TYLOO": ("TYLOO", "TYLOO"),
    "Nova Esports": ("NOVA", "Nova Esports"),
    "All Gamers": ("AG", "All Gamers"),
    "Xi Lai Gaming": ("XLG", "Xi Lai Gaming"),
    "XLG Esports": ("XLG", "XLG Esports"),
    "EDward Gaming": ("EDG", "EDward Gaming"),
    "A Team": ("A", "A Team"),
    "KeepBest Gaming": ("KBG", "KeepBest Gaming"),
    "TBD": ("TBD", "待定"),
}


def _team_short(name: str) -> str:
    entry = _TEAMS.get((name or "").strip())
    return entry[0] if entry else (name or "")


def _team_display(name: str) -> str:
    entry = _TEAMS.get((name or "").strip())
    if not entry:
        return name or ""
    return entry[0]


def _norm_team(tag: str, t1n: str, t2n: str) -> str:
    if not tag:
        return tag
    if tag in (t1n, t2n):
        return tag
    if tag == _team_short(t1n):
        return t1n
    if tag == _team_short(t2n):
        return t2n
    if t1n.startswith(tag):
        return t1n
    if t2n.startswith(tag):
        return t2n
    return tag


_SERIES_CN = {
    "Group Stage": "小组赛",
    "Playoffs": "季后赛",
    "Play-In": "入围赛",
    "UB Relegation": "保级赛",
    "Upper Quarterfinals": "半区四分之一决赛",
    "Lower Round 1": "半区第一轮",
    "Lower Round 2": "半区第二轮",
    "Lower Round 3": "半区第三轮",
    "Lower Round 4": "半区第四轮",
    "Upper Semifinals": "半区半决赛",
    "Lower Semifinals": "半区半决赛",
    "Upper Final": "半区决赛",
    "Lower Final": "半区决赛",
    "Grand Final": "总决赛",
    "Week 1": "第一周",
    "Week 2": "第二周",
    "Week 3": "第三周",
    "Week 4": "第四周",
    "Week 5": "第五周",
    "Match 1": "第一场",
    "Match 2": "第二场",
    "Match 3": "第三场",
    "Round of 16": "十六强赛",
    "Round of 8": "八强赛",
    "Quarterfinals": "四分之一决赛",
    "Semifinals": "半决赛",
    "Finals": "决赛",
    "Regular Season": "常规赛",
    "Main Event": "正赛",
    # 国际赛事（冠军赛 / Masters）的阶段名
    "Opening": "揭幕战",
    "Winner's": "胜者组",
    "Elimination": "淘汰赛",
    "Decider": "决胜轮",
    "Round Robin": "循环赛",
}


def _cn_series(name: str) -> str:
    """赛段名中文化。

    支持 "Playoffs–Upper Semifinals"、"Group Stage–Opening (C)" 这类组合形式：
    逐段翻译后用 "·" 连接，并保留组别后缀 "(C)"。
    """
    name = (name or "").strip()
    if not name:
        return name
    if name in _SERIES_CN:
        return _SERIES_CN[name]
    m = re.match(r"^(.+?)\s*[–—]\s*(.+?)(\s*\([^)]*\))?$", name)
    if m:
        left = _SERIES_CN.get(m.group(1).strip(), m.group(1).strip())
        right = _SERIES_CN.get(m.group(2).strip(), m.group(2).strip())
        return f"{left}·{right}{m.group(3) or ''}"
    return name


def _cn_time(time_str: str) -> str:
    t = (time_str or "").strip()
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", t, re.I)
    if not m:
        return t
    hour, minute, ampm = int(m.group(1)), m.group(2), m.group(3).upper()
    period = "上午" if (ampm == "AM" and hour != 12) or (ampm == "PM" and hour == 12) else "下午"
    hour24 = hour if ampm == "AM" else (hour + 12 if hour != 12 else 12)
    return f"{period}{hour}:{minute}"


def _fmt_match(match: dict) -> str:
    teams = match.get("teams") or []
    if len(teams) < 2:
        return ""
    t1, t2 = teams[0], teams[1]
    scores = match.get("scores") or ["", ""]
    line = f"{_team_display(t1['name'])} vs {_team_display(t2['name'])}"
    if match.get("status") == "Completed":
        if scores and any(sc and sc not in ("-", "–") for sc in scores):
            line += f"  {scores[0]}:{scores[1] if len(scores) > 1 else '-'}"
        else:
            line += "  (完成)"
    else:
        line += f"  {_cn_time(match.get('time') or '')}".rstrip()
        tag = _cn_series(match.get("series") or "")
        event = (match.get("event") or "").strip()
        if event and tag:
            tag = f"{event} · {tag}"
        elif event:
            tag = event
        if tag:
            line += f" [{tag}]"
    return line


def _player_rank_key(p: dict):
    r = p.get("rating") or 0
    return r if r > 0 else (p.get("kills") or 0)


def _game_players(game: dict) -> list:
    """按 rating 降序返回选手列表（含中文角色）；无 rating 时按击杀降序。"""
    ps = list(game.get("players") or [])
    ps.sort(key=_player_rank_key, reverse=True)
    return ps


def _fmt_player_line(p: dict) -> str:
    line = f"{p.get('name','?')} ({_cn_agent(p.get('agent'))}) "
    rating = p.get("rating", 0) or 0
    acs = p.get("acs", 0) or 0
    if rating > 0:
        line += f"{rating:.2f} / {acs} / "
    line += f"{p.get('kills',0)}-{p.get('deaths',0)}-{p.get('assists',0)}"
    return line


def _game_mvp(game: dict) -> dict | None:
    ps = game.get("players") or []
    if not ps:
        return None
    winner = game.get("winner") or ""
    rated = [p for p in ps if (p.get("rating") or 0) > 0]
    if rated:
        return max(rated, key=lambda p: p.get("rating", 0))
    # fallback: kills, then kd_diff, then prefer winner team
    def _mvp_key(p):
        k = p.get("kills", 0)
        d = p.get("deaths", 0)
        kd_diff = k - d
        on_winner = 1 if p.get("team") == winner else 0
        return (k, kd_diff, on_winner)
    return max(ps, key=_mvp_key)


def _format_game_report(game: dict, match: dict | None = None) -> str:
    """单图播报：比分 + MVP。"""
    t1, t2 = game.get("teams") or ["", ""]
    s1 = (game.get("scores") or {}).get(t1) or {}
    s2 = (game.get("scores") or {}).get(t2) or {}
    title = game.get("map_cn") or game.get("map") or "未知地图"
    header = (
        f"{_event_label(match)} · 对局「{title}」结束\n"
        f"{_team_display(t1)} {s1.get('total',0)} : "
        f"{s2.get('total',0)} {_team_display(t2)}"
    )
    mvp = _game_mvp(game)
    lines = [header]
    if s1 or s2:
        lines.append(
            f"  {_team_short(t1)} {s1.get('ct',0)}防/{s1.get('t',0)}攻 · "
            f"{_team_short(t2)} {s2.get('ct',0)}防/{s2.get('t',0)}攻"
        )
    if mvp:
        lines.append("")
        lines.append(f"本图 MVP: {_fmt_player_line(mvp)}")
    return "\n".join(lines)


def _format_starting_report(match: dict) -> str:
    """开赛提醒：比赛即将开始时播报。"""
    teams = match.get("teams") or []
    if len(teams) < 2:
        return ""
    t1, t2 = teams[0], teams[1]
    header = f"{_event_label(match)} · 即将开赛"
    eta_h = _eta_hours(match.get("eta"))
    eta_txt = ""
    if eta_h is not None:
        if eta_h < 1:
            eta_txt = f"约 {max(1, int(round(eta_h * 60)))} 分钟后开赛"
        else:
            h = int(eta_h)
            m = int(round((eta_h - h) * 60))
            eta_txt = f"约 {h} 小时{m} 分钟后开赛"
    lines = [
        header,
        f"{_team_display(t1['name'])} vs {_team_display(t2['name'])}",
    ]
    dt = ""
    if match.get("date"):
        dt = _cn_date(match["date"]) + " " + _cn_time(match.get("time") or "")
    if dt:
        lines.append(dt)
    if eta_txt:
        lines.append(eta_txt)
    if match.get("series"):
        lines.append(f"[{_cn_series(match['series'])}]")
    return "\n".join(lines)


def _format_live_score(match: dict, games: list[dict]) -> str:
    """进行中比赛实时比分：总比分局数 + 当前进行中地图比分。"""
    teams = match.get("teams") or []
    t1 = teams[0]["name"] if teams else ""
    t2 = teams[1]["name"] if len(teams) > 1 else ""
    map_wins = {}
    for g in games:
        if g.get("winner"):
            map_wins[g["winner"]] = map_wins.get(g["winner"], 0) + 1
    w1 = map_wins.get(t1, 0)
    w2 = map_wins.get(t2, 0)
    header = (
        f"{_event_label(match)} · 比赛进行中\n"
        f"{_team_display(t1)} {w1} : {w2} {_team_display(t2)}"
    )
    lines = [header]
    for g in games:
        t1n, t2n = _teams2(g)
        s1 = (g.get("scores") or {}).get(t1n, {}).get("total", 0)
        s2 = (g.get("scores") or {}).get(t2n, {}).get("total", 0)
        mname = g.get("map_cn") or g.get("map") or "?"
        done = "已结束" if _game_done(g) else "进行中"
        lines.append(f"■ {mname}: {_team_short(t1n)} {s1} : {s2} {_team_short(t2n)} ({done})")
    return "\n".join(lines)


def _format_final_report(match: dict, games: list[dict], is_final: bool = True) -> str:
    """整场结束播报：总比分 + 每图比分 + 每图 MVP。"""
    teams = match.get("teams") or []
    scores = match.get("scores") or ["", ""]
    t1 = teams[0]["name"] if teams else ""
    t2 = teams[1]["name"] if len(teams) > 1 else ""
    header = (
        f"{_event_label(match)} · {'比赛结束' if is_final else '比赛进行中'}\n"
        f"{_team_display(t1)} {scores[0] if scores else '?'} : "
        f"{scores[1] if len(scores) > 1 else '?'} {_team_display(t2)}"
    )
    series = match.get("series")
    if series:
        header += f"\n{_cn_series(series)}"
    lines = [header]
    if not games:
        return "\n".join(lines)
    lines.append("")
    for g in games:
        t1n, t2n = _teams2(g)
        s1 = (g.get("scores") or {}).get(t1n, {})
        s2 = (g.get("scores") or {}).get(t2n, {})
        mvp = _game_mvp(g)
        won = g.get("winner") or t1n or "?"
        mvp_txt = f", MVP {_fmt_player_line(mvp)}" if mvp else ""
        lines.append(
            f"■ {g.get('map_cn') or g.get('map') or '?'}: "
            f"{t1n} {s1.get('total',0)} : {s2.get('total',0)} {t2n}  "
            f"({_team_short(won)} 胜{mvp_txt})"
        )
    return "\n".join(lines)


_BO3_GAMES = 2  # 本赛事 BO3


def _game_done(g: dict) -> bool:
    return bool(g.get("winner"))


def _teams2(g: dict) -> tuple[str, str]:
    """安全解包比赛 teams，长度不足时补空串。"""
    ts = g.get("teams") or []
    t1 = ts[0] if len(ts) > 0 else ""
    t2 = ts[1] if len(ts) > 1 else ""
    return t1, t2


_HELP_TEXT = (
    "用法:\n"
    "/vct today 今日赛程与即将开始的比赛\n"
    "/vct all 全部赛程\n"
    "/vct result 比赛结果\n"
    "/vct match <比赛ID或链接> 查看比赛详情（比分/MVP/选手数据）\n"
    "/vct bind 把当前会话设为定时播报目标\n"
    "/vct unbind 取消当前会话的定时播报\n"
    "/vct list 查看已绑定的播报目标\n"
    "/vct sid 显示当前会话 ID"
)


@register(
    "astrbot_plugin_vctniceeeee_new",
    "liangyin235",
    "VCT CN 无畏契约中国赛区比赛播报（赛程 / 比分 / 详情 / 实时监控）",
    "1.2.0",
    "",
)
class VctCnPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._scheduler = None
        self._bind_result = ""
        self._state_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "monitor_state.json"
        )
        self._state = self._load_state()
        self._bound_events: dict[str, AstrMessageEvent] = {}

    async def initialize(self):
        await self._setup_scheduler()
        # 启动后立即执行一次首检，避免等待满一个间隔才有反应
        import asyncio as _asyncio

        try:
            _asyncio.create_task(self._auto_broadcast())
        except Exception as _e:  # noqa: BLE001
            logger.error("[vct_cn] 首检任务启动失败: %s", _e)
        logger.info("[vct_cn] 插件初始化完成")

    async def terminate(self):
        """插件卸载/重载时停止调度器，避免旧任务残留导致重复播报。"""
        if self._scheduler:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception as e:  # noqa: BLE001
                logger.error("[vct_cn] 关闭调度器失败: %s", e)
            self._scheduler = None
        logger.info("[vct_cn] 插件已终止")

    # ---------- 状态持久化 ----------
    def _load_state(self) -> dict:
        try:
            if os.path.exists(self._state_path):
                with open(self._state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:  # noqa: BLE001
            logger.error("[vct_cn] 读取状态失败: %s", e)
        return {"reported": {}, "game_reported": {}}

    def _save_state(self):
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            logger.error("[vct_cn] 保存状态失败: %s", e)

    def _mark_reported(self, match_id: str):
        (self._state.setdefault("reported", {}))[match_id] = True
        self._state.setdefault("game_reported", {}).setdefault(match_id, {})
        self._save_state()

    def _mark_game_reported(self, match_id: str, game_id: str):
        self._state.setdefault("game_reported", {}).setdefault(match_id, {})[
            game_id
        ] = True
        self._save_state()

    # ---------- 定时任务 ----------
    async def _setup_scheduler(self):
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError:
            logger.error("[vct_cn] apscheduler 未安装，定时播报不可用")
            return
        self._scheduler = AsyncIOScheduler()
        interval_sec = int(self.config.get("poll_interval_min", 30)) * 60
        self._scheduler.add_job(
            self._auto_broadcast,
            IntervalTrigger(seconds=interval_sec),
            id="vct_cn_auto_broadcast",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
        live_sec = int(self.config.get("live_poll_min", 5)) * 60
        self._scheduler.add_job(
            self._live_detail_tick,
            IntervalTrigger(seconds=live_sec),
            id="vct_cn_live_detail",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            "[vct_cn] 定时任务已启动，每 %d 分钟常规检查，每 %d 分钟播报进行中详情",
            interval_sec // 60,
            live_sec // 60,
        )

    async def _target_sessions(self) -> list[str]:
        raw = self.config.get("target_sessions", [])
        if isinstance(raw, str):
            raw = [raw]
        sessions = []
        for s in raw:
            s = str(s or "").strip()
            if s and s not in sessions:
                sessions.append(s)
        return sessions

    async def _set_target_sessions(self, sessions: list[str]) -> None:
        self.config["target_sessions"] = sessions
        save = getattr(self.config, "save_config_async", None)
        if save:
            try:
                await save()
            except Exception as e:  # noqa: BLE001
                logger.error("[vct_cn] 保存配置失败: %s", e)

    async def _send(self, text: str) -> bool:
        if not text:
            return False
        chain = MessageChain(chain=[Plain(text)])
        any_sent = False
        for session_id in await self._target_sessions():
            event = self._bound_events.get(session_id)
            try:
                if event is not None:
                    await event.send(chain)
                else:
                    result = await self.context.send_message(session_id, chain)
                    if result:
                        any_sent = True
                    else:
                        logger.warning("[vct_cn] send_message returned False for %s", session_id)
            except Exception as e:  # noqa: BLE001
                logger.error("[vct_cn] 播报到 %s 失败: %s", session_id, e)
        return any_sent

    async def _notify_starting(self, matches: list[dict]):
        """开赛提醒：距离开赛 <= TRIGGER_MINUTES 分钟且未提醒过的比赛播报一次。"""
        notified = self._state.setdefault("starting_notified", {})
        for m in matches:
            mid = m.get("match_id")
            if not mid or m.get("status") != "Upcoming":
                continue
            eta_h = _eta_hours(m.get("eta"))
            if eta_h is None or eta_h <= 0 or eta_h > TRIGGER_MINUTES / 60:
                continue
            if m.get("teams") and any(
                t.get("name") in ("TBD",) for t in m.get("teams")
            ):
                continue
            if notified.get(mid):
                continue
            text = _format_starting_report(m)
            if not text:
                continue
            sent = await self._send(text)
            if sent:
                notified[mid] = True
                self._save_state()
                logger.info("[vct_cn] 已播报开赛提醒 %s", mid)

    async def _notify_live_detail(self, matches: list[dict]):
        """比赛进行中：每轮检查输出一次比赛详情（/vct match 同款），比赛结束即停。"""
        for m in matches:
            mid = m.get("match_id")
            if not mid or m.get("status") not in ("Live", "LIVE"):
                continue
            if m.get("teams") and any(
                t.get("name") in ("TBD",) for t in m.get("teams")
            ):
                continue
            try:
                det = fetch_match_details(mid)
                games = det["games"]
            except Exception as e:  # noqa: BLE001
                logger.error("[vct_cn] 拉取进行中详情 %s 失败: %s", mid, e)
                continue
            if not games:
                continue  # 暂无对局数据，跳过
            if games and all(_game_done(g) for g in games):
                continue  # 所有图已打完，停止实时播报
            text = await self._render_match_detail(mid)
            if not text or "失败" in text:
                continue
            await self._send(text)
            logger.info("[vct_cn] 已播报进行中详情 %s", mid)

    async def _live_detail_tick(self):
        """实时比赛专用轮询：每 5 分钟拉一次赛事详情，有比赛进行中才播报"""
        try:
            html = _fetch_page(MATCHES_URL)
            matches = _parse_cn_matches(html)
        except Exception as e:  # noqa: BLE001
            logger.error("[vct_cn] 实时详情拉取失败: %s", e)
            return
        if not matches:
            return
        await self._notify_live_detail(matches)

    async def _auto_broadcast(self):
        # Wait for platform to be fully connected after restart
        import asyncio as _aio
        await _aio.sleep(20)
        try:
            html = _fetch_page(MATCHES_URL)
            matches = _parse_cn_matches(html)
        except Exception as e:  # noqa: BLE001
            logger.error("[vct_cn] 自动拉取失败: %s", e)
            return
        if not matches:
            logger.info("[vct_cn] vlr.gg 当前无比赛数据，跳过本轮")
            return

        await self._notify_starting(matches)

        # 0) 检查之前 LIVE 的比赛是否已从页面消失（比赛结束被移除）
        current_mids = {m.get("match_id") for m in matches if m.get("match_id")}
        prev_live = self._state.get("prev_live_mids", [])
        for mid in prev_live:
            if mid not in current_mids and not self._state.get("reported", {}).get(mid):
                # 之前是 LIVE，现在不在页面上了 = 比赛结束被移除
                try:
                    det = fetch_match_details(mid)
                    games = det["games"]
                    if games and all(_game_done(g) for g in games):
                        # 找到对应的比赛信息（从之前的记录）
                        m_info = self._state.get("prev_live_matches", {}).get(mid, {}).copy()
                        # 从比赛详情更新 scores，映射到正确的 team 顺序
                        info = det.get("info") or {}
                        if info.get("score") and m_info.get("teams"):
                            winner_score, loser_score = info["score"]
                            # 找到赢家是哪个 team
                            winner_name = ""
                            for g in games:
                                if g.get("winner"):
                                    winner_name = g["winner"]
                                    break
                            teams = m_info["teams"]
                            t1_name = teams[0]["name"] if teams else ""
                            t2_name = teams[1]["name"] if len(teams) > 1 else ""
                            if winner_name == t1_name:
                                m_info["scores"] = [winner_score, loser_score]
                            else:
                                m_info["scores"] = [loser_score, winner_score]
                        text = _format_final_report(m_info, games, is_final=True)
                        if text:
                            sent = await self._send(text)
                            if sent:
                                self._state.setdefault("reported", {})[mid] = True
                                self._state.setdefault("game_reported", {}).setdefault(mid, {})
                                for g in games:
                                    self._state["game_reported"][mid][g.get("game_id")] = True
                                self._save_state()
                                logger.info("[vct_cn] 已播报结束（页面消失） %s", mid)
                            else:
                                logger.warning("[vct_cn] 播报结束（页面消失） %s 发送失败", mid)
                except Exception as e:
                    logger.error("[vct_cn] 页面消失比赛 %s 补发失败: %s", mid, e)

        # 记录当前 LIVE 的比赛和对应信息
        live_matches = {m.get("match_id"): m for m in matches if m.get("status") in ("Live", "LIVE") and m.get("match_id")}
        self._state["prev_live_mids"] = list(live_matches.keys())
        self._state["prev_live_matches"] = {mid: {"teams": m.get("teams"), "scores": m.get("scores"), "series": m.get("series")} for mid, m in live_matches.items()}
        self._save_state()

        # 1) 已结束但未播报的比赛（补发总结）
        boot = not self._state.get("initialized")
        if boot:
            # 首次启动：只把已有的 Completed 静默标记，不逐场抓详情，
            # 避免一次性补发几十场历史比赛
            for m in matches:
                mid = m.get("match_id")
                if mid and m.get("status") == "Completed":
                    self._state.setdefault("reported", {})[mid] = True
                    self._state.setdefault("game_reported", {}).setdefault(mid, {})
            self._state["initialized"] = True
            self._save_state()
            logger.info("[vct_cn] 首次启动，静默标记已有比赛结果")

        for m in matches:
            mid = m.get("match_id")
            if not mid or m.get("status") != "Completed":
                continue
            if self._state.get("reported", {}).get(mid):
                continue
            if m.get("teams") and any(
                t.get("name") in ("TBD",) for t in m.get("teams")
            ):
                continue
            try:
                det = fetch_match_details(mid)
                games = det["games"]
                text = _format_final_report(m, games)
                if not text:
                    continue
                sent = await self._send(text)
                if sent:
                    self._state.setdefault("reported", {})[mid] = True
                    self._state.setdefault("game_reported", {}).setdefault(mid, {})
                    for g in games:
                        self._state["game_reported"][mid][g.get("game_id")] = True
                    self._save_state()
                    logger.info("[vct_cn] \u5df2\u64ad\u62a5\u6574\u573a\u7ed3\u679c %s", mid)
                else:
                    logger.warning("[vct_cn] \u64ad\u62a5\u6574\u573a\u7ed3\u679c %s \u53d1\u9001\u5931\u8d25\uff0c\u4e0d\u6807\u8bb0\u5df2\u64ad\u62a5", mid)
            except Exception as e:  # noqa: BLE001
                logger.error("[vct_cn] 补发比赛结果 %s 失败: %s", mid, e)

        # 2) 进行中/开赛在即的比赛：检测已结束的单图并逐图播报
        for m in matches:
            mid = m.get("match_id")
            if not mid or m.get("status") not in ("Upcoming", "Live", "LIVE"):
                continue
            if m.get("status") == "Upcoming":
                eta = _eta_hours(m.get("eta"))
                if eta is None or eta > 24:
                    continue
            if m.get("teams") and any(
                t.get("name") in ("TBD",) for t in m.get("teams")
            ):
                continue
            try:
                det = fetch_match_details(mid)
                games = det["games"]
            except Exception as e:  # noqa: BLE001
                logger.error("[vct_cn] 拉取比赛详情 %s 失败: %s", mid, e)
                continue
            if not games:
                continue
            game_done_ids = {g.get("game_id") for g in games if _game_done(g)}
            pending = game_done_ids - set(
                self._state.setdefault("game_reported", {}).setdefault(mid, {})
            )
            for g in games:
                if g.get("game_id") not in pending:
                    continue
                text = _format_game_report(g, m)
                if not text:
                    continue
                sent = await self._send(text)
                if sent:
                    self._state["game_reported"][mid][g.get("game_id")] = True
                    self._save_state()
                    logger.info("[vct_cn] 已播报单图结果 %s/%s", mid, g.get("game_id"))
            # 3) 整场打完：任一队赢满 BO 数（BO3 需同队赢 2 图）
            wins: dict[str, int] = {}
            for g in games:
                w = g.get("winner")
                if w:
                    wins[w] = wins.get(w, 0) + 1
            max_wins = max(wins.values()) if wins else 0
            if max_wins < 2:
                logger.info("[vct_cn] 比赛 %s 尚未结束 (max_wins=%d)，跳过整场播报", mid, max_wins)
            else:
                text = _format_final_report(m, games, is_final=True)
                if text:
                    sent = await self._send(text)
                    if sent:
                        self._state.setdefault("reported", {})[mid] = True
                        self._save_state()
                        logger.info("[vct_cn] 已播报整场结果 %s", mid)
                    else:
                        logger.warning("[vct_cn] 播报整场结果 %s 发送失败，不标记已播报", mid)

        # 4) 进行中比赛的详情播报由独立任务 _live_detail_tick 每 5 分钟执行

        logger.info("[vct_cn] 定时播报检查完成")

    # ---------- 手动命令 ----------
    @filter.command("vct")
    async def vct_command(self, event: AstrMessageEvent):
        args = (event.message_str or "").strip().split()
        sub = args[1].lower() if len(args) > 1 else ""

        # 刷新华发送事件缓存：任何 /vct 命令都会让当前会话具备自动播报能力（无需重新 bind）
        cur_umo = event.unified_msg_origin or event.session_id or ""
        if cur_umo and cur_umo in await self._target_sessions():
            self._bound_events[cur_umo] = event

        if not sub:
            yield event.plain_result(_HELP_TEXT)
            return

        if sub in ("bind", "绑定", "订阅"):
            await self._do_bind(event)
            yield event.plain_result(self._bind_result or "")
            return
        if sub in ("unbind", "解绑", "取消订阅"):
            await self._do_unbind(event)
            yield event.plain_result(self._bind_result or "")
            return
        if sub in ("list", "列表", "目标"):
            sessions = await self._target_sessions()
            if not sessions:
                yield event.plain_result("当前没有绑定任何播报目标群\n使用 /vct bind 绑定当前会话")
            else:
                yield event.plain_result(
                    "已绑定的播报目标:\n" + "\n".join(f"  - {s}" for s in sessions)
                )
            return
        if sub in ("sid",):
            yield event.plain_result(
                f"当前会话 unified_msg_origin: {event.unified_msg_origin or '无法获取'}"
            )
            return

        if sub in ("match", "详情", "详细") and len(args) > 2:
            yield event.plain_result(await self._render_match_detail(args[2]))
            return

        try:
            matches = _parse_cn_matches(_fetch_page(MATCHES_URL))
        except Exception as e:  # noqa: BLE001
            yield event.plain_result(f"获取失败: {e}")
            return

        if not matches:
            yield event.plain_result("未解析到任何比赛数据（页面结构可能已变化）")
            return

        if sub in ("today", "今日", "今天"):
            text = self._render_today(matches)
        elif sub in ("all", "全部", "赛程"):
            text = self._render_all(matches)
        elif sub in ("result", "results", "结果", "比分"):
            text = self._render_results(matches)
        else:
            text = _HELP_TEXT
        yield event.plain_result(text)

    async def _render_match_detail(self, raw: str) -> str:
        mid = ""
        m = re.search(r"vlr\.gg/(\d+)/", raw)
        m2 = re.search(r"^(\d{4,})$", raw.strip())
        if m:
            mid = m.group(1)
        elif m2:
            mid = m2.group(1)
        if not mid:
            return "用法: /vct match <比赛ID或 vlr.gg 链接>"
        try:
            det = fetch_match_details(mid)
            info = det["info"]
            games = det["games"]
        except Exception as e:  # noqa: BLE001
            return f"拉取比赛详情失败: {e}"

        lines = [f"比赛 #{mid}"]
        if info and info.get("score"):
            lines.append(f"总比分 {info['score'][0]} : {info['score'][1]}")
        note = info.get("header_note") if info else ""
        note_cn = _cn_series(note) if note else ""
        if note_cn and note_cn != note:
            lines.append(note_cn)

        if not games:
            lines.append("（暂无对局数据，比赛可能尚未开始）")
            return "\n".join(lines)

        snippet_games = games[:4]
        for g in snippet_games:
            t1n, t2n = _teams2(g)
            s1 = (g.get("scores") or {}).get(t1n, {})
            s2 = (g.get("scores") or {}).get(t2n, {})
            lines.append("")
            title = g.get("map_cn") or g.get("map") or "未知地图"
            lines.append(
                f"■ {title}: {_team_display(t1n)} {s1.get('total',0)} : "
                f"{s2.get('total',0)} {_team_display(t2n)}"
            )
            if s1 and s2:
                lines.append(
                    f"  {_team_short(t1n)} {s1.get('ct',0)}防/{s1.get('t',0)}攻 · "
                    f"{_team_short(t2n)} {s2.get('ct',0)}防/{s2.get('t',0)}攻"
                )
            raw_ps = g.get("players") or []
            if raw_ps:
                # 按 p["team"]（vlr.gg 的队伍 tag）分组，每名选手单独一行
                from collections import defaultdict
                grps = defaultdict(list)
                for p in raw_ps:
                    grps[_norm_team(p.get("team") or "", t1n, t2n)].append(p)
                for tn in (t1n, t2n):
                    ps = sorted(grps.get(tn, []), key=_player_rank_key, reverse=True)
                    if ps:
                        lines.append(f"  {_team_short(tn)}")
                        for p in ps:
                            lines.append(f"    {_fmt_player_line(p)}")
            else:
                ps = _game_players(g)
                for i, p in enumerate(ps[:5]):
                    lines.append(f"  {i+1}. {_fmt_player_line(p)}")
            mvp = _game_mvp(g)
            if mvp:
                lines.append(f"  MVP: {_fmt_player_line(mvp)}")
        return "\n".join(lines)

    async def _do_bind(self, event: AstrMessageEvent):
        session_id = event.unified_msg_origin or event.session_id
        if not session_id:
            self._bind_result = "无法获取当前会话 ID，绑定失败"
            return
        sessions = await self._target_sessions()
        if session_id not in sessions:
            sessions.append(session_id)
            await self._set_target_sessions(sessions)
        # 保存事件对象用于主动播报（事件来自该会话所属平台，发送可靠）
        self._bound_events[session_id] = event
        self._bind_result = (
            f"绑定成功! 定时播报目标: {session_id}\n(每 "
            f"{self.config.get('poll_interval_min', 60)} 分钟检查一次)"
        )

    async def _do_unbind(self, event: AstrMessageEvent):
        session_id = event.unified_msg_origin or event.session_id
        sessions = await self._target_sessions()
        if not session_id:
            await self._set_target_sessions([])
            self._bound_events.clear()
            self._bind_result = "无法获取当前会话，已清空全部播报目标"
            return
        if session_id in sessions:
            sessions.remove(session_id)
            await self._set_target_sessions(sessions)
            self._bound_events.pop(session_id, None)
            self._bind_result = f"已取消播报: {session_id}"
            return
        self._bind_result = "当前会话不在播报目标中"

    def _render_today(self, matches: list[dict]) -> str:
        today = [
            m
            for m in matches
            if m.get("status") in ("Upcoming", "Live", "LIVE")
            and (h := _eta_hours(m.get("eta"))) is not None
            and h <= 24
            and not (
                m.get("teams")
                and any(t.get("name") in ("TBD",) for t in m.get("teams"))
            )
        ]
        if not today:
            return "24 小时内暂无 VCT CN 比赛"
        lines = [_events_header(today, "近 24 小时"), ""]
        grouped: dict[str, list[dict]] = {}
        for m in today:
            grouped.setdefault(m.get("date") or "近期", []).append(m)
        for date, ms in sorted(grouped.items(), key=lambda kv: _date_sort_key(kv[0])):
            lines.append(f"■ {_cn_date(date)}")
            for m in ms:
                line = _fmt_match(m)
                if line:
                    lines.append("  " + line)
        return "\n".join(lines)

    def _render_all(self, matches: list[dict]) -> str:
        lines = [_events_header(matches, "全部赛程"), ""]
        grouped: dict[str, list[dict]] = {}
        for m in matches:
            if not m.get("date"):
                continue
            grouped.setdefault(m.get("date"), []).append(m)
        for date, ms in sorted(grouped.items(), key=lambda kv: _date_sort_key(kv[0])):
            valid = [
                m
                for m in ms
                if m.get("status") != "Completed"
                and not (
                    m.get("teams")
                    and any(t.get("name") in ("TBD",) for t in m.get("teams"))
                )
            ]
            if not valid:
                continue
            lines.append(f"■ {_cn_date(date)}")
            for m in valid:
                line = _fmt_match(m)
                if line:
                    lines.append("  " + line)
        return "\n".join(lines)

    def _render_results(self, matches: list[dict]) -> str:
        completed = [m for m in matches if m.get("status") == "Completed"]
        if not completed:
            return "暂无已完成的比赛结果"
        lines = [_events_header(completed, "比赛结果"), ""]
        grouped: dict[str, list[dict]] = {}
        for m in completed:
            grouped.setdefault(m.get("date") or "未知日期", []).append(m)
        for date, ms in sorted(grouped.items(), key=lambda kv: _date_sort_key(kv[0])):
            lines.append(f"■ {_cn_date(date)}")
            for m in ms[:10]:
                line = _fmt_match(m)
                if line:
                    lines.append("  " + line)
        return "\n".join(lines)