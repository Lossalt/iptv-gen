from __future__ import annotations

from pathlib import Path

from .normalize import normalize_name

# alias.txt：一行一个标准频道，逗号分隔别名。首个为显示名。
#   CCTV1,CCTV-1,CCTV1综合,CCTV-1 综合,中央一台
#   湖南卫视,湖南卫视HD,湖南高清卫视


def load_alias_map(path: str | Path | None) -> dict[str, str]:
    """返回 归一化别名 → 标准显示名。"""
    mapping: dict[str, str] = {}
    if not path:
        return mapping
    p = Path(path)
    if not p.exists():
        return mapping
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 兼容逗号 / 竖线 / 冒号分隔
        if "|" in line:
            parts = [x.strip() for x in line.split("|")]
        elif "," in line:
            parts = [x.strip() for x in line.split(",")]
        else:
            parts = [line]
        parts = [x for x in parts if x]
        if not parts:
            continue
        canonical = parts[0]
        for item in parts:
            key = normalize_name(item)
            if key and key not in mapping:
                mapping[key] = canonical
        # 标准名本身也指向显示名
        ckey = normalize_name(canonical)
        if ckey:
            mapping[ckey] = canonical
    return mapping


def resolve_name(name: str, alias_map: dict[str, str] | None = None) -> str:
    """别名解析 + 归一化，返回标准频道名。"""
    if not name:
        return ""
    key = normalize_name(name)
    if alias_map and key in alias_map:
        return alias_map[key]
    if alias_map:
        # 再试去噪后的原名
        bare = normalize_name(name.replace(" ", ""))
        if bare in alias_map:
            return alias_map[bare]
    return key or name.strip()
