from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig
from .m3u import generate_m3u, generate_txt
from .models import Channel, ProbeResult

log = logging.getLogger(__name__)


def write_outputs(
    cfg: AppConfig,
    items: list[tuple[Channel, list[ProbeResult]]],
    probes: dict[str, ProbeResult],
) -> dict[str, Path]:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    m3u_path = cfg.output_dir / cfg.output_m3u
    txt_path = cfg.output_dir / cfg.output_txt
    report_path = cfg.output_dir / cfg.output_report

    m3u_text = generate_m3u(
        items,
        epg_url=cfg.epg_url,
        include_dead=cfg.rank.include_dead,
        max_per_channel=cfg.rank.max_per_channel,
    )
    txt_text = generate_txt(items, max_per_channel=cfg.rank.max_per_channel)
    m3u_path.write_text(m3u_text, encoding="utf-8")
    txt_path.write_text(txt_text, encoding="utf-8")

    online = sum(1 for p in probes.values() if p.online)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stream_total": len(probes),
        "stream_online": online,
        "channel_total": len(items),
        "channels_with_live": sum(
            1 for _, ranked in items if any(p.online for p in ranked)
        ),
        "check": {
            "timeout_sec": cfg.check.timeout_sec,
            "concurrency": cfg.check.concurrency,
            "ffprobe": cfg.check.enable_ffprobe,
        },
        "rank": {
            "sort_by": cfg.rank.sort_by,
            "max_per_channel": cfg.rank.max_per_channel,
        },
        "streams": [p.to_dict() for p in probes.values()],
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("已写出 %s / %s / %s", m3u_path.name, txt_path.name, report_path.name)
    return {"m3u": m3u_path, "txt": txt_path, "report": report_path}
