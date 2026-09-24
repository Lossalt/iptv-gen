from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .alias import resolve_name
from .models import Channel

# template.txt：只导出列表中的频道，并按文件顺序排序。
# 支持天马 #genre# 分组：
#   央视,#genre#
#   CCTV1
#   CCTV2
#   卫视,#genre#
#   湖南卫视
# 也支持简单列表（无分组标题则保留频道原 group）。
# 文件不存在或为空 → 不过滤，导出全部。


@dataclass
class TemplateItem:
    name: str
    group: str = ""


def load_template(path: str | Path | None) -> list[TemplateItem]:
    items: list[TemplateItem] = []
    if not path:
        return items
    p = Path(path)
    if not p.exists():
        return items
    current_group = ""
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        # 纯注释跳过；#genre# 分组行保留
        if line.startswith("#") and "#genre#" not in line.lower():
            continue
        lower = line.lower()
        if lower.endswith("#genre#") or lower.endswith(",#genre#"):
            name = line.split(",")[0].strip()
            current_group = name
            continue
        # 允许 "频道,http://..." 形式，只取名称
        name = line.split(",", 1)[0].strip()
        if name:
            items.append(TemplateItem(name=name, group=current_group))
    return items


def apply_template(
    channels: list[Channel],
    template: list[TemplateItem],
    alias_map: dict[str, str] | None = None,
) -> list[Channel]:
    """按模板筛选并排序。模板为空则原样返回（经 sort_channels 后的顺序）。"""
    if not template:
        return channels

    index: dict[str, Channel] = {}
    for ch in channels:
        key = resolve_name(ch.name, alias_map)
        # 已有则保留流更多的那条元数据
        if key not in index:
            index[key] = ch

    picked: list[Channel] = []
    seen: set[str] = set()
    for item in template:
        key = resolve_name(item.name, alias_map)
        if not key or key in seen:
            continue
        ch = index.get(key)
        if ch is None:
            continue
        seen.add(key)
        # 模板分组优先
        if item.group:
            ch.group = item.group
        # 显示名尽量用模板/别名标准名
        pretty = resolve_name(item.name, alias_map) or item.name
        if pretty:
            ch.name = pretty
        picked.append(ch)
    return picked
