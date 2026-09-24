from __future__ import annotations

import logging
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .config import AppConfig
from .m3u import parse_m3u_file, parse_m3u_text
from .models import Stream

log = logging.getLogger(__name__)


def load_remote_urls(cfg: AppConfig) -> list[str]:
    path = cfg.remote_sources_file
    if not path.exists():
        log.warning("远程源列表不存在: %s", path)
        return []
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def load_local_streams(cfg: AppConfig) -> list[Stream]:
    streams: list[Stream] = []
    d = cfg.local_sources_dir
    if not d.exists():
        return streams
    for p in sorted(d.rglob("*")):
        if p.suffix.lower() not in {".m3u", ".m3u8", ".txt"}:
            continue
        try:
            found = parse_m3u_file(str(p))
            log.info("本地源 %s → %d 条", p.name, len(found))
            streams.extend(found)
        except OSError as e:
            log.warning("读取本地源失败 %s: %s", p, e)
    return streams


def fetch_url_text(url: str, timeout: float, user_agent: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "*/*",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def collect(cfg: AppConfig) -> list[Stream]:
    """采集远程订阅 + 本地文件中的全部频道流。"""
    streams: list[Stream] = []
    remote_urls = load_remote_urls(cfg)
    log.info("远程订阅 %d 个，开始拉取…", len(remote_urls))

    def _one(url: str) -> list[Stream]:
        try:
            text = fetch_url_text(url, cfg.fetch_timeout_sec, cfg.check.user_agent)
            items = parse_m3u_text(text, source=url)
            log.info("远程 %s → %d 条", url, len(items))
            return items
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            log.warning("远程源失败 %s: %s", url, e)
            return []

    if remote_urls:
        with ThreadPoolExecutor(max_workers=min(8, len(remote_urls))) as pool:
            futs = [pool.submit(_one, u) for u in remote_urls]
            for f in as_completed(futs):
                streams.extend(f.result())

    streams.extend(load_local_streams(cfg))
    # 去重 URL，保持首次出现的元数据
    seen: set[str] = set()
    unique: list[Stream] = []
    for s in streams:
        k = s.url.strip()
        if not k or k in seen:
            continue
        seen.add(k)
        unique.append(s)
    http_n = sum(1 for s in unique if s.url.lower().startswith(("http://", "https://")))
    log.info("合计采集 %d 条流（HTTP(S) %d，其它协议 %d）", len(unique), http_n, len(unique) - http_n)
    return unique
