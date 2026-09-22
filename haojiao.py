from __future__ import annotations

import base64
import hashlib
import json
import random
import string
import time
import urllib.request

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    HAS_AES = True
except ImportError:  # 无 pycryptodome 时降级（解密不可用）
    HAS_AES = False

HJ_BASE = "https://api.haojiao.cc/wiki"
HJ_GAME_VALORANT = "t2Ud5pOQlscKLbRC"
_SIGN_KEY = "N61P#=Pf$yz=fwFZa)U8"
_AES_KEY = "B-:9bzB8K%~q{Au?^>Pfl*)k"  # 24 字节 => AES-192
_AES_IV = _AES_KEY[:16]
_APP_VERSION = "1.52.159"
_TIMEOUT = 30

_STATUS_MAP = {1: "Upcoming", 2: "Live", 3: "Completed"}

# 号角队伍缩写 -> 插件内部英文队名（对齐 vlr.gg / _TEAMS）
_TEAM_ALIASES = {
    "BLG": "Bilibili Gaming",
    "TE": "Trace Esports",
    "XLG": "Xi Lai Gaming",
    "EDG": "EDward Gaming",
    "FPX": "FunPlus Phoenix",
    "TEC": "Titan Esports Club",
    "TYL": "TYLOO",
    "DRG": "Dragon Ranger Gaming",
    "JDG": "JD Gaming",
    "WOL": "Wolves Esports",
    "NOVA": "Nova Esports",
    "AG": "All Gamers",
    "KBG": "KeepBest Gaming",
    "TBD": "TBD",
}


def _headers() -> dict:
    ts = str(int(time.time() * 1000))
    nonce = "".join(
        random.choices(string.ascii_letters + string.digits, k=10)
    )
    sign = hashlib.sha1((_SIGN_KEY + nonce + ts).encode()).hexdigest()
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
        ),
        "Referer": "https://web.haojiao.cc/",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "x-hj-timestamp": ts,
        "x-hj-nonce": nonce,
        "x-hj-os": "web",
        "x-hj-sign": sign,
        "x-hj-version": _APP_VERSION,
    }


def _decrypt(body: str) -> str:
    if not HAS_AES:
        raise RuntimeError("缺少 pycryptodome，无法解密号角响应")
    raw = base64.b64decode(body)
    cipher = AES.new(_AES_KEY.encode(), AES.MODE_CBC, _AES_IV.encode())
    return unpad(cipher.decrypt(raw), 16).decode("utf-8")


def _call(method: str, path: str, data: dict | None = None) -> dict:
    url = HJ_BASE + path
    payload = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=payload, headers=_headers(), method=method)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        ctype = resp.headers.get("Content-Type", "")
        body = resp.read().decode("utf-8", errors="ignore")
    if "text/plain" in ctype:
        body = _decrypt(body)
    return json.loads(body)


def fetch_matches(
    start_ms: int | None = None,
    end_ms: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """号角赛程列表，返回 {count, list}。时间参数为毫秒时间戳。"""
    data: dict = {"game_id": HJ_GAME_VALORANT, "page": page, "page_size": page_size}
    if start_ms:
        data["start_time"] = start_ms
    if end_ms:
        data["end_time"] = end_ms
    res = _call("POST", "/api/v1/match/list_visitor", data)
    return res.get("data") or {"count": 0, "list": []}


def fetch_battle(match_id: str) -> dict:
    """号角比赛详情（总比分/赛段/队伍）。"""
    res = _call("GET", f"/api/v1/match/battle_detail?match_id={match_id}")
    return res.get("data") or {}


def _team_name(camp: dict) -> str:
    short = (camp.get("name_short") or "").strip()
    if short in _TEAM_ALIASES:
        return _TEAM_ALIASES[short]
    return (camp.get("name_main") or short or "?").strip()


def to_plugin_match(item: dict, now_ms: int | None = None) -> dict:
    """号角原始条目 -> 插件赛程 dict（与 parse_page 输出兼容）。"""
    vs = item.get("versus_info") or {}
    main_camps = vs.get("main_camp") or []
    guest_camps = vs.get("guest_camp") or []
    main = main_camps[0] if main_camps else {}
    guest = guest_camps[0] if guest_camps else {}
    t1 = _team_name(main) if main else "TBD"
    t2 = _team_name(guest) if guest else "TBD"
    status = _STATUS_MAP.get(item.get("match_status"), "Upcoming")
    start_ms = item.get("match_start_time")
    start_str = item.get("match_start_time_str") or ""
    date = start_str[:10]
    time_str = start_str[11:16]
    eta = ""
    if start_ms and now_ms:
        diff_h = (start_ms - now_ms) / 3600000.0
        if diff_h > 0:
            h = int(diff_h)
            m = int(round((diff_h - h) * 60))
            eta = f"{h}h {m}m" if h else f"{m}m"
    is_main_win = vs.get("is_main_win")
    if is_main_win is None:
        try:
            ms = int(str(vs.get("main_score") or ""))
            gs = int(str(vs.get("guest_score") or ""))
            if str(vs.get("main_score") or "").strip() and str(
                vs.get("guest_score") or ""
            ).strip():
                is_main_win = 1 if ms > gs else 0
        except (TypeError, ValueError):
            is_main_win = None
    teams = [{"name": t1, "winner": is_main_win == 1}]
    if guest:
        teams.append({"name": t2, "winner": is_main_win == 0})
    scores = [
        str(vs.get("main_score") or ""),
        str(vs.get("guest_score") or ""),
    ]
    group = item.get("tournament_group_info") or {}
    stage = item.get("stage_info") or {}
    series = " ".join(
        x
        for x in (
            group.get("name_main", ""),
            stage.get("stage_name", ""),
            item.get("schedule_name") or "",
        )
        if x
    )
    return {
        "href": "",
        "match_id": item.get("unique_id") or item.get("match_id") or "",
        "source": "haojiao",
        "date": date,
        "time": time_str,
        "status": status,
        "eta": eta,
        "series": series,
        "teams": teams,
        "scores": scores,
    }
