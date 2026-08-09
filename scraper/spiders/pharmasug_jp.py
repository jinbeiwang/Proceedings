"""PharmaSUG Japan proceedings spider。

PharmaSUG Japan 以 Single Day Event 形式举办,论文(讲演资料)托管在
pharmasug.org/proceedings/japan{year}/(WordPress 静态页):
  - 2023 / 2025:页面直连可用(2025-08 实地核实),含 PDF 标题与直链
  - 2020-2024 部分年份对非浏览器 UA 返回 403,降级走 Wayback 归档
  - 页面无作者信息,仅收录标题/PDF 链接
"""
from __future__ import annotations

import re

from base import BaseSpider, log
from models import Paper

CODE_RE = re.compile(r"PharmaSUG[-_]?Japan[-_]?\d{4}[-_]?(\w+)\.(?:pdf|pptx?)",
                     re.IGNORECASE)


class PharmaSUGJapanSpider(BaseSpider):
    conference = "pharmasug-jp"
    base_url = "https://www.pharmasug.org"
    rate_limit = 1.0

    YEARS = list(range(2018, 2027))

    def set_years(self, years: set[int]) -> None:
        self.years = sorted(years)

    def collect(self) -> list[Paper]:
        years = getattr(self, "years", None) or self.YEARS
        papers: list[Paper] = []
        for year in years:
            got = self._scrape_year(year)
            if got:
                log.info("[pharmasug-jp] %d 年: %d 篇", year, len(got))
                papers.extend(got)
        log.info("[pharmasug-jp] 共 %d 篇", len(papers))
        return papers

    def _scrape_year(self, year: int) -> list[Paper]:
        url = f"{self.base_url}/proceedings/japan{year}/"
        html = self.fetch_html(url)
        if not html or ".pdf" not in html.lower():
            # 403/404 或页面无 PDF -> 走 Wayback 归档(CI 环境可达)
            html = self.fetch_wayback(url) or html
        if not html:
            return []
        return self._parse(html, year, url)

    def _parse(self, html: str, year: int, page_url: str) -> list[Paper]:
        soup = self.soup(html)
        papers: list[Paper] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not re.search(r"\.(pdf|pptx?)$", href, re.I):
                continue
            if "japan" not in href.lower() and "pharmasug" not in href.lower():
                continue
            # 排除会场/第三方无关 PDF(如 2023 页的场地指引链接)
            if "pharmasug" not in href.lower():
                continue
            if href.startswith("/"):
                pdf_url = f"{self.base_url}{href}"
            elif href.startswith("http"):
                pdf_url = href
            else:
                continue

            fname = href.rsplit("/", 1)[-1]
            m = CODE_RE.search(fname)
            num = m.group(1) if m else ""
            code = f"PharmaSUG-Japan-{year}-{num}" if num else \
                f"PharmaSUG-Japan-{year}-{len(papers) + 1:02d}"

            title = a.get_text(" ", strip=True)
            if not title or len(title) < 3:
                # 兜底:从文件名生成可读标题
                title = re.sub(r"\.(pdf|pptx?)$", "", fname, flags=re.I)
                title = title.replace("-", " ").replace("_", " ")
                title = re.sub(r"^PharmaSUG\s*Japan\s*\d{4}\s*", "",
                               title, flags=re.I).strip() or code

            pid = Paper.make_id(self.conference, code)
            if pid in seen:
                continue
            seen.add(pid)
            papers.append(self.make_paper(
                id=pid,
                title=title,
                year=year,
                paper_code=code,
                section_code="KS",
                section_name="Presentations",
                pdf_url=pdf_url,
                source_url=page_url,
            ))
        return papers
