"""MWSUG (Midwest SAS Users Group) proceedings spider。

已验证的官网结构(2026-08 实地核实):
  - 论文页: https://www.mwsug.org/{year}/papers (现站仅托管近几年,约 2025 起)
  - 上半部分为 TOC 表格,每行:
      <td class="paper_number">AE-006</td>
      <td class="paper_author">Kirk Paul Lafler<br> & Charu Shankar</td>
      <td class="paper_title"><a href="#AE-006">标题</a></td>
    表格前的 <h2> 为 section 名。
  - 下半部分 "Abstracts" 区,每篇形如:
      <a name="AE-006"></a><b>AE-006 : 标题<br>作者, 单位<br>...</b><br>摘要正文...
  - 官网不提供 PDF 直链,pdf_url 留空,source_url 指向年度论文页。

更早年历史论文现站已下线,如需补齐须走 Wayback(另建 spider)。
"""
from __future__ import annotations

import re
from datetime import datetime
from html import unescape

from base import BaseSpider, log
from models import Paper

PAPER_NUM_RE = re.compile(r"^([A-Z]{2})-(\d{2,4})$")
ANCHOR_RE = re.compile(r'<a[^>]+(?:name|id)="([A-Z]{2}-\d{2,4})"[^>]*>')

# 现站托管的最早年份(探测 2024 及更早为 404;如需扩展向下调整)
YEAR_MIN = 2025


class MWSUGSpider(BaseSpider):
    conference = "mwsug"
    base_url = "https://www.mwsug.org"
    rate_limit = 1.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.years_filter: set[int] | None = None

    def set_years(self, years: set[int]) -> None:
        self.years_filter = years

    def collect(self) -> list[Paper]:
        papers: list[Paper] = []
        year = YEAR_MIN
        year_max = datetime.now().year + 1
        misses = 0
        while misses < 2 and year <= year_max:  # 连续 2 年 404 即认为到头了
            if self.years_filter and year not in self.years_filter:
                year += 1
                continue
            url = f"{self.base_url}/{year}/papers"
            html = self.fetch_html(url)
            if not html or "Error: 404" in html[:4000]:
                log.info("[mwsug] %d 无论文页,跳过", year)
                misses += 1
                year += 1
                continue
            misses = 0
            log.info("[mwsug] 抓取 %d 年 -> %s", year, url)
            got = self._scrape_year(year, url, html)
            log.info("[mwsug] %d 年 %d 篇", year, len(got))
            papers.extend(got)
            year += 1
        log.info("[mwsug] 共 %d 篇", len(papers))
        return papers

    def _scrape_year(self, year: int, page_url: str, html: str) -> list[Paper]:
        soup = self.soup(html)
        abstracts = self._extract_abstracts(soup)

        papers: list[Paper] = []
        for tr in soup.find_all("tr"):
            num_td = tr.find("td", class_="paper_number")
            title_td = tr.find("td", class_="paper_title")
            auth_td = tr.find("td", class_="paper_author")
            if not num_td or not title_td:
                continue
            code = num_td.get_text(" ", strip=True)
            m = PAPER_NUM_RE.match(code)
            if not m:
                continue
            a = title_td.find("a")
            title = (a.get_text(" ", strip=True) if a
                     else title_td.get_text(" ", strip=True))
            if not title:
                continue
            section_code = m.group(1)
            # section 名:行前最近的 <h2>(Abstracts 区无表格,不会误取)
            h2 = tr.find_previous("h2")
            section_name = h2.get_text(" ", strip=True) if h2 else ""
            authors = self._split_authors(
                auth_td.get_text("\n", strip=True) if auth_td else "")
            abstract = abstracts.get(code, "")
            papers.append(self.make_paper(
                id=Paper.make_id(self.conference, f"{year}-{code}"),
                title=title,
                authors=authors,
                year=year,
                conference=self.conference,
                section_code=section_code,
                section_name=section_name,
                paper_code=f"{code}-{year}",
                pdf_url="",
                source_url=page_url,
                abstract=abstract,
            ))
        return papers

    @staticmethod
    def _extract_abstracts(soup) -> dict[str, str]:
        """Abstracts 区:<a name="XX-NNN"> 之间按原文 HTML 切块,去标签。

        每块开头的 <b>CODE : 标题<br>作者, 单位…</b> 与 TOC 表格重复,去掉。
        """
        html = str(soup)
        anchors = [(m.group(1), m.end()) for m in ANCHOR_RE.finditer(html)]
        result: dict[str, str] = {}
        for i, (name, start) in enumerate(anchors):
            end = anchors[i + 1][1] if i + 1 < len(anchors) else min(start + 8000, len(html))
            chunk = html[start:end]
            chunk = re.sub(r"<b>.*?</b>", "", chunk, count=1, flags=re.DOTALL)
            chunk = re.sub(r"<(table|hr)\b.*", "", chunk, flags=re.DOTALL)
            text = unescape(re.sub(r"<[^>]+>", " ", chunk))
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                result[name] = text[:2000]
        return result

    @staticmethod
    def _split_authors(text: str) -> list[str]:
        """'Kirk Paul Lafler\\n & Charu Shankar' -> 按换行/& 拆分。"""
        if not text:
            return []
        parts = re.split(r"\n|&| and ", text)
        out: list[str] = []
        for p in parts:
            p = p.strip(" \t;")
            if p:
                out.append(p)
        return out
