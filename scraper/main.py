"""抓取主入口:调度各会议 spider,汇总去重,输出静态站点所需的 JSON 数据。

用法:
  python main.py                          # 抓取所有已实现 spider
  python main.py -c pharmasug-us          # 只抓 PharmaSUG US
  python main.py -c pharmasug-us --years 2024,2025
  python main.py --out ../site/data       # 指定输出目录

增量策略: 读取已有 papers.json,按 id 合并(新论文追加,已有论文保留更早 added_at)。
输出:
  {out}/papers.json       全量论文记录
  {out}/conferences.json  各会议元数据 + 统计(篇数/年份范围/section 列表)
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

import httpx

# 允许 scraper/ 目录直接运行,把自身加入 sys.path
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from base import HEADERS  # noqa: E402
from models import CONFERENCES  # noqa: E402
from spiders import SPIDERS  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


def load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {p["id"]: p for p in data}
    except (json.JSONDecodeError, KeyError):
        return {}


def merge(old: dict[str, dict], new_papers: list) -> list[dict]:
    """合并: 新论文加入;已有论文保留旧 added_at,其余字段以新抓取为准。

    降级保护: 新记录是占位标题(仅编号,无真实标题)而旧记录有真实标题时,
    保留旧记录——避免 Wayback 不可达时重跑把已有富数据冲成占位符。
    """
    merged: dict[str, dict] = dict(old)
    for p in new_papers:
        d = p.to_dict() if hasattr(p, "to_dict") else dict(p)
        pid = d["id"]
        if pid in merged:
            old_rec = merged[pid]
            if _is_placeholder_title(d.get("title", "")) and not _is_placeholder_title(old_rec.get("title", "")):
                continue
            d["added_at"] = old_rec.get("added_at", d["added_at"])
        merged[pid] = d
    return list(merged.values())


def _is_placeholder_title(title: str) -> bool:
    """判断标题是否为 CDX 兜底生成的占位符(如 'Paper 123-2010' / 'SUGI 1998 Paper 45')。"""
    return bool(re.match(r"^(Paper\s+\d|SUGI\s+\d{4}\s+Paper\s)", title or ""))


def build_conferences_meta(papers: list[dict]) -> list[dict]:
    """按会议聚合统计。"""
    by_conf: dict[str, list[dict]] = defaultdict(list)
    for p in papers:
        by_conf[p.get("conference", "")].append(p)

    out = []
    for code, meta in CONFERENCES.items():
        items = by_conf.get(code, [])
        years = [p["year"] for p in items if p.get("year")]
        sections = sorted({p.get("section_name") for p in items if p.get("section_name")})
        out.append({
            "code": code,
            "name": meta["name"],
            "region": meta["region"],
            "lang": meta["lang"],
            "count": len(items),
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
            "sections": sections,
            "implemented": code in SPIDERS,
        })
    # 按篇数降序
    out.sort(key=lambda c: c["count"], reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser(description="会议论文抓取器")
    ap.add_argument("-c", "--conferences", default="",
                    help="逗号分隔的会议代码,默认全部已实现 spider")
    ap.add_argument("--out", default=str(HERE.parent / "site" / "data"),
                    help="JSON 输出目录")
    ap.add_argument("--cache", default=str(HERE / ".cache"),
                    help="HTML 缓存目录(加速重跑)")
    ap.add_argument("--years", default="",
                    help="限定年份,逗号分隔(仅对支持的 spider 生效)")
    args = ap.parse_args()

    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    papers_path = out_dir / "papers.json"
    conf_path = out_dir / "conferences.json"

    # 选择要运行的 spider
    if args.conferences:
        codes = [c.strip() for c in args.conferences.split(",") if c.strip()]
    else:
        codes = list(SPIDERS.keys())

    years_filter = {int(y) for y in args.years.split(",") if y.strip()} or None

    all_new = []
    client = httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True)
    try:
        for code in codes:
            cls = SPIDERS.get(code)
            if not cls:
                log.warning("未知会议代码: %s,跳过", code)
                continue
            spider = cls(cache_dir=cache_dir, client=client)
            # 同一 spider 类可能注册多个会议代码(如 SASGlobalForumSpider -> sgf/sugi)
            if code != spider.conference:
                spider.conference = code
                spider.meta = CONFERENCES.get(code, {})
            if years_filter and hasattr(spider, "set_years"):
                spider.set_years(years_filter)
            try:
                papers = spider.collect()
                all_new.extend(papers)
                log.info("[%s] 抓取完成: %d 篇", code, len(papers))
            except Exception:
                log.exception("[%s] 抓取失败", code)
    finally:
        client.close()

    # 增量合并
    old = load_existing(papers_path)
    merged = merge(old, all_new)
    merged.sort(key=lambda p: (p.get("conference", ""), p.get("year", 0),
                               p.get("paper_code", "")))

    # 紧凑格式(无缩进): 显著减小文件体积,加快浏览器下载与解析
    papers_path.write_text(
        json.dumps(merged, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    conf_path.write_text(
        json.dumps(build_conferences_meta(merged), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    log.info("=" * 50)
    log.info("总计 %d 篇 -> %s", len(merged), papers_path)
    log.info("会议统计 -> %s", conf_path)
    by_conf = defaultdict(int)
    for p in merged:
        by_conf[p.get("conference", "")] += 1
    for c, n in sorted(by_conf.items(), key=lambda x: -x[1]):
        log.info("  %-16s %d 篇", c, n)


if __name__ == "__main__":
    main()
