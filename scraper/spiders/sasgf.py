"""SAS Global Forum / SUGI proceedings spider。

覆盖四个时期的论文归档(已实地核实 2026-08):

1. SUGI 早期 (1976-1996, 第1-21届):
   - TOC 页: https://support.sas.com/resources/papers/proceedings-archive/SUGI{YY}/proceedings.html
   - PDF: .../SUGI{YY}/Sugi-{YY}-{编号} {作者}.pdf
   - 结构: <a class="external text" href="...pdf">标题</a> + <ul>作者</ul>
   - 状态: ✅ 在线

2. SUGI 后期 (1997-2006, 第22-31届):
   - TOC 页: https://www2.sas.com/proceedings/sugi{N}/ → 403,需 Wayback
   - PDF: sugi{N}/{编号}-{N}.pdf (在线)
   - 状态: ⚠️ TOC 需走 Wayback

3. SGF 前期 (2007-2014):
   - TOC 页: https://www2.sas.com/proceedings/forum{YYYY}/
   - PDF: forum{YYYY}/{编号}-{YYYY}.pdf
   - 结构: 每篇 2 个 <tr>(编号+作者 / 标题)
   - 状态: ✅ 在线(需限速)

4. SGF 后期 (2015-2021):
   - PDF: https://www.sas.com/content/dam/SAS/support/en/sas-global-forum-proceedings/{YYYY}/{编号}-{YYYY}.pdf
   - TOC: ❌ 已移除,需 Wayback 恢复
   - 状态: ⚠️ TOC 需走 Wayback
"""
from __future__ import annotations

import re

from base import BaseSpider, log
from models import Paper

# SUGI 年份 <-> 届号映射
SUGI_EARLY_START = 1976   # SUGI 1
SUGI_EARLY_END = 1996     # SUGI 21
SUGI_LATE_START = 1997    # SUGI 22
SUGI_LATE_END = 2006      # SUGI 31
SGF_START = 2007
SGF_END = 2021


class SASGlobalForumSpider(BaseSpider):
    conference = "sgf"
    base_url = "https://www2.sas.com"
    rate_limit = 2.0

    def collect(self) -> list[Paper]:
        if self.conference == "sugi":
            return self._collect_sugi()
        return self._collect_sgf()

    # ---- SUGI ----
    def _collect_sugi(self) -> list[Paper]:
        papers: list[Paper] = []

        # SUGI 早期 (1976-1996): 直接从 support.sas.com 抓取
        for year in range(SUGI_EARLY_START, SUGI_EARLY_END + 1):
            yy = year - 1900
            log.info("[sugi] 抓取 SUGI %d (早期归档)", year)
            papers.extend(self._scrape_sugi_early(year, yy))

        # SUGI 后期 (1997-2006): Wayback Machine
        for year in range(SUGI_LATE_START, SUGI_LATE_END + 1):
            n = year - 1975  # 届号
            log.info("[sugi] 抓取 SUGI %d (第%d届, Wayback)", year, n)
            papers.extend(self._scrape_sugi_late(year, n))

        log.info("[sugi] 共 %d 篇", len(papers))
        return papers

    def _scrape_sugi_early(self, year: int, yy: int) -> list[Paper]:
        """SUGI 1976-1996: support.sas.com 上的早期归档。"""
        url = f"https://support.sas.com/resources/papers/proceedings-archive/SUGI{yy:02d}/proceedings.html"
        html = self.fetch_html(url)
        if not html:
            return []

        soup = self.soup(html)
        papers: list[Paper] = []
        seen: set[str] = set()

        for a in soup.find_all("a", class_="external text"):
            href = a.get("href", "")
            if ".pdf" not in href.lower():
                continue

            pdf_url = href
            if not pdf_url.startswith("http"):
                pdf_url = f"https://support.sas.com/resources/papers/proceedings-archive/SUGI{yy:02d}/{href}"

            if pdf_url in seen:
                continue
            seen.add(pdf_url)

            title = a.get_text(strip=True)
            if not title:
                continue

            # 作者在紧邻的 <ul> 中
            author = ""
            ul = a.find_next_sibling("ul") or a.find_next("ul")
            if ul:
                author = ul.get_text(strip=True)

            # 从文件名提取编号: Sugi-76-02 Goodnight.pdf -> SUGI76-02
            fname = href.split("/")[-1]
            m = re.match(r"Sugi-(\d+)-(\w+)", fname, re.IGNORECASE)
            paper_code = f"SUGI{yy:02d}-{m.group(2)}" if m else f"SUGI{yy:02d}-{len(papers)+1:03d}"

            papers.append(
                self.make_paper(
                    title=title,
                    authors=[author] if author else [],
                    year=year,
                    section_code="",
                    section_name="SUGI Proceedings",
                    paper_code=paper_code,
                    pdf_url=pdf_url,
                    source_url=url,
                )
            )

        return papers

    def _scrape_sugi_late(self, year: int, n: int) -> list[Paper]:
        """SUGI 1997-2006: Wayback Machine 获取 TOC 页,失败则 CDX 直查。"""
        original_url = f"https://www2.sas.com/proceedings/sugi{n}/"
        html = self.fetch_wayback(original_url)
        if html:
            papers = self._parse_sugi_late_toc(html, year, n, original_url)
            if papers:
                return papers

        # CDX 直查 PDF
        log.info("[sugi] %d 年 TOC 无结果,尝试 CDX 直查", year)
        return self._scrape_sugi_cdx(year, n)

    def _scrape_sugi_cdx(self, year: int, n: int) -> list[Paper]:
        """通过 CDX API 直接查找 SUGI 某年的所有 PDF 归档。"""
        pattern = f"www2.sas.com/proceedings/sugi{n}/*"
        results = self.wayback_cdx_search(pattern, limit=2000)

        url_latest: dict[str, str] = {}
        for r in results:
            orig = r.get("original", "")
            ts = r.get("timestamp", "")
            if orig and ts and ".pdf" in orig.lower():
                if orig not in url_latest or ts > url_latest[orig]:
                    url_latest[orig] = ts

        if not url_latest:
            log.warning("[sugi] %d 年 CDX 也无结果", year)
            return []

        papers: list[Paper] = []
        seen: set[str] = set()
        pdf_re = re.compile(r"(\d[\d]*)[-_](\d+)\.pdf", re.IGNORECASE)

        for orig, ts in sorted(url_latest.items()):
            m = pdf_re.search(orig)
            if not m:
                continue
            paper_num = m.group(1)
            paper_code = f"SUGI{year}-{paper_num}"
            if paper_code in seen:
                continue
            seen.add(paper_code)

            pdf_url = self.wayback_url(orig, ts)
            papers.append(
                self.make_paper(
                    title=f"SUGI {year} Paper {paper_num}",
                    year=year,
                    section_code="",
                    section_name="SUGI Proceedings",
                    paper_code=paper_code,
                    pdf_url=pdf_url,
                    source_url=orig,
                )
            )

        log.info("[sugi] %d 年 CDX 提取 %d 篇", year, len(papers))
        return papers

    def _parse_sugi_late_toc(self, html: str, year: int, n: int, source_url: str) -> list[Paper]:
        """解析 SUGI 后期 TOC 页面。"""
        soup = self.soup(html)
        papers: list[Paper] = []
        seen: set[str] = set()

        # SUGI 后期 TOC 结构与 SGF 类似,尝试多种解析方式
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # 匹配 PDF 链接: 024-30.pdf, 165-29.pdf 等
            m = re.search(r"(\d[\d]*)[-_](\d+)\.pdf", href, re.IGNORECASE)
            if not m:
                continue

            pdf_url = href
            if not pdf_url.startswith("http"):
                pdf_url = f"https://www2.sas.com/proceedings/sugi{n}/{href}"

            if pdf_url in seen:
                continue
            seen.add(pdf_url)

            title = a.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            # 论文编号
            paper_num = m.group(1)
            paper_code = f"SUGI{year}-{paper_num}"

            # 尝试提取作者(同行的相邻文本)
            author = ""
            parent = a.parent
            if parent:
                text = parent.get_text(strip=True)
                # 移除标题文本后的部分作为作者
                if title in text:
                    remainder = text[text.index(title) + len(title):].strip(" .;,-")
                    if remainder and len(remainder) < 200:
                        author = remainder

            papers.append(
                self.make_paper(
                    title=title,
                    authors=[author] if author else [],
                    year=year,
                    section_code="",
                    section_name="SUGI Proceedings",
                    paper_code=paper_code,
                    pdf_url=pdf_url,
                    source_url=source_url,
                )
            )

        return papers

    # ---- SAS Global Forum ----
    def _collect_sgf(self) -> list[Paper]:
        papers: list[Paper] = []

        # SGF 前期 (2007-2008): 直接从 www2.sas.com 抓取(2009+ 已迁移,需 Wayback)
        for year in range(SGF_START, 2009):
            log.info("[sgf] 抓取 SAS Global Forum %d (www2.sas.com)", year)
            papers.extend(self._scrape_sgf_early(year))

        # SGF 后期 (2009-2021): Wayback Machine(www2.sas.com 页面已 301 到 404)
        for year in range(2009, SGF_END + 1):
            log.info("[sgf] 抓取 SAS Global Forum %d (Wayback)", year)
            papers.extend(self._scrape_sgf_late(year))

        log.info("[sgf] 共 %d 篇", len(papers))
        return papers

    def _scrape_sgf_early(self, year: int) -> list[Paper]:
        """SGF 2007-2014: www2.sas.com 上的 TOC 页。"""
        url = f"https://www2.sas.com/proceedings/forum{year}/"
        html = self.fetch_html(url)
        if not html:
            return []

        soup = self.soup(html)
        papers: list[Paper] = []
        seen: set[str] = set()

        # SGF TOC 结构: 每篇论文由 2 个 <tr> 组成
        # 第1个 <tr>: <a href=".../002-2007.pdf"><b>Paper 002-2007:</b></a> + 作者
        # 第2个 <tr>: <i><a href=".../002-2007.pdf">标题</a></i>
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # 匹配 PDF: 002-2007.pdf, 184-2007.pdf
            m = re.search(r"(\d+)[-_](\d{4})\.pdf", href, re.IGNORECASE)
            if not m:
                continue

            paper_num = m.group(1)
            url_year = m.group(2)
            if url_year != str(year):
                continue

            pdf_url = href
            if not pdf_url.startswith("http"):
                pdf_url = f"https://www2.sas.com/proceedings/forum{year}/{href}"

            if pdf_url in seen:
                continue
            seen.add(pdf_url)

            # 提取标题(斜体链接中的文本,或链接文本本身)
            title = ""
            link_text = a.get_text(strip=True)

            # 如果链接文本是 "Paper 002-2007:" 格式,标题在下一个 <tr> 的 <i><a> 中
            if re.match(r"Paper\s+\d+", link_text, re.IGNORECASE):
                # 找下一个 <a> 标签(标题链接)
                next_a = a.find_next("a", href=True)
                if next_a and ".pdf" in next_a.get("href", "").lower():
                    title = next_a.get_text(strip=True)

                # 作者在同一个 <td> 的下一个 <td> 中
                author = ""
                tr = a.find_parent("tr")
                if tr:
                    tds = tr.find_all("td")
                    if len(tds) >= 2:
                        author = tds[-1].get_text(strip=True).strip(";").strip()
            else:
                # 链接文本就是标题
                title = link_text
                author = ""

            if not title:
                title = f"Paper {paper_num}-{year}"

            paper_code = f"SGF{year}-{paper_num}"

            papers.append(
                self.make_paper(
                    title=title,
                    authors=[author] if author else [],
                    year=year,
                    section_code="",
                    section_name="SAS Global Forum",
                    paper_code=paper_code,
                    pdf_url=pdf_url,
                    source_url=url,
                )
            )

        return papers

    def _scrape_sgf_late(self, year: int) -> list[Paper]:
        """SGF 2009-2021: Wayback Machine 获取 TOC 页,失败则用 CDX 直查 PDF。"""
        # 方法 1: 尝试多个可能的 TOC URL
        candidates = [
            f"https://www2.sas.com/proceedings/forum{year}/",
            f"https://support.sas.com/resources/papers/proceedings/proceedings/pdfs/sgf{year}/",
            f"https://support.sas.com/resources/papers/proceedings/proceedings/forum{year}/",
            f"https://support.sas.com/resources/papers/proceedings/forum{year}/",
        ]

        for url in candidates:
            html = self.fetch_wayback(url)
            if html and ".pdf" in html:
                papers = self._parse_sgf_early_toc(html, year, url)
                if papers:
                    return papers

        # 方法 2: CDX 直查 PDF URL
        log.info("[sgf] %d 年 TOC 页无结果,尝试 CDX 直查 PDF", year)
        return self._scrape_sgf_cdx(year)

    def _scrape_sgf_cdx(self, year: int) -> list[Paper]:
        """通过 CDX API 直接查找 SGF 某年份的所有 PDF 归档。"""
        patterns = [
            f"www.sas.com/content/dam/SAS/support/en/sas-global-forum-proceedings/{year}/*",
            f"www2.sas.com/proceedings/forum{year}/*",
            f"support.sas.com/resources/papers/proceedings/proceedings/pdfs/sgf{year}/*",
        ]

        # 收集所有 CDX 结果
        url_latest: dict[str, str] = {}  # original_url -> timestamp
        for pattern in patterns:
            results = self.wayback_cdx_search(pattern, limit=2000)
            for r in results:
                orig = r.get("original", "")
                ts = r.get("timestamp", "")
                if orig and ts and ".pdf" in orig.lower():
                    if orig not in url_latest or ts > url_latest[orig]:
                        url_latest[orig] = ts

        if not url_latest:
            log.warning("[sgf] %d 年 CDX 也无 PDF 结果", year)
            return []

        # 从 PDF URL 提取论文信息
        papers: list[Paper] = []
        seen: set[str] = set()
        pdf_re = re.compile(r"(\d+)[-_](\d{4})\.pdf", re.IGNORECASE)

        for orig, ts in sorted(url_latest.items()):
            m = pdf_re.search(orig)
            if not m:
                continue

            paper_num = m.group(1)
            url_year = m.group(2)
            if url_year != str(year):
                continue

            paper_code = f"SGF{year}-{paper_num}"
            if paper_code in seen:
                continue
            seen.add(paper_code)

            pdf_url = self.wayback_url(orig, ts)
            papers.append(
                self.make_paper(
                    title=f"Paper {paper_num}-{year}",
                    year=year,
                    section_code="",
                    section_name="SAS Global Forum",
                    paper_code=paper_code,
                    pdf_url=pdf_url,
                    source_url=orig,
                )
            )

        log.info("[sgf] %d 年 CDX 提取 %d 篇", year, len(papers))
        return papers

    def _parse_sgf_early_toc(self, html: str, year: int, source_url: str) -> list[Paper]:
        """解析 SGF TOC 页面(复用前期解析逻辑)。"""
        soup = self.soup(html)
        papers: list[Paper] = []
        seen: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"(\d+)[-_](\d{4})\.pdf", href, re.IGNORECASE)
            if not m:
                continue

            paper_num = m.group(1)
            url_year = m.group(2)
            if url_year != str(year):
                continue

            # 构造 PDF URL(优先用 content/dam 路径)
            pdf_url = href
            if not pdf_url.startswith("http"):
                if "web.archive.org" in source_url:
                    # Wayback 快照: 用 wayback URL
                    pdf_url = self._wayback_pdf_url(href, year, source_url)
                else:
                    pdf_url = f"https://www2.sas.com/proceedings/forum{year}/{href}"

            if pdf_url in seen:
                continue
            seen.add(pdf_url)

            title = ""
            link_text = a.get_text(strip=True)

            if re.match(r"Paper\s+\d+", link_text, re.IGNORECASE):
                next_a = a.find_next("a", href=True)
                if next_a and ".pdf" in next_a.get("href", "").lower():
                    title = next_a.get_text(strip=True)
                author = ""
                tr = a.find_parent("tr")
                if tr:
                    tds = tr.find_all("td")
                    if len(tds) >= 2:
                        author = tds[-1].get_text(strip=True).strip(";").strip()
            else:
                title = link_text
                author = ""

            if not title or len(title) < 3:
                continue

            paper_code = f"SGF{year}-{paper_num}"

            papers.append(
                self.make_paper(
                    title=title,
                    authors=[author] if author else [],
                    year=year,
                    section_code="",
                    section_name="SAS Global Forum",
                    paper_code=paper_code,
                    pdf_url=pdf_url,
                    source_url=source_url,
                )
            )

        return papers

    def _wayback_pdf_url(self, href: str, year: int, source_url: str) -> str:
        """从 Wayback 快照 URL 构造 PDF 的 Wayback URL。"""
        # 提取 timestamp 从 source_url
        m = re.search(r"/web/(\d+)", source_url)
        ts = m.group(1) if m else ""

        # 确保 href 是绝对 URL
        if href.startswith("http"):
            original = href
        elif href.startswith("/"):
            original = f"https://www2.sas.com{href}"
        else:
            original = f"https://www2.sas.com/proceedings/forum{year}/{href}"

        # 尝试 content/dam 路径(后期 SGF)
        dam_url = f"https://www.sas.com/content/dam/SAS/support/en/sas-global-forum-proceedings/{year}/{href.split('/')[-1]}"
        if ts:
            return self.wayback_url(dam_url, ts)
        return dam_url
