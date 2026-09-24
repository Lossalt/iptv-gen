from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from iptv_gen.m3u import generate_m3u, generate_txt, parse_m3u_text
from iptv_gen.models import Channel, ProbeResult, Stream
from iptv_gen.normalize import group_channels, normalize_name, sort_channels
from iptv_gen.rank import score_probe, sort_probes
from iptv_gen.config import RankConfig


def test_parse_extinf_and_group():
    text = """#EXTM3U
#EXTINF:-1 tvg-id="cctv1" tvg-logo="http://x/1.png" group-title="央视",CCTV-1 综合
http://a/1.m3u8
#EXTINF:-1 group-title="卫视",湖南卫视
http://a/2.m3u8
湖南卫视,http://a/3.m3u8
"""
    streams = parse_m3u_text(text, source="t")
    assert len(streams) == 3
    assert streams[0].name == "CCTV-1 综合"
    assert streams[0].group == "央视"
    assert streams[0].logo == "http://x/1.png"
    assert streams[2].url == "http://a/3.m3u8"


def test_normalize_merges_quality_suffix():
    assert normalize_name("CCTV-1 综合") == "CCTV1-综合" or "CCTV1" in normalize_name("CCTV-1 综合")
    assert normalize_name("湖南卫视HD") == normalize_name("湖南卫视")
    assert normalize_name("CCTV1高清") == normalize_name("CCTV1")


def test_group_and_sort():
    streams = parse_m3u_text(
        """#EXTM3U
#EXTINF:-1 group-title="卫视",湖南卫视
http://a/1
#EXTINF:-1 group-title="央视",CCTV1
http://a/2
#EXTINF:-1 group-title="卫视",湖南卫视HD
http://a/3
"""
    )
    channels = group_channels(streams)
    assert len(channels) == 2
    ordered = sort_channels(channels)
    assert ordered[0].name.upper().startswith("CCTV")
    hunan = next(c for c in ordered if "湖南" in c.name)
    assert len(hunan.streams) == 2


def test_score_and_sort_prefers_resolution():
    cfg = RankConfig()
    low = ProbeResult(url="l", online=True, height=720, speed_mbps=2, latency_ms=100)
    high = ProbeResult(url="h", online=True, height=1080, speed_mbps=2, latency_ms=100)
    dead = ProbeResult(url="d", online=False)
    assert score_probe(high, cfg) > score_probe(low, cfg) > score_probe(dead, cfg)
    ranked = sort_probes([dead, low, high], cfg)
    assert ranked[0].url == "h"
    assert ranked[-1].url == "d"


def test_generate_m3u_contains_live_only():
    ch = Channel(name="CCTV1", group="央视", tvg_id="CCTV1")
    ch.add_stream(Stream(url="http://ok", name="CCTV1"))
    ch.add_stream(Stream(url="http://bad", name="CCTV1"))
    ranked = [
        ProbeResult(url="http://ok", online=True, height=1080, score=80),
        ProbeResult(url="http://bad", online=False, score=-1),
    ]
    text = generate_m3u([(ch, ranked)], epg_url="https://epg.x/e.xml", include_dead=False)
    assert "http://ok" in text
    assert "http://bad" not in text
    assert "CCTV1" in text
    txt = generate_txt([(ch, ranked)])
    assert "CCTV1,http://ok" in txt
