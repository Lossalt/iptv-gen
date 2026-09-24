# iptv-gen

国内 IPTV **M3U 生成器** 雏形：多源采集 → 按本机网络检测连通性/清晰度/速率 → 自动排序 → 输出可用播放列表。

> 工具本身不提供、不托管任何直播源内容。请只使用你有权使用的源，并遵守当地法规。

## 功能

| 模块 | 能力 |
|------|------|
| 采集 `collect` | 拉取 `sources/remote.txt` 订阅 + 读取 `sources/local/*.m3u\|txt` |
| 别名 `alias` | `config/alias.txt` 把 CCTV1 / CCTV-1 / 中央一台 等收成一台 |
| 模板 `template` | `config/template.txt` 只导出关心的频道，并按模板顺序排列 |
| 归一化 `normalize` | 频道名去清晰度后缀、CCTV 编号统一、按 `group-title` 分组 |
| 检测 `check` | HTTP 连通、延迟、采样下载速率；HLS master 解析分辨率；可选 `ffprobe` 精测 |
| 排序 `rank` | 综合得分：连通 > 分辨率 > 速率 > 延迟 > 码率（权重可配） |
| 生成 `generate` | `output/iptv-ranked.m3u` / `iptv-ranked.txt` / `check-report.json` |

## 快速开始

```powershell
# 1) 进入项目
cd iptv-gen

# 2) 仅用本地示例试跑（不拉远程）
$env:PYTHONPATH = "src"
python -m iptv_gen --local-only -c config/config.json run
# 本地源放到 sources/local/ ，可先复制示例：
Copy-Item examples\demo.m3u sources\local\

# 3) 完整流程（远程订阅 + 本地）
python -m iptv_gen -c config/config.json run

# 只采集 / 只检测；抽样前 50 条（优先 http/https，避开 rtp 组播）
python -m iptv_gen -c config/config.json collect
python -m iptv_gen -c config/config.json --limit 50 check
python -m iptv_gen -c config/config.json --limit 50 run
```

若安装了 [ffmpeg](https://ffmpeg.org/)（`ffprobe` 在 PATH 中），清晰度识别会更准；没有也能跑，会尽量从 HLS `#EXT-X-STREAM-INF RESOLUTION=` 推断。

## 目录

```
iptv-gen/
├── config/config.json      # 超时、并发、排序权重、阈值
├── config/alias.txt        # 频道别名（同台多写法合并）
├── config/template.txt     # 导出模板（频道清单 + 顺序 + 分组）
├── sources/remote.txt      # 远程 M3U 订阅（一行一个）
├── sources/local/          # 自编 / 本地 M3U、天马 txt
├── examples/               # 示例播放列表
├── src/iptv_gen/           # 核心代码
├── output/                 # 生成结果与检测报告
└── tests/                  # 单元测试
```

## 配置要点（`config/config.json`）

- `check.timeout_sec` / `concurrency`：本机网络检测的超时与并发
- `check.enable_ffprobe`：是否用 ffprobe 测分辨率/码率
- `rank.sort_by`：`score` | `resolution` | `speed` | `latency`
- `rank.max_per_channel`：每频道导出几条最优源
- `rank.min_resolution_height` / `min_speed_mbps` / `max_latency_ms`：质量门槛
- `open_alias` / `open_template`：是否启用别名表 / 导出模板

### 别名表 `config/alias.txt`

一行一个标准频道，逗号（或 `|`）分隔别名；第一个名字是导出显示名：

```
CCTV1,CCTV-1,CCTV1综合,中央一台
湖南卫视|湖南卫视HD|湖南台
```

匹配前会做归一化（去 HD/高清、CCTV-1→CCTV1 等），因此别名可写得简短。

### 导出模板 `config/template.txt`

只导出列表中的频道，并按文件顺序排序（天马 `#genre#` 分组）：

```
央视,#genre#
CCTV1
CCTV2
卫视,#genre#
湖南卫视
```

文件为空或不存在、或 `open_template=false` 时导出全部频道。

## 检测与排序逻辑（雏形）

```
得分 = 40×连通 + 25×清晰度 + 20×速率 + 10×延迟 + 5×码率   （归一化到 0~100）
```

同一频道多条流按得分降序写入 M3U；不可用流默认不写入（`include_dead: true` 可保留）。

### 协议说明

- `http(s)://`、HLS `m3u8`：支持连通 / 延迟 / 采样速率 / 分辨率检测
- `rtp://` `udp://` 等运营商组播、`rtmp` `rtsp`：无法 HTTP 探活，会标记为跳过（内网组播需专用链路，可自行扩展 IGMP/UDP 探测）
- 抽样 `--limit` 会优先检测 HTTP(S) 流

### 本机试跑摘要（示例）

```
采集约 2500–4200 条流 → 归一化后约 1500 个频道
抽样 50 条 HTTP 流：可用 41 / 50
CCTV1 多源合并后约 20+ 条候选，按得分写入前 5 条
```

## 参考项目（思路 / 数据源）

| 项目 | 借鉴点 |
|------|--------|
| [joevess/IPTV](https://github.com/joevess/IPTV) | 多源整合，按分辨率/速度择优 |
| [Guovin/iptv-api](https://github.com/Guovin/iptv-api) | 采集 + 可用性校验 + 测速筛选 + `sort_by=resolution,speed` |
| [ngo5/IPTV](https://github.com/ngo5/IPTV) | 社区源清单、EPG/检测工具索引 |
| [dongyubin/IPTV](https://github.com/dongyubin/IPTV) | 人工策展目录、IPv4/IPv6 分类 |
| [zhimin-dev/iptv-checker](https://github.com/zhimin-dev/iptv-checker) | 直播源有效性检测产品形态参考 |

`sources/remote.txt` 中预置了若干公开订阅地址，**请自行筛选并确认可用/合规**；失效或不想用的行用 `#` 注释掉即可。

## 测试

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests -q
```

## 路线图（下一步）

- [ ] 频道别名库（类似 Guovin `alias.txt`）与模板 `template.txt`（只导出你关心的台）
- [ ] 广告/循环占位源过滤
- [ ] 归属地 / 运营商偏好（移动/联通/电信）
- [ ] IPv4/IPv6 分流输出
- [ ] 历史结果缓存、定时任务
- [ ] 简易 Web 报告（检测进度、Top 流对比）
