from __future__ import annotations

import re
import unicodedata

from .models import Channel, Stream

# 常见后缀噪音（清晰度/源标记），归一化时去掉，便于多源合并
_NOISE = re.compile(
    r"[\s_\-]*("
    r"超清|高清|标清|蓝光|流畅|"
    r"HD|SD|FHD|UHD|4K|8K|H265|H264|HEVC|AVC|"
    r"IPV4|IPV6|IPv4|IPv6|"
    r"备用|备份|线路\s*\d*|源\s*\d*|"
    r"\d{3,4}[PpIi]|1080|720|576|480"
    r")[\s_\-]*$",
    re.I,
)

_CCTV_RE = re.compile(r"^CCTV[\s\-_]*(\d+\+?)(.*)$", re.I)
_BRACKET_RE = re.compile(r"[\(（][^\)）]*[\)）]")
# CCTV 常见「台标副标题」，归一化键里去掉，避免 CCTV1 / CCTV1综合 分裂
_CCTV_DESC = re.compile(
    r"^[\s\-_·]*("
    r"综合|财经|综艺|中文国际|体育|电影|国防军事|军事农业|电视剧|纪录|科教|戏曲|"
    r"社会与法|新闻|少儿|音乐|农业农村|体育赛事|奥林匹克|"
    r"欧洲|美洲|高清|超清|标清|频道"
    r")+$",
    re.I,
)


def normalize_name(name: str) -> str:
    """频道名归一化：全角半角、去括号备注、去清晰度后缀、CCTV 统一。"""
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).strip()
    s = _BRACKET_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" -_·|/")
    s = _NOISE.sub("", s).strip(" -_·|/")
    m = _CCTV_RE.match(s)
    if m:
        num = m.group(1).upper().replace("＋", "+")
        rest = (m.group(2) or "").strip()
        rest = _NOISE.sub("", rest).strip(" -_·|/")
        # 副标题只是描述 → 键收成 CCTV{n}；真正不同频道（5+/4欧洲等）保留
        if rest and _CCTV_DESC.match(rest):
            rest = ""
        s = f"CCTV{num}" + (f"-{rest}" if rest else "")
    return s or name.strip()


def group_channels(
    streams: list[Stream],
    default_group: str = "未分组",
    alias_map: dict[str, str] | None = None,
) -> list[Channel]:
    """按归一化频道名（可叠加别名表）合并多条流。"""
    # 延迟 import，避免与 alias 模块循环
    from .alias import resolve_name

    buckets: dict[str, Channel] = {}
    order: list[str] = []
    for st in streams:
        key = resolve_name(st.name, alias_map) if alias_map else normalize_name(st.name)
        if not key:
            key = st.name or st.url
        if key not in buckets:
            group = st.group or default_group
            buckets[key] = Channel(name=key, group=group, logo=st.logo, tvg_id=st.tvg_id)
            order.append(key)
        buckets[key].add_stream(st)
    return [buckets[k] for k in order]


def preferred_group_order() -> list[str]:
    """国内常见分组展示顺序。"""
    return [
        "央视",
        "卫视",
        "高清",
        "地方",
        "港澳台",
        "体育",
        "影视",
        "新闻",
        "少儿",
        "其他",
        "未分组",
    ]


def sort_channels(channels: list[Channel]) -> list[Channel]:
    order = preferred_group_order()
    rank = {g: i for i, g in enumerate(order)}

    def key(ch: Channel):
        g = ch.group or "未分组"
        gi = rank.get(g, len(order))
        # 细分：央视 CCTV 编号
        m = re.match(r"CCTV(\d+)", ch.name, re.I)
        cctv_n = int(m.group(1)) if m else 999
        return (gi, cctv_n, ch.name)

    # 先把 group 尽量映射到标准桶
    mapped: list[Channel] = []
    for ch in channels:
        g = ch.group or ""
        if not g:
            ch.group = "未分组"
        elif re.search(r"央视|CCTV", g, re.I):
            ch.group = "央视"
        elif re.search(r"卫视", g):
            ch.group = "卫视"
        elif re.search(r"体育|sport", g, re.I):
            ch.group = "体育"
        elif re.search(r"影|剧|movie|film", g, re.I):
            ch.group = "影视"
        elif re.search(r"少儿|卡通|动画|kids|cartoon", g, re.I):
            ch.group = "少儿"
        elif re.search(r"新闻|news", g, re.I):
            ch.group = "新闻"
        elif re.search(r"港|澳|台|HK|TW|MT", g, re.I):
            ch.group = "港澳台"
        elif re.search(r"地方|北京|上海|广东|浙江|江苏|山东|四川|湖南|湖北|河南|河北|"
                       r"安徽|福建|江西|辽宁|吉林|黑龙江|陕西|山西|甘肃|青海|新疆|西藏|"
                       r"宁夏|内蒙古|广西|云南|贵州|海南|重庆|天津", g):
            ch.group = "地方"
        mapped.append(ch)
    return sorted(mapped, key=key)
