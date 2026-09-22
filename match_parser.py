from __future__ import annotations

import os
import re
import urllib.request

try:
    from .translations import _cn_map
except ImportError:
    from translations import _cn_map

REQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "text/html, */*",
}


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "")
    return s.strip()


def _get_proxy_handler():
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    if proxy_url:
        return urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    return None


def fetch(url: str, referer: str = "") -> str:
    headers = dict(REQ_HEADERS)
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    handler = _get_proxy_handler()
    if handler:
        opener = urllib.request.build_opener(handler)
        with opener.open(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    else:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="ignore")


fetch_page_html = fetch


def _get_real_match_id(match_page_html: str) -> str | None:
    m = re.search(r'data-match-id="(\d+)"', match_page_html)
    return m.group(1) if m else None


def parse_match_page(html: str) -> dict | None:
    mid = re.search(r'data-match-id="(\d+)"', html)
    if not mid:
        return None
    result = {"match_id": mid.group(1)}

    # VLR HTML order: loser, colon, winner
    m = re.search(
        r'match-header-vs-score-loser"[^>]*>\s*(\d+)\s*</span>'
        r'[^<]*<span[^>]*match-header-vs-score-colon[^>]*>\s*:\s*</span>'
        r'[^<]*<span[^>]*match-header-vs-score-winner"[^>]*>\s*(\d+)\s*</span>',
        html,
        re.S,
    )
    if m:
        result["score"] = (m.group(2), m.group(1))  # winner first, loser second
    note = re.search(r'match-header-vs-note">\s*([^<]+?)\s*<', html)
    if note:
        result["header_note"] = note.group(1).strip()
    return result


def _cell_num(row: str, col: str):
    m = re.search(r'data-col="' + col + r'"[\s\S]*?(?=</div>|</span>)', row)
    cell = m.group(0) if m else ""
    for side in ("mod-both", "mod-t", "mod-ct"):
        v = re.search(r'class="side ' + side + r'">([0-9.]+)', cell)
        if v:
            try:
                return float(v.group(1)) if "." in v.group(1) else int(v.group(1))
            except ValueError:
                continue
    return None


def _parse_player_rows(block: str, teams: list[str]) -> list[dict]:
    players = []
    count = 0
    for row in re.split(r'(?=<div class="ovw-row">)', block):
        nm = re.search(r'ovw-player-name text-of">\s*([^<]+?)\s*<', row)
        if not nm:
            continue
        count += 1
        tag_m = re.search(r'ovw-player-tag ge-text-light">\s*([^<]+?)\s*<', row)
        tag = _clean(tag_m.group(1)) if tag_m else ""
        am = re.search(r'<img src="/img/vlr/game/agents/([a-z_0-9]+)\.png"', row)
        agent = am.group(1) if am else ""
        if not tag and teams:
            tag = teams[0] if count <= 5 else (teams[1] if len(teams) > 1 else tag)
        rating = _cell_num(row, "rating2")
        acs = _cell_num(row, "acs")
        kills = _cell_num(row, "kills")
        deaths = _cell_num(row, "deaths")
        assists = _cell_num(row, "assists")
        players.append(
            {
                "name": _clean(nm.group(1)),
                "team": tag,
                "agent": agent,
                "rating": float(rating) if rating is not None else 0.0,
                "acs": int(acs) if acs is not None else 0,
                "kills": int(kills) if kills is not None else 0,
                "deaths": int(deaths) if deaths is not None else 0,
                "assists": int(assists) if assists is not None else 0,
            }
        )
    return players


def _map_play_order(match_html: str) -> dict[str, int]:
    order = {}
    # Pattern 1: data-game-id + data-href with ?game= param
    for gid, n in re.findall(
        r'data-game-id="(\d+)" data-href="[^"]*\?game=(\d+)"', match_html
    ):
        order[gid] = int(n)
    if order:
        return order
    # Pattern 2: vm-stats-gamesnav-item in DOM order (left to right = map 1, 2, 3...)
    nav_items = re.findall(
        r'vm-stats-gamesnav-item[^"]*"[^>]*data-game-id="(\d+)"', match_html
    )
    for i, gid in enumerate(nav_items, 1):
        if gid not in order:
            order[gid] = i
    return order


def parse_overview(html: str) -> list[dict]:
    games = []
    blocks = re.split(
        r'(?=<div class="vm-stats-game[^"]*"[^>]*data-game-id=")', html
    )
    for b in blocks:
        gid_m = re.search(r'data-game-id="([^"]+)"', b)
        if not gid_m:
            continue
        gid = gid_m.group(1)
        if gid == "all":
            continue

        mp = re.findall(
            r'font-weight: 700[^>]*>\s*<span[^>]*>\s*([A-Za-z ]+?)\s*<', b
        )
        teams = []
        scores = {}
        hd = b[b.find("vm-stats-game-header") :]
        r_idx = hd.find("vlr-rounds")
        if r_idx != -1:
            hd = hd[:r_idx]
        mr_idx = hd.find('<div class="team mod-right">')

        def _side(name_m, total_m, part, default_total=0):
            if not name_m:
                return None
            name = name_m.group(1).strip()
            ct_m = re.search(r'<span class="mod-ct">(\d+)</span>', part)
            t_m = re.search(r'<span class="mod-t">(\d+)</span>', part)
            ct = int(ct_m.group(1)) if ct_m else 0
            t = int(t_m.group(1)) if t_m else 0
            total = int(total_m.group(1)) if total_m else (ct + t or default_total)
            return name, {"ct": ct, "t": t, "total": total}

        left_part = hd[:mr_idx] if mr_idx != -1 else hd
        left = _side(
            re.search(r'<div class="team-name">\s*([^<]+?)\s*<', left_part),
            re.search(
                r'<div class="score[^"]*"\s*style="[^"]*margin-right\s*:\s*12px[^"]*">\s*(\d+)',
                left_part,
            ),
            left_part,
        )
        if left:
            teams.append(left[0])
            scores[left[0]] = left[1]
        if mr_idx != -1:
            right_part = hd[mr_idx:]
            right = _side(
                re.search(
                    r'<div class="team mod-right">.*?<div class="team-name">\s*([^<]+?)\s*<',
                    right_part,
                    re.S,
                ),
                re.search(
                    r'<div class="score[^"]*"\s*style="[^"]*margin-left\s*:\s*8px[^"]*">\s*(\d+)',
                    right_part,
                ),
                right_part,
            )
            if right:
                teams.append(right[0])
                scores[right[0]] = right[1]
        winner = ""
        if len(teams) == 2:
            s1 = scores[teams[0]]["total"]
            s2 = scores[teams[1]]["total"]
            if s1 != s2 and max(s1, s2) >= 13:
                winner = max(teams, key=lambda t: scores[t]["total"])
        players = _parse_player_rows(b, teams)

        games.append(
            {
                "map": mp[0].strip() if mp else "",
                "map_cn": _cn_map(mp[0].strip()) if mp else "",
                "game_id": gid,
                "teams": teams,
                "scores": scores,
                "winner": winner,
                "players": players,
            }
        )
    return games


def fetch_overview(match_id: str, game_id: str = "", referer: str = "") -> str:
    url = f"https://www.vlr.gg/match/tab/overview?match_id={match_id}"
    if game_id and game_id != "all":
        url += f"&game_id={game_id}"
    return fetch(url, referer=referer)


def fetch_match_details(url_id: str) -> dict:
    page_url = f"https://www.vlr.gg/{url_id}"
    match_html = fetch(page_url, referer=page_url)
    real_id = _get_real_match_id(match_html)
    info = parse_match_page(match_html)
    games = []
    if real_id:
        # VLR overview only fills stats for the "active" game block;
        # fetch once with game_id=all to get all maps, then sort by match page order.
        try:
            ov_html = fetch_overview(real_id, referer=page_url)
            if ov_html and "ovw-row" in ov_html:
                games = parse_overview(ov_html)
        except Exception:
            pass

        order = _map_play_order(match_html)
        if order:
            games.sort(key=lambda g: order.get(g.get("game_id", ""), 9999))

    return {
        "url_id": url_id,
        "match_id": real_id,
        "match_html": match_html,
        "info": info,
        "games": games,
    }
