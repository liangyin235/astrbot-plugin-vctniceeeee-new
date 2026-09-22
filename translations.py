_AGENTS_CN = {
    "jett": "捷风",
    "raze": "雷兹",
    "reyna": "芮娜",
    "neon": "霓虹",
    "phoenix": "不死鸟",
    "yoru": "夜露",
    "iso": "壹决",
    "sova": "猎枭",
    "breach": "铁臂",
    "skye": "斯凯",
    "fade": "黑梦",
    "gekko": "盖可",
    "kayo": "KAY/O",
    "kay-o": "KAY/O",
    "k-o": "KAY/O",
    "omen": "幽影",
    "brimstone": "炼狱",
    "viper": "蝰蛇",
    "astra": "星礈",
    "harbor": "海神",
    "clove": "暮蝶",
    "sage": "贤者",
    "cypher": "零",
    "killjoy": "奇乐",
    "chamber": "尚勃勒",
    "deadlock": "钢锁",
    "vyse": "维斯",
    "tejo": "钛狐",
    "waylay": "幻棱",
}


def _cn_agent(slug: str) -> str:
    return _AGENTS_CN.get((slug or "").strip().lower(), slug or "")


_MAPS_CN = {
    "sunset": "日落之城",
    "lotus": "莲华古城",
    "pearl": "深海明珠",
    "fracture": "裂变峡谷",
    "breeze": "微风岛屿",
    "icebox": "森寒冬港",
    "bind": "源工重镇",
    "haven": "隐世修所",
    "split": "霓虹町",
    "ascent": "亚海悬城",
    "abyss": "幽邃地窟",
    "summit": "天枢云阙",
    "corrode": "盐海矿镇",
    "district": "商贸区",
    "drift": "漂移",
    "glitch": "故障",
    "plaza": "广场",
    "tibet": "藏身所",
}


def _cn_map(slug: str) -> str:
    return _MAPS_CN.get((slug or "").strip().lower(), slug or "")
