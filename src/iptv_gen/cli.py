from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .alias import load_alias_map
from .check import probe_many
from .collect import collect
from .config import AppConfig
from .generate import write_outputs
from .normalize import group_channels, sort_channels
from .rank import build_ranked_items
from .template import apply_template, load_template


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _load_catalog(cfg: AppConfig) -> tuple[dict[str, str], list]:
    alias_map = load_alias_map(cfg.alias_file if cfg.open_alias else None)
    template = load_template(cfg.template_file if cfg.open_template else None)
    if alias_map:
        logging.info("别名表：%d 条映射", len(alias_map))
    if template:
        logging.info("模板：%d 个频道（仅导出模板内频道）", len(template))
    else:
        logging.info("模板：未启用或为空，导出全部频道")
    return alias_map, template


def _apply_limit(streams: list, limit: int) -> list:
    if limit and limit > 0:
        # 抽样优先 HTTP(S)/HLS，避免被 rtp:// 组播占满
        httpish = [s for s in streams if s.url.lower().startswith(("http://", "https://"))]
        others = [s for s in streams if not s.url.lower().startswith(("http://", "https://"))]
        picked = (httpish + others)[:limit]
        logging.info(
            "抽样模式：仅检测 %d 条流（http %d / 其它 %d，共 %d）",
            limit,
            len(httpish),
            len(others),
            len(streams),
        )
        return picked
    return streams


def cmd_run(cfg: AppConfig, limit: int = 0) -> int:
    streams = collect(cfg)
    if not streams:
        logging.error("未采集到任何频道流。请在 sources/remote.txt 或 sources/local/ 放入 M3U。")
        return 1
    streams = _apply_limit(streams, limit)
    alias_map, template = _load_catalog(cfg)
    channels = sort_channels(group_channels(streams, alias_map=alias_map))
    logging.info("归一化后频道数：%d", len(channels))
    channels = apply_template(channels, template, alias_map)
    logging.info("模板筛选后频道数：%d", len(channels))
    if not channels:
        logging.error("模板筛选后为空。检查 config/template.txt 或关闭 open_template。")
        return 1
    probes = probe_many(streams, cfg.check)
    items = build_ranked_items(channels, probes, cfg.rank)
    paths = write_outputs(cfg, items, probes)
    print()
    print("完成。输出文件：")
    for k, p in paths.items():
        print(f"  [{k}] {p}")
    return 0


def cmd_collect(cfg: AppConfig) -> int:
    streams = collect(cfg)
    alias_map, template = _load_catalog(cfg)
    channels = sort_channels(group_channels(streams, alias_map=alias_map))
    channels = apply_template(channels, template, alias_map)
    print(f"采集流 {len(streams)} 条 → 频道 {len(channels)} 个（含别名/模板）")
    for ch in channels[:30]:
        print(f"  [{ch.group}] {ch.name} ({len(ch.streams)} 源)")
    if len(channels) > 30:
        print(f"  … 其余 {len(channels) - 30} 个省略")
    return 0


def cmd_check_only(cfg: AppConfig, limit: int = 0) -> int:
    streams = collect(cfg)
    streams = _apply_limit(streams, limit)
    probes = probe_many(streams, cfg.check)
    online = sum(1 for p in probes.values() if p.online)
    print(f"检测完成：可用 {online} / {len(probes)}")
    # 打印 Top 20
    ranked = sorted(
        probes.values(),
        key=lambda p: (-(1 if p.online else 0), -(p.height or 0), p.latency_ms or 9999),
    )
    for p in ranked[:20]:
        flag = "✓" if p.online else "✗"
        print(
            f"  {flag} {p.resolution_label or p.resolution or '-':8} "
            f"{(p.speed_mbps or 0):5.2f}Mbps "
            f"{(p.latency_ms or 0):6.0f}ms  {p.url[:80]}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="iptv-gen",
        description="国内 IPTV M3U 生成器：多源采集 + 本地网络检测 + 清晰度/连通性排序",
    )
    p.add_argument(
        "-c",
        "--config",
        default=None,
        help="config/config.json 路径（默认：工作目录下 config/config.json）",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="调试日志")
    p.add_argument(
        "--local-only",
        action="store_true",
        help="只使用 sources/local/，不拉取远程订阅",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="只检测前 N 条流（0=全部），便于抽样试跑",
    )
    sub = p.add_subparsers(dest="command")
    sub.add_parser("run", help="采集 → 检测 → 排序 → 生成（默认）")
    sub.add_parser("collect", help="仅采集并汇总频道")
    sub.add_parser("check", help="仅检测连通性/清晰度")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    cfg_path = Path(args.config) if args.config else None
    if cfg_path is None:
        # 优先 cwd，其次包相对上级（项目根）
        cand = Path.cwd() / "config" / "config.json"
        cfg_path = cand if cand.exists() else Path(__file__).resolve().parents[2] / "config" / "config.json"
    cfg = AppConfig.load(cfg_path if cfg_path.exists() else None)
    if args.local_only:
        cfg.remote_sources_file = cfg.project_root / "sources" / "remote.txt.disabled"

    cmd = args.command or "run"
    limit = int(args.limit or 0)
    if cmd == "collect":
        return cmd_collect(cfg)
    if cmd == "check":
        return cmd_check_only(cfg, limit=limit)
    return cmd_run(cfg, limit=limit)


if __name__ == "__main__":
    sys.exit(main())
