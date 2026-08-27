"""PharmaRUG China(中国制药行业 R 用户组年会)spider。

数据源: PharmaRUG 官方 GitHub Pages 站点
  https://pharmarug.github.io/
首页 Events 表列出历年年会站点 /pharmarug-{year}/,日程页为
  https://pharmarug.github.io/pharmarug-{year}/program.html
表格四列: Time | Topic | Presenter | Location
  - Topic 单元格含演示标题 + slides 链接(pptx)+ video 链接
  - Presenter 形如 "Name, Org" 或 "Name, Org, Name, Org"
clinyun.com 等第三方索引也源自此官方站;本 spider 直接抓官方源。
"""
from __future__ import annotations

import re

from base import BaseSpider, log
from models import Paper

ROOT_URL = "https://pharmarug.github.io/"
# 无效行(非演示)
_SKIP_TITLE = re.compile(
    r"^(registration|break|lunch|welcome|closing|photo|q\s*&\s*a)\b", re.I)


class PharmaRugSpider(BaseSpider):
    conference = "pharmarug-cn"
    base_url = "https://pharmarug.github.io"
    rate_limit = 1.0

    def collect(self) -> list[Paper]:
        events = self._discover_events()
        if not events:
            log.warning("[pharmarug-cn] 首页无年会链接")
            return []
        papers: list[Paper] = []
        for ev in events:
            papers.extend(self._collect_year(ev))
        log.info("[pharmarug-cn] %d 届年会,共 %d 条", len(events), len(papers))
        return papers

    def _discover_events(self) -> list[dict]:
        html = self.fetch_html(ROOT_URL)
        if not html:
            return []
        soup = self.soup(html)
        out: list[dict] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=re.compile(r"pharmarug-\d{4}/?$", re.I)):
            url = a["href"].rstrip("/")
            if url in seen:
                continue
            seen.add(url)
            m = re.search(r"pharmarug-(\d{4})", url, re.I)
            if m:
                out.append({"year": int(m.group(1)), "url": url + "/"})
        out.sort(key=lambda e: e["year"])
        return out

    def _collect_year(self, ev: dict) -> list[Paper]:
        url = ev["url"] + "program.html"
        html = self.fetch_html(url)
        if not html:
            log.info("[pharmarug-cn] %d 年无 program 页,跳过", ev["year"])
            return []
        soup = self.soup(html)
        papers: list[Paper] = []
        seq = 0
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 3:
                    continue
                if all(c.name == "th" for c in cells):
                    continue  # 表头行(Time|Topic|Presenter|Location)
                topic_cell = cells[1]
                presenter = _clean(cells[2].get_text(" ", strip=True))
                if not presenter:
                    continue  # Registration/Break 等无演讲者行

                title, slides_url = _parse_topic(topic_cell, ev["url"])
                if not title or _SKIP_TITLE.match(title):
                    continue
                # 纯 "Welcome" 等开场行: 有演讲者但标题过短也保留(官网如此收录)

                seq += 1
                papers.append(self.make_paper(
                    title=title,
                    authors=_parse_presenters(presenter),
                    year=ev["year"],
                    section_code="MT",
                    section_name="Annual Meeting Talk",
                    paper_code=f"PRUG-{ev['year']}-{seq:02d}",
                    pdf_url=slides_url,
                    source_url=url,
                    lang="en",
                ))
        log.info("[pharmarug-cn] %d 年 %d 条", ev["year"], len(papers))
        return papers


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _parse_topic(cell, event_url: str) -> tuple[str, str]:
    """Topic 单元格 -> (标题, slides 链接)。

    slides 链接(pptx/pdf)的锚文本即标题;无 slides 时取单元格文本
    并去掉尾部 'video'/'video N' 标记。
    """
    slides_url = ""
    for a in cell.find_all("a", href=True):
        href = a["href"]
        if re.search(r"\.(pptx|ppt|pdf)$", href, re.I):
            if not slides_url:
                slides_url = href if href.startswith("http") else event_url + href
            title = _clean(a.get_text(" ", strip=True))
            if title:
                return title, slides_url

    text = _clean(cell.get_text(" ", strip=True))
    text = re.sub(r"\s*video\s*\d*\s*$", "", text, flags=re.I)
    return text.strip(), ""


def _parse_presenters(raw: str) -> list[str]:
    """'Yan Qiao, BeiGene, Chengeng Tian, Novartis' -> ['Yan Qiao (BeiGene)', 'Chengeng Tian (Novartis)']。

    启发式: 偶数段两两配对(名字, 单位);奇数段(≥3)末段视为共同单位。
    """
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return []
    if len(parts) == 1:
        return parts
    if len(parts) % 2 == 0:
        pairs = [(parts[i], parts[i + 1]) for i in range(0, len(parts), 2)]
    else:
        org = parts[-1]
        names = parts[:-1]
        pairs = [(n, org) for n in names]
    return [f"{n} ({o})" for n, o in pairs if n]
