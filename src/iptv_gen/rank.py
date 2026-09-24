from __future__ import annotations

from .config import RankConfig
from .models import Channel, ProbeResult, RankedStream, Stream


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_probe(probe: ProbeResult, cfg: RankConfig) -> float:
    """综合得分：连通 > 清晰度 > 速率 > 延迟 > 码率。"""
    if not probe.online:
        return -1.0

    # 硬过滤仍参与排序但低分
    height = probe.height or 0
    res_score = _clamp(height / 1080.0, 0.0, 1.5) / 1.5
    speed = probe.speed_mbps or 0.0
    speed_score = _clamp(speed / 5.0, 0.0, 1.5) / 1.5
    latency = probe.latency_ms if probe.latency_ms is not None else cfg.max_latency_ms
    latency_score = _clamp(1.0 - latency / cfg.max_latency_ms)
    br = probe.bitrate_kbps or 0.0
    br_score = _clamp(br / 4000.0, 0.0, 1.5) / 1.5

    total_w = cfg.w_online + cfg.w_resolution + cfg.w_speed + cfg.w_latency + cfg.w_bitrate
    score = (
        cfg.w_online * 1.0
        + cfg.w_resolution * res_score
        + cfg.w_speed * speed_score
        + cfg.w_latency * latency_score
        + cfg.w_bitrate * br_score
    )
    return round(score / total_w * 100.0, 2)


def quality_ok(probe: ProbeResult, cfg: RankConfig) -> bool:
    if not probe.online:
        return False
    if probe.height and probe.height < cfg.min_resolution_height:
        return False
    if probe.speed_mbps is not None and probe.speed_mbps < cfg.min_speed_mbps:
        return False
    if probe.latency_ms is not None and probe.latency_ms > cfg.max_latency_ms:
        return False
    return True


def sort_probes(probes: list[ProbeResult], cfg: RankConfig) -> list[ProbeResult]:
    for p in probes:
        p.score = score_probe(p, cfg)

    def key(p: ProbeResult):
        if not p.online:
            return (1, 0, 0, 0, 0, p.url)
        ok = 0 if quality_ok(p, cfg) else 1
        if cfg.sort_by == "resolution":
            return (ok, -(p.height or 0), -(p.speed_mbps or 0), p.latency_ms or 0, -p.score, p.url)
        if cfg.sort_by == "speed":
            return (ok, -(p.speed_mbps or 0), -(p.height or 0), p.latency_ms or 0, -p.score, p.url)
        if cfg.sort_by == "latency":
            return (ok, p.latency_ms or 0, -(p.height or 0), -(p.speed_mbps or 0), -p.score, p.url)
        # 默认 score
        return (ok, -p.score, -(p.height or 0), -(p.speed_mbps or 0), p.latency_ms or 0, p.url)

    return sorted(probes, key=key)


def rank_channel_streams(
    channel: Channel,
    probes: dict[str, ProbeResult],
    cfg: RankConfig,
) -> list[ProbeResult]:
    own = [probes.get(s.url) or ProbeResult(url=s.url) for s in channel.streams]
    return sort_probes(own, cfg)


def build_ranked_items(
    channels: list[Channel],
    probes: dict[str, ProbeResult],
    cfg: RankConfig,
) -> list[tuple[Channel, list[ProbeResult]]]:
    items: list[tuple[Channel, list[ProbeResult]]] = []
    for ch in channels:
        ranked = rank_channel_streams(ch, probes, cfg)
        # 频道级：有可用流优先；再比最高流得分
        best = next((p for p in ranked if p.online), None)
        best_score = best.score if best else -1.0
        items.append((ch, ranked))
    # 频道顺序：分组已在 normalize.sort_channels 处理，这里保持传入顺序
    _ = cfg
    return items


def flatten_ranked(
    items: list[tuple[Channel, list[ProbeResult]]],
) -> list[RankedStream]:
    out: list[RankedStream] = []
    for ch, ranked in items:
        for p in ranked:
            st = next((s for s in ch.streams if s.url == p.url), Stream(url=p.url, name=ch.name))
            out.append(
                RankedStream(
                    stream=st,
                    probe=p,
                    channel_name=ch.name,
                    channel_group=ch.group,
                )
            )
    return out
