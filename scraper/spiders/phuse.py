"""PHUSE spider — 通过 Strapi CMS API 抓取 PHUSE 会议论文。

数据源(2026-08 实地核实):
  Strapi API: https://cms.phuse.global/api/archives
  - 公开无需认证,支持分页(pageSize 上限 100)
  - 总计 ~8100+ 篇论文,覆盖历年 PHUSE Connect / CSS / Working Group Events
  - 字段: event, year, city, region, title, author, company, co_author,
          educational_category, keywords, filename
  - PDF 托管在 S3: https://phuse.s3.eu-central-1.amazonaws.com/Archive/{year}/{event}/{region}/{city}/{filename}
  - filename 可能含多个文件(换行分隔): "PRE_AD06.pdf\nPAP_AD06.pdf"
  - 优先取 PAP_(论文),其次 PRE_(演示)

会议代码 -> 过滤条件:
  phuse-eu   -> region=EU
  phuse-us   -> region=US
  phuse-apac -> region=APAC
  phuse-css  -> event=CSS
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

from base import BaseSpider, log
from models import Paper

# PHUSE stream 代码 -> 名称映射(从 Keywords 列提取)
STREAM_MAP = {
    "AD": "Application Development & Software Demonstrations",
    "ML": "Artificial Intelligence, Machine Learning and Large Language Models",
    "AS": "Analytics & Statistics & Analytical Risk-Based Monitoring",
    "OS": "Open Source Technologies",
    "DS": "Data Science",
    "RC": "Regulatory Compliance & Submission",
    "DM": "Data Management",
    "PV": "Pharmacovigilance",
    "ST": "Statistics",
    "TT": "Technology & Tools",
    "SD": "Software Development",
    "WK": "Workshop",
    "KN": "Keynote",
    "LN": "Late News",
    "RG": "Regulatory",
    "QT": "Quantitative Pharmacology",
    "EX": "Excellence",
    "IN": "Innovation",
    "LF": "Leadership & Future",
    "CM": "Communications",
    "ED": "Education",
    "DT": "Data Transparency",
    "AR": "Analytics and Risk Based Monitoring",
}

# 会议代码 -> 过滤条件
CONF_FILTERS = {
    "phuse-eu":   {"field": "region", "value": "EU"},
    "phuse-us":   {"field": "region", "value": "US"},
    "phuse-apac": {"field": "region", "value": "APAC"},
    "phuse-css":  {"field": "event",  "value": "CSS"},
}

S3_BASE = "https://phuse.s3.eu-central-1.amazonaws.com"
API_BASE = "https://cms.phuse.global/api/archives"
PAGE_SIZE = 100  # Strapi API 上限


class PHUSESpider(BaseSpider):
    conference = "phuse-eu"
    base_url = "https://phuse.global"
    rate_limit = 0.5  # API 很快,不需要太长间隔

    def collect(self) -> list[Paper]:
        # 获取全量数据(带共享缓存)
        all_items = self._fetch_all_archives()

        # 按会议代码过滤
        flt = CONF_FILTERS.get(self.conference)
        if not flt:
            log.warning("[%s] 未知 PHUSE 会议代码,返回全部数据", self.conference)
            filtered = all_items
        else:
            field, value = flt["field"], flt["value"]
            filtered = [
                item for item in all_items
                if (item.get("attributes", {}).get(field, "") or "").upper() == value.upper()
            ]

        log.info("[%s] 过滤后 %d / %d 篇", self.conference, len(filtered), len(all_items))

        # 转换为 Paper 对象
        papers: list[Paper] = []
        seen_ids: set[str] = set()

        for item in filtered:
            paper = self._make_paper_from_item(item)
            if paper and paper.id not in seen_ids:
                seen_ids.add(paper.id)
                papers.append(paper)

        log.info("[%s] 共 %d 篇", self.conference, len(papers))
        return papers

    # ---- Strapi API 调用 ----
    def _fetch_all_archives(self) -> list[dict]:
        """获取全量 PHUSE Archive 数据(所有地区/事件)。
        使用共享缓存文件,避免多个 PHUSE 会议代码重复请求。
        """
        cache_file = self._shared_cache_path()
        if cache_file and cache_file.exists():
            log.info("[%s] 使用共享缓存: %s", self.conference, cache_file)
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        all_items: list[dict] = []
        page = 1
        total_pages = 1

        while page <= total_pages:
            url = f"{API_BASE}?pagination[page]={page}&pagination[pageSize]={PAGE_SIZE}&sort=year:desc"
            self._throttle()
            try:
                resp = self._client.get(url, timeout=30.0)
                if resp.status_code != 200:
                    log.warning("[%s] API 第 %d 页 HTTP %s", self.conference, page, resp.status_code)
                    break
                data = resp.json()
                items = data.get("data", [])
                all_items.extend(items)
                pagination = data.get("meta", {}).get("pagination", {})
                total_pages = pagination.get("pageCount", 1)
                total = pagination.get("total", 0)
                log.info("[%s] API 第 %d/%d 页, 获取 %d 条 (累计 %d/%d)",
                         self.conference, page, total_pages, len(items), len(all_items), total)
                page += 1
            except Exception as exc:
                log.warning("[%s] API 第 %d 页异常: %s", self.conference, page, exc)
                break

        # 保存共享缓存
        if cache_file and all_items:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(all_items, ensure_ascii=False), encoding="utf-8")
            log.info("[%s] 共享缓存已保存: %d 条 -> %s",
                     self.conference, len(all_items), cache_file)

        return all_items

    def _shared_cache_path(self) -> Path | None:
        """共享缓存路径(所有 PHUSE 会议代码共用)。"""
        if not self.cache_dir:
            return None
        return self.cache_dir / "phuse_shared_api.json"

    # ---- 数据转换 ----
    def _make_paper_from_item(self, item: dict) -> Paper | None:
        """将 Strapi API 条目转换为 Paper 对象。"""
        attrs = item.get("attributes", {})
        if not attrs:
            return None

        title = (attrs.get("title") or "").strip()
        if not title:
            return None

        year_str = str(attrs.get("year") or "").strip()
        try:
            year = int(year_str)
        except ValueError:
            return None

        # 解析 keywords: "AD06; Application Development & Software Demonstrations; Best in Stream"
        keywords_raw = (attrs.get("keywords") or "").strip()
        section_code, section_name = _parse_keywords(keywords_raw)

        # 从标题提取论文编号: "AD06: Harnessing..." -> AD06
        paper_code = _extract_paper_code(title, keywords_raw)

        # 构造 PDF URL
        filename_raw = (attrs.get("filename") or "").strip()
        pdf_url = self._construct_pdf_url(filename_raw, attrs)
        if not pdf_url:
            return None

        # 作者
        author = (attrs.get("author") or "").strip()
        co_author = (attrs.get("co_author") or "").strip()
        authors = [a for a in [author, co_author] if a]

        # 论文编号兜底
        if not paper_code:
            paper_code = f"PHUSE-{year}-{section_code or 'XX'}-{item.get('id', '???')}"

        return self.make_paper(
            title=title,
            authors=authors,
            year=year,
            section_code=section_code,
            section_name=section_name,
            paper_code=paper_code,
            pdf_url=pdf_url,
            source_url=f"https://phuse.global/Communications/PHUSE_Archive",
            keywords=[k.strip() for k in keywords_raw.split(";") if k.strip()],
        )

    def _construct_pdf_url(self, filename_raw: str, attrs: dict) -> str:
        """从 filename 字段和元数据构造 PDF URL。
        filename 格式: "PRE_AD06.pdf\nPAP_AD06.pdf" (可能多行)
        S3 路径: Archive/{year}/{event}/{region}/{city}/{filename}
        """
        if not filename_raw:
            return ""

        # 解析文件名列表,优先 PAP_ (论文) 其次 PRE_ (演示)
        files = [f.strip() for f in filename_raw.split("\n") if f.strip()]
        if not files:
            return ""

        chosen = ""
        for f in files:
            if f.upper().startswith("PAP_") and f.lower().endswith(".pdf"):
                chosen = f
                break
        if not chosen:
            for f in files:
                if f.lower().endswith(".pdf"):
                    chosen = f
                    break
        if not chosen:
            return ""

        year = attrs.get("year", "")
        event = attrs.get("event", "Connect")
        region = attrs.get("region", "")
        city = attrs.get("city", "")

        # 构造 S3 URL
        # Connect 事件: Archive/{year}/Connect/{region}/{city}/{filename}
        # CSS 事件: Archive/{year}/CSS/{filename} (可能无 region/city)
        if event.upper() == "CSS":
            path = f"Archive/{year}/CSS/{chosen}"
        else:
            path = f"Archive/{year}/{event}/{region}/{city}/{chosen}"

        return f"{S3_BASE}/{quote(path)}"


def _parse_keywords(keywords: str) -> tuple[str, str]:
    """从 Keywords 字段解析 stream 代码和名称。
    格式: "AD06; Application Development & Software Demonstrations; Best in Stream"
    """
    if not keywords:
        return "", ""
    parts = [p.strip() for p in keywords.split(";") if p.strip()]
    if not parts:
        return "", ""

    # 第一部分通常是论文编号(含 stream 代码): AD06
    code_part = parts[0]
    code_match = re.match(r"^([A-Z]+)(\d+)", code_part)
    stream_code = code_match.group(1) if code_match else ""

    # 第二部分(如果存在)是 stream 全名
    stream_name = ""
    if len(parts) > 1:
        stream_name = parts[1]
    elif stream_code:
        stream_name = STREAM_MAP.get(stream_code, stream_code)

    return stream_code, stream_name


def _extract_paper_code(title: str, keywords: str) -> str:
    """从标题或关键词中提取论文编号。"""
    # 从标题前缀提取: "AD06: Harnessing..." -> AD06
    m = re.match(r"^([A-Z]+\d+)\s*[:：]?\s*", title)
    if m:
        return m.group(1)
    # 从 keywords 提取
    if keywords:
        m = re.match(r"^([A-Z]+\d+)", keywords.strip())
        if m:
            return m.group(1)
    return ""
