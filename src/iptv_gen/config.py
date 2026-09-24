from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CheckConfig:
    timeout_sec: float = 5.0
    connect_timeout_sec: float = 3.0
    concurrency: int = 32
    download_bytes: int = 256 * 1024  # 测速采样字节数
    enable_ffprobe: bool = True
    ffprobe_timeout_sec: float = 6.0
    user_agent: str = (
        "Mozilla/5.0 (Linux; Android 12; TV) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


@dataclass
class RankConfig:
    # 排序权重（总分约 0~100）
    w_online: float = 40.0
    w_resolution: float = 25.0
    w_speed: float = 20.0
    w_latency: float = 10.0
    w_bitrate: float = 5.0
    # 阈值
    min_resolution_height: int = 360
    min_speed_mbps: float = 0.3
    max_latency_ms: float = 4000.0
    max_per_channel: int = 5
    include_dead: bool = False
    sort_by: str = "score"  # score | resolution | speed | latency


@dataclass
class AppConfig:
    project_root: Path
    remote_sources_file: Path
    local_sources_dir: Path
    output_dir: Path
    output_m3u: str = "iptv-ranked.m3u"
    output_txt: str = "iptv-ranked.txt"
    output_report: str = "check-report.json"
    epg_url: str = "https://epg.112114.xyz/pp.xml"
    fetch_timeout_sec: float = 15.0
    check: CheckConfig = field(default_factory=CheckConfig)
    rank: RankConfig = field(default_factory=RankConfig)

    @staticmethod
    def load(path: str | Path | None = None) -> "AppConfig":
        root = Path(path).resolve().parent if path else Path.cwd()
        cfg_path = Path(path) if path else root / "config" / "config.json"
        data: dict[str, Any] = {}
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            root = cfg_path.resolve().parent.parent
        check = CheckConfig(**data.get("check", {}))
        rank = RankConfig(**data.get("rank", {}))
        paths = data.get("paths", {})
        return AppConfig(
            project_root=root,
            remote_sources_file=root / paths.get("remote_sources_file", "sources/remote.txt"),
            local_sources_dir=root / paths.get("local_sources_dir", "sources/local"),
            output_dir=root / paths.get("output_dir", "output"),
            output_m3u=data.get("output_m3u", "iptv-ranked.m3u"),
            output_txt=data.get("output_txt", "iptv-ranked.txt"),
            output_report=data.get("output_report", "check-report.json"),
            epg_url=data.get("epg_url", "https://epg.112114.xyz/pp.xml"),
            fetch_timeout_sec=float(data.get("fetch_timeout_sec", 15.0)),
            check=check,
            rank=rank,
        )
