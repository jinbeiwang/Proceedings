"""CDISC Interchange (Global) 演示归档 spider。

数据源: cdisc.org 官方 "Interchange Presentations" 索引页
  https://www.cdisc.org/events/interchange-presentations
该页列出 2023+ 各届 Interchange / CDISC Day 归档页,如:
  /events/interchange/2025-cdisc-tmf-us-interchange/archive
  /events/cdisc-day/2025-china-cdisc-day/archive

归档页为 Drupal 站点,结构规整:
  - div.paragraph--type--interchange-session > h3.card-title       -> session 名
      field--name-field-p-session-chair / -p-session-room          -> 主席/房间(跳过)
  - div.paragraph--type--session-presentation:
      field--name-field-p-presentation-title .field__item           -> 演示标题
      field--name-field-p-speaker .field__item                      -> 演讲者
      field--name-field-p-presentation-doc-public a[href]           -> 公开 PDF 直链
部分归档页 "not yet available"(0 个演示),自动跳过。
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from base import BaseSpider, log
from models import Paper

INDEX_URL = "https://www.cdisc.org/events/interchange-presentations"

# 归档链接文本 -> region
_REGION_HINTS = [
    ("us", "US"), ("europe", "EU"), ("japan", "JP"), ("china", "CN"),
    ("korea", "APAC"), ("india", "APAC"),
]


class CDISCInterchangeSpider(BaseSpider):
    conference = "cdisc-interchange"
    base_url = "https://www.cdisc.org"
    rate_limit = 1.0

    def collect(self) -> list[Paper]:
        archive_links = self._discover_archives()
        if not archive_links:
            log.warning("[cdisc-interchange] 索引页无归档链接")
            return []

        papers: list[Paper] = []
        for ev in archive_links:
            papers.extend(self._collect_event(ev))
        log.info("[cdisc-interchange] %d 届归档,共 %d 条演示",
                 len(archive_links), len(papers))
        return papers

    def _discover_archives(self) -> list[dict]:
        html = self.fetch_html(INDEX_URL)
        if not html:
            return []
        soup = self.soup(html)
        seen: set[str] = set()
        out: list[dict] = []
        for a in soup.find_all("a", href=re.compile(r"/archive", re.I)):
            href = a.get("href", "")
            url = self.absurl(href)
            if url in seen:
                continue
            # 仅事件归档页(过滤页内锚点/外链)
            if "/events/interchange/" not in href and "/events/cdisc-day/" not in href:
                continue
            seen.add(url)
            name = a.get_text(" ", strip=True)
            m = re.search(r"/(?:interchange|cdisc-day)/(\d{4})-", href)
            year = int(m.group(1)) if m else None
            if not year or not name:
                continue
            out.append({
                "name": name,
                "url": url,
                "year": year,
                "region": _region_of(href),
            })
        out.sort(key=lambda e: (e["year"], e["name"]))
        return out

    def _collect_event(self, ev: dict) -> list[Paper]:
        html = self.fetch_html(ev["url"])
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")

        papers: list[Paper] = []
        sessions = soup.find_all("div", class_=re.compile(r"paragraph--type--interchange-session"))
        if not sessions:
            log.info("[cdisc-interchange] %s 无 session(未发布),跳过", ev["name"])
            return []

        for sess in sessions:
            h3 = sess.find("h3", class_=re.compile(r"card-title"))
            session_name = h3.get_text(" ", strip=True) if h3 else ""
            # 去掉 "Session N: " / "Track X - " 前缀,留语义部分
            section_name = re.sub(r"^Session\s*\d+:\s*", "", session_name)
            for pres in sess.find_all(
                    "div", class_=re.compile(r"paragraph--type--session-presentation")):
                p = self._parse_presentation(pres, ev, section_name, len(papers) + 1)
                if p:
                    papers.append(p)
        log.info("[cdisc-interchange] %s: %d 条", ev["name"], len(papers))
        return papers

    def _parse_presentation(self, pres, ev: dict, section_name: str, seq: int):
        def field_text(cls: str) -> str:
            node = pres.find("div", class_=re.compile(cls))
            return node.get_text(" ", strip=True) if node else ""

        title = field_text(r"field--name-field-p-presentation-title")
        if not title or len(title) < 4:
            return None
        speaker = field_text(r"field--name-field-p-speaker")

        pdf_url = ""
        doc = pres.find("div", class_=re.compile(r"field--name-field-p-presentation-doc-public"))
        if doc:
            a = doc.find("a", href=re.compile(r"\.pdf", re.I))
            if a:
                pdf_url = self.absurl(a["href"])

        code = _paper_code(ev, section_name, seq, pdf_url)
        authors = _parse_speakers(speaker)
        return self.make_paper(
            title=title,
            authors=authors,
            year=ev["year"],
            section_code=_section_code(section_name),
            section_name=section_name or "General",
            paper_code=code,
            pdf_url=pdf_url,
            source_url=ev["url"],
            region=ev["region"],
        )


def _region_of(href: str) -> str:
    low = href.lower()
    for hint, region in _REGION_HINTS:
        if hint in low:
            return region
    return "Global"


def _parse_speakers(speaker: str) -> list[str]:
    """'Nancy Brucken, IQVIA; and Sandra Smith, Acme' -> ['Nancy Brucken (IQVIA)', ...]。"""
    if not speaker:
        return []
    raw = re.sub(r"\band\b", ";", speaker, flags=re.I)
    out = []
    for part in re.split(r"[;]", raw):
        part = re.sub(r"\s+", " ", part).strip(" ,")
        if not part:
            continue
        segs = [s.strip() for s in part.split(",")]
        if len(segs) >= 2:
            out.append(f"{segs[0]} ({', '.join(segs[1:])})")
        else:
            out.append(part)
    return out


def _section_code(section_name: str) -> str:
    m = re.search(r"Track\s+([A-Z])", section_name or "")
    if m:
        return m.group(1)
    if re.search(r"plenary|keynote", section_name or "", re.I):
        return "PL"
    return "GE"


def _paper_code(ev: dict, section_name: str, seq: int, pdf_url: str) -> str:
    slug = ev["url"].rsplit("/events/", 1)[-1].replace("/archive", "")
    stem = ""
    if pdf_url:
        stem = pdf_url.rsplit("/", 1)[-1].split(".pdf")[0]
        stem = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-")[:60]
    if stem:
        return f"CDISC-{slug}-{stem}"
    return f"CDISC-{slug}-{seq:03d}"
