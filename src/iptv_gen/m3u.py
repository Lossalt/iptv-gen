from __future__ import annotations

import re

from .models import Channel, Stream

_ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"')
_USER_AGENT_RE = re.compile(r"user-agent\s*=\s*([^;]+)", re.I)
_REFERRER_RE = re.compile(r"referer\s*=\s*([^;]+)", re.I)


def _parse_extinf(line: str) -> tuple[str, dict[str, str]]:
    """解析 `#EXTINF:<duration> <attrs>,<display name>`。

    兼容：`#EXTINF:-1 tvg-id="x",Name`、`#EXTINF:-1,Name`、
    以及属性里 URL 含逗号的情况。
    """
    s = line.strip()
    if not s.upper().startswith("#EXTINF"):
        return "", {}
    body = s.split(":", 1)[1] if ":" in s else ""
    # 从右往左找不在引号内的逗号，其后为显示名
    name, attr_part = _split_outside_quotes(body)
    attrs: dict[str, str] = {k.lower(): v for k, v in _ATTR_RE.findall(attr_part)}
    name = _ATTR_RE.sub("", name).strip(" ,\t")
    if not name:
        name = (attrs.get("tvg-name") or "").strip()
    return name, attrs


def _split_outside_quotes(body: str) -> tuple[str, str]:
    """按引号外最后一个逗号切成 (name, attr_part)。"""
    in_quote = False
    last_comma = -1
    for i, ch in enumerate(body):
        if ch == '"':
            in_quote = not in_quote
        elif ch == "," and not in_quote:
            last_comma = i
    if last_comma == -1:
        return body.strip(), ""
    return body[last_comma + 1 :].strip(), body[:last_comma]


def parse_m3u_text(text: str, source: str = "") -> list[Stream]:
    """解析 M3U / 天马 / txt 混合文本，返回 Stream 列表。"""
    streams: list[Stream] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    pending_name = ""
    pending_attrs: dict[str, str] = {}
    pending_headers: dict[str, str] = {}

    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        i += 1
        if not raw or raw.startswith("#EXTM3U"):
            continue
        if raw.upper().startswith("#EXTINF"):
            pending_name, pending_attrs = _parse_extinf(raw)
            pending_headers = {}
            continue
        if raw.upper().startswith("#EXTVLCOPT") or raw.upper().startswith("#KODIPROP"):
            ua = _USER_AGENT_RE.search(raw)
            ref = _REFERRER_RE.search(raw)
            if ua:
                pending_headers["User-Agent"] = ua.group(1).strip().strip('"')
            if ref:
                pending_headers["Referer"] = ref.group(1).strip().strip('"')
            continue
        if raw.startswith("#"):
            continue
        # URL 行；天马 txt 形如 Name,http://...
        url = raw
        name = pending_name
        if not pending_attrs and "," in raw and not raw.startswith("http"):
            name, _, url = raw.partition(",")
            name, url = name.strip(), url.strip()
        if not url:
            continue
        if not name:
            name = url
        stream = Stream(
            url=url.strip(),
            name=name.strip(),
            group=(pending_attrs.get("group-title") or pending_attrs.get("group") or "").strip(),
            logo=pending_attrs.get("tvg-logo", ""),
            tvg_id=pending_attrs.get("tvg-id", ""),
            headers=dict(pending_headers),
            source=source,
        )
        streams.append(stream)
        pending_name, pending_attrs, pending_headers = "", {}, {}
    return streams


def parse_m3u_file(path: str) -> list[Stream]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse_m3u_text(f.read(), source=path)


def generate_m3u(
    items: list[tuple[Channel, list]],  # (channel, ranked_probes_desc)
    epg_url: str = "",
    include_dead: bool = False,
    max_per_channel: int = 5,
) -> str:
    """生成标准 M3U。items 已按频道排序，内部流按得分降序。"""
    header = "#EXTM3U"
    if epg_url:
        header += f' x-tvg-url="{epg_url}" url-tvg="{epg_url}"'
    lines = [header]
    for channel, ranked in items:
        written = 0
        for probe in ranked:
            if not include_dead and not probe.online:
                continue
            if written >= max_per_channel:
                break
            stream = next((s for s in channel.streams if s.url == probe.url), None)
            if stream is None:
                continue
            display = channel.name
            if probe.resolution_label:
                display = f"{display}·{probe.resolution_label}"
            attrs = []
            if channel.tvg_id or stream.tvg_id:
                attrs.append(f'tvg-id="{channel.tvg_id or stream.tvg_id}"')
            if channel.logo or stream.logo:
                attrs.append(f'tvg-logo="{channel.logo or stream.logo}"')
            attrs.append(f'group-title="{channel.group or "未分组"}"')
            attr_str = " " + " ".join(attrs) if attrs else ""
            lines.append(f"#EXTINF:-1{attr_str},{display}")
            if stream.headers:
                # 兼容部分播放器的 UA / Referer
                for k, v in stream.headers.items():
                    if k.lower() == "user-agent":
                        lines.append(f"#EXTVLCOPT:http-user-agent={v}")
                    elif k.lower() == "referer":
                        lines.append(f"#EXTVLCOPT:http-referrer={v}")
            lines.append(stream.url)
            written += 1
        if written == 0 and include_dead and channel.streams:
            # 无可用流时输出第一条，避免频道整块消失
            s = channel.streams[0]
            lines.append(
                f'#EXTINF:-1 group-title="{channel.group or "未分组"}",{channel.name}'
            )
            lines.append(s.url)
    return "\n".join(lines) + "\n"


def generate_txt(items: list[tuple[Channel, list]], max_per_channel: int = 5) -> str:
    """天马/DIYP txt 格式：频道名,URL 多行。"""
    lines: list[str] = []
    for channel, ranked in items:
        written = 0
        for probe in ranked:
            if not probe.online:
                continue
            if written >= max_per_channel:
                break
            stream = next((s for s in channel.streams if s.url == probe.url), None)
            if stream is None:
                continue
            lines.append(f"{channel.name},{stream.url}")
            written += 1
    return "\n".join(lines) + "\n"
