from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from .config import CheckConfig
from .models import ProbeResult, Stream

log = logging.getLogger(__name__)

_RES_RE = re.compile(r"RESOLUTION=(\d+)x(\d+)", re.I)
_BANDWIDTH_RE = re.compile(r"BANDWIDTH=(\d+)", re.I)


def _detect_protocol(url: str) -> str:
    low = url.lower()
    if low.startswith("rtp://") or low.startswith("udp://") or low.startswith("rtp/"):
        return "multicast"
    if low.startswith("rtsp://"):
        return "rtsp"
    if low.startswith("rtmp://") or low.startswith("rtmps://"):
        return "rtmp"
    path = low.split("?", 1)[0]
    if path.endswith(".m3u8") or "m3u8" in path:
        return "hls"
    if path.endswith(".ts"):
        return "ts"
    if low.startswith("http://") or low.startswith("https://"):
        return "http"
    return "other"


def _http_open(url: str, cfg: CheckConfig, headers: dict[str, str] | None = None):
    h = {
        "User-Agent": cfg.user_agent,
        "Accept": "*/*",
        "Connection": "close",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h, method="GET")
    return urllib.request.urlopen(req, timeout=cfg.timeout_sec)


def _probe_hls_master(body: str, result: ProbeResult) -> None:
    """从 HLS master playlist 解析最高清晰度（无需 ffprobe）。"""
    best_w = best_h = 0
    best_br = 0
    for line in body.splitlines():
        if not line.startswith("#EXT"):
            continue
        rm = _RES_RE.search(line)
        bm = _BANDWIDTH_RE.search(line)
        if rm:
            w, h = int(rm.group(1)), int(rm.group(2))
            if w * h > best_w * best_h:
                best_w, best_h = w, h
        if bm:
            best_br = max(best_br, int(bm.group(1)))
    if best_h:
        result.width, result.height = best_w, best_h
    if best_br and not result.bitrate_kbps:
        result.bitrate_kbps = best_br / 1000.0


def _ffprobe(url: str, cfg: CheckConfig, headers: dict[str, str] | None, result: ProbeResult) -> None:
    if not cfg.enable_ffprobe or not shutil.which("ffprobe"):
        return
    cmd = [
        "ffprobe",
        "-v", "error",
        "-hide_banner",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name,bit_rate",
        "-of", "json",
        "-user_agent", cfg.user_agent,
    ]
    if headers:
        if "Referer" in headers:
            cmd += ["-referer", headers["Referer"]]
        for k, v in headers.items():
            if k.lower() == "user-agent":
                cmd += ["-user_agent", v]
    cmd += ["-i", url]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg.ffprobe_timeout_sec,
            check=False,
        )
        if proc.returncode != 0:
            return
        data = json.loads(proc.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            return
        v = streams[0]
        result.width = v.get("width") or result.width
        result.height = v.get("height") or result.height
        result.codec = v.get("codec_name") or result.codec
        br = v.get("bit_rate")
        if br:
            result.bitrate_kbps = float(br) / 1000.0
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError):
        return


def probe_stream(stream: Stream, cfg: CheckConfig) -> ProbeResult:
    """检测单条流：连通性、延迟、采样速率、清晰度。"""
    result = ProbeResult(url=stream.url, protocol=_detect_protocol(stream.url))
    headers = dict(stream.headers) if stream.headers else None

    if result.protocol in {"multicast", "rtmp", "rtsp"}:
        # 组播/专用协议：无法用 HTTP 探活；运营商内网可能可播
        result.online = False
        result.error = f"{result.protocol} 协议，需专用链路/播放器，跳过 HTTP 检测"
        return result

    start = time.perf_counter()
    try:
        with _http_open(stream.url, cfg, headers) as resp:
            result.http_status = getattr(resp, "status", None) or resp.getcode()
            result.latency_ms = (time.perf_counter() - start) * 1000.0
            # 采样读取，估算吞吐
            sample_start = time.perf_counter()
            data = resp.read(cfg.download_bytes)
            elapsed = max(time.perf_counter() - sample_start, 1e-3)
            result.speed_mbps = (len(data) * 8) / elapsed / 1_000_000.0

            # HLS 文本探测
            text_head = ""
            try:
                text_head = data[:8000].decode("utf-8", errors="replace")
            except Exception:
                text_head = ""
            if text_head.lstrip().startswith("#EXTM3U"):
                _probe_hls_master(text_head, result)

            result.online = result.http_status is not None and 200 <= result.http_status < 400 and len(data) > 0
    except urllib.error.HTTPError as e:
        result.http_status = e.code
        result.error = f"HTTP {e.code}"
        result.online = False
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        result.error = str(e)
        result.online = False
    except Exception as e:  # noqa: BLE001 — 检测器不因单点异常中断
        result.error = f"{type(e).__name__}: {e}"
        result.online = False

    if result.online:
        _ffprobe(stream.url, cfg, headers, result)

    return result


def probe_many(
    streams: Iterable[Stream], cfg: CheckConfig
) -> dict[str, ProbeResult]:
    items = list(streams)
    log.info("开始检测 %d 条流，并发 %d …", len(items), cfg.concurrency)
    results: dict[str, ProbeResult] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, cfg.concurrency)) as pool:
        futs = {pool.submit(probe_stream, s, cfg): s for s in items}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                pr = fut.result()
            except Exception as e:  # noqa: BLE001
                pr = ProbeResult(url=s.url, error=str(e), online=False)
            results[s.url] = pr
            done += 1
            if done % 50 == 0 or done == len(items):
                online = sum(1 for r in results.values() if r.online)
                log.info("进度 %d/%d，当前可用 %d", done, len(items), online)
    online = sum(1 for r in results.values() if r.online)
    log.info("检测完成：可用 %d / %d", online, len(results))
    return results
