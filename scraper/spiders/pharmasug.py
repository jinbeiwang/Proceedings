"""PharmaSUG US proceedings spider。

已验证的官网结构(2026-08 实地核实):
  - 索引页: https://pharmasug.org/past-conference-proceedings/
    按年份列出各届会议,链接形如
    /conferences/pharmasug-{year}-us/conference-proceedings/
  - 年度页: 含 section 锚点链接 <a href="#AP">Advanced Programming</a>
    以及论文直链 <a href="/proceedings/{year}/{SECTION}/PharmaSUG-{year}-{SECTION}-{num}.pdf">
  - 论文标题即链接文本;作者信息需从 PDF 正文提取(此处仅索引)。

本 spider 抓取全部可用年份,输出 title/section/year/paper_code/pdf_url。
"""
from __future__ import annotations

import re
from datetime import datetime

from base import BaseSpider, log
from models import Paper

# 论文 PDF 直链: /proceedings/2025/AP/PharmaSUG-2025-AP-002.pdf
PAPER_RE = re.compile(
    r"/proceedings/(\d{4})/([A-Z]+)/([\w.-]+)\.pdf$", re.IGNORECASE
)
# 年度 proceedings 页: /conferences/pharmasug-2025-us/conference-proceedings/
YEAR_RE = re.compile(r"pharmasug-(\d{4})-us/conference-proceedings/?", re.IGNORECASE)
# section 锚点: #AP
ANCHOR_RE = re.compile(r"^#([A-Z]+)$")


class PharmaSUGSpider(BaseSpider):
    conference = "pharmasug-us"
    base_url = "https://pharmasug.org"
    rate_limit = 1.2

    INDEX_URL = "https://pharmasug.org/past-conference-proceedings/"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.years_filter: set[int] | None = None

    def set_years(self, years: set[int]) -> None:
        self.years_filter = years

    def collect(self) -> list[Paper]:
        papers: list[Paper] = []
        for year, year_url in self._discover_years():
            if self.years_filter and year not in self.years_filter:
                continue
            log.info("[pharmasug-us] 抓取 %d 年 -> %s", year, year_url)
            papers.extend(self._scrape_year(year, year_url))
        log.info("[pharmasug-us] 共 %d 篇", len(papers))
        return papers

    def _discover_years(self) -> list[tuple[int, str]]:
        """从索引页发现年度 proceedings 页;失败则按年份枚举兜底。"""
        html = self.fetch_html(self.INDEX_URL)
        found: dict[int, str] = {}
        if html:
            for a in self.soup(html).find_all("a", href=True):
                m = YEAR_RE.search(a["href"])
                if m:
                    y = int(m.group(1))
                    found[y] = self.absurl(a["href"].split("#")[0])
        # 兜底: 索引页若为 JS 渲染,枚举近年(PharmaSUG US 自 2011 起有在线 proceedings)
        if not found:
            this_year = datetime.now().year
            for y in range(2011, this_year + 1):
                found[y] = (
                    f"{self.base_url}/conferences/pharmasug-{y}-us/conference-proceedings/"
                )
        return sorted(found.items())

    def _scrape_year(self, year: int, year_url: str) -> list[Paper]:
        html = self.fetch_html(year_url)
        if not html:
            return []
        soup = self.soup(html)

        # 建立 section 代码 -> 名称 映射(来自锚点链接)
        section_names: dict[str, str] = {}
        for a in soup.find_all("a", href=True):
            m = ANCHOR_RE.match(a["href"].strip())
            if m:
                code = m.group(1).upper()
                name = a.get_text(strip=True)
                if name:
                    section_names[code] = name

        # 提取论文直链
        papers: list[Paper] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            m = PAPER_RE.search(a["href"])
            if not m:
                continue
            p_year, section, paper_code = m.group(1), m.group(2).upper(), m.group(3)
            if str(year) != p_year:       # 跨年链接跳过
                continue
            pdf_url = self.absurl(a["href"])
            if pdf_url in seen:
                continue
            seen.add(pdf_url)
            title = a.get_text(strip=True) or paper_code
            papers.append(
                self.make_paper(
                    title=title,
                    year=int(p_year),
                    section_code=section,
                    section_name=section_names.get(section, section),
                    paper_code=paper_code,
                    pdf_url=pdf_url,
                    source_url=year_url,
                )
            )
        return papers
