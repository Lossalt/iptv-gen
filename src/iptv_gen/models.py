from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Stream:
    """一条可播放地址（同一频道可有多条候选流）。"""

    url: str
    name: str = ""
    group: str = ""
    logo: str = ""
    tvg_id: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    source: str = ""  # 来源标识：remote/local 文件名

    def key(self) -> str:
        return self.url.strip()


@dataclass
class Channel:
    """归一化后的频道，聚合同名多源。"""

    name: str
    group: str = "未分组"
    logo: str = ""
    tvg_id: str = ""
    streams: list[Stream] = field(default_factory=list)

    def add_stream(self, stream: Stream) -> None:
        if stream.url and all(s.url != stream.url for s in self.streams):
            self.streams.append(stream)
        if not self.logo and stream.logo:
            self.logo = stream.logo
        if not self.tvg_id and stream.tvg_id:
            self.tvg_id = stream.tvg_id


@dataclass
class ProbeResult:
    """单条流的检测结果。"""

    url: str
    online: bool = False
    http_status: int | None = None
    latency_ms: float | None = None
    speed_mbps: float | None = None
    width: int | None = None
    height: int | None = None
    bitrate_kbps: float | None = None
    codec: str | None = None
    protocol: str = ""  # hls / ts / other
    error: str | None = None
    score: float = 0.0

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return ""

    @property
    def resolution_label(self) -> str:
        if not self.height:
            return ""
        h = self.height
        if h >= 2000:
            return "4K"
        if h >= 1000:
            return "1080P"
        if h >= 700:
            return "720P"
        if h >= 500:
            return "576P"
        return f"{h}P"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["resolution"] = self.resolution
        d["resolution_label"] = self.resolution_label
        return d


@dataclass
class RankedStream:
    stream: Stream
    probe: ProbeResult
    channel_name: str
    channel_group: str = ""
