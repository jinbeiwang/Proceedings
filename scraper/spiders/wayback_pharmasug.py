"""Wayback Machine spider — 恢复 PharmaSUG 旧年份 proceedings。

PharmaSUG 官网近年(2011+)的 proceedings 可直接抓取,但更早年份(2007-2010等)
的索引页可能已变更结构或不可达。本 spider 通过 Wayback Machine CDX API
查找归档的 PharmaSUG proceedings 页面和 PDF 链接,解析论文列表。

工作流程:
  1. CDX API 查询 pharmasug.org 上所有 proceedings 相关的归档 URL
  2. 从 CDX 结果中直接提取 PDF 链接(含年份/section/编号信息)
  3. 如有索引页归档,获取并解析标题/作者
  4. 输出 Paper 对象(conference="pharmasug-us"),PDF URL 指向 Wayback

输出论文与现有 PharmaSUG spider 合并(按 id 去重)。
"""
from __future__ import annotations

import re
from collections import defaultdict

from base import BaseSpider, log
from models import Paper, CONFERENCES

# PharmaSUG 论文 PDF 链接正则
# 标准格式: /proceedings/2013/AD/PharmaSUG-2013-AD-001.pdf
PAPER_RE = re.compile(
    r"/proceedings/(\d{4})/([A-Z]+)/([\w.-]+)\.pdf", re.IGNORECASE
)
# 旧格式: /proceedings/2010/PharmaSUG-2010-AD-001.pdf (无 section 子目录)
PAPER_RE_OLD = re.compile(
    r"/proceedings/(\d{4})/([\w.-]+)\.pdf", re.IGNORECASE
)
# 最佳论文格式: /download/bestpapers2008/AD/PharmaSUG-2008-AD-01.pdf
BEST_PAPER_RE = re.compile(
    r"/download/bestpapers(\d{4})/([A-Z]+)/([\w.-]+)\.pdf", re.IGNORECASE
)
# CD 论文格式: /cd/papers/AD/AD01.pdf (无年份,归为 2010)
CD_PAPER_RE = re.compile(
    r"/cd/papers/([A-Z]+)/([\w.-]+)\.pdf", re.IGNORECASE
)
# 年度 proceedings 索引页
YEAR_RE = re.compile(r"pharmasug[-_](\d{4})[-_]us/conference[-_]proceedings", re.IGNORECASE)
OLD_INDEX_RE = re.compile(r"/proceedings/(\d{4})/?$", re.IGNORECASE)


class WaybackPharmaSUGSpider(BaseSpider):
    conference = "pharmasug-us"
    base_url = "https://pharmasug.org"
    rate_limit = 2.0

    def collect(self) -> list[Paper]:
        # 强制使用 pharmasug-us 作为会议代码(main.py 可能传入 pharmasug-wayback)
        self.conference = "pharmasug-us"
        self.meta = CONFERENCES.get("pharmasug-us", {})

        log.info("[pharmasug-wayback] 开始从 Wayback Machine 恢复旧年份 PharmaSUG 论文")

        # 1. CDX 查询: 找到所有归档的 proceedings 相关 URL
        cdx_results: list[dict] = []
        for pattern in [
            "pharmasug.org/proceedings/*",
            "www.pharmasug.org/proceedings/*",
            "pharmasug.org/download/bestpapers*/*",
            "www.pharmasug.org/download/bestpapers*/*",
            "pharmasug.org/cd/papers/*",
            "www.pharmasug.org/cd/papers/*",
        ]:
            results = self.wayback_cdx_search(pattern, limit=5000)
            cdx_results.extend(results)
            log.info("[pharmasug-wayback] CDX 查询 %s -> %d 条", pattern, len(results))

        if not cdx_results:
            log.warning("[pharmasug-wayback] CDX 无结果")
            return []

        # 2. 去重: 每个 original URL 只取最近一次成功的快照
        url_latest: dict[str, str] = {}  # original_url -> timestamp
        for r in cdx_results:
            orig = r.get("original", "")
            ts = r.get("timestamp", "")
            if orig and ts:
                if orig not in url_latest or ts > url_latest[orig]:
                    url_latest[orig] = ts

        log.info("[pharmasug-wayback] 去重后 %d 个唯一 URL", len(url_latest))

        # 3. 从 PDF URL 中直接提取论文信息
        papers_from_pdf: list[Paper] = []
        seen_ids: set[str] = set()
        index_pages: dict[int, list[tuple[str, str]]] = defaultdict(list)  # year -> [(url, ts)]

        for orig, ts in url_latest.items():
            # 匹配标准 PDF 链接
            m = PAPER_RE.search(orig)
            if m:
                year = int(m.group(1))
                section = m.group(2).upper()
                paper_code = m.group(3)
                pdf_url = self.wayback_url(orig, ts)
                papers_from_pdf.append(
                    self.make_paper(
                        title=paper_code,
                        year=year,
                        section_code=section,
                        section_name=section,
                        paper_code=paper_code,
                        pdf_url=pdf_url,
                        source_url=orig,
                    )
                )
                continue

            # 匹配旧格式 PDF 链接
            m = PAPER_RE_OLD.search(orig)
            if m:
                year = int(m.group(1))
                paper_code = m.group(2)
                # 从编号提取 section: PharmaSUG-2010-AD-001 -> AD
                sec_match = re.search(r"-([A-Z]+)-\d+", paper_code, re.IGNORECASE)
                section = sec_match.group(1).upper() if sec_match else ""
                pdf_url = self.wayback_url(orig, ts)
                papers_from_pdf.append(
                    self.make_paper(
                        title=paper_code,
                        year=year,
                        section_code=section,
                        section_name=section,
                        paper_code=paper_code,
                        pdf_url=pdf_url,
                        source_url=orig,
                    )
                )
                continue

            # 匹配最佳论文格式: /download/bestpapers2008/AD/PharmaSUG-2008-AD-01.pdf
            m = BEST_PAPER_RE.search(orig)
            if m:
                year = int(m.group(1))
                section = m.group(2).upper()
                paper_code = m.group(3)
                pdf_url = self.wayback_url(orig, ts)
                papers_from_pdf.append(
                    self.make_paper(
                        title=f"Best Paper: {paper_code}",
                        year=year,
                        section_code=section,
                        section_name=f"{section} (Best Paper)",
                        paper_code=f"PharmaSUG-{year}-{paper_code}",
                        pdf_url=pdf_url,
                        source_url=orig,
                    )
                )
                continue

            # 匹配 CD 论文格式: /cd/papers/AD/AD01.pdf (年份未知,归为 2010)
            m = CD_PAPER_RE.search(orig)
            if m:
                section = m.group(1).upper()
                paper_code = m.group(2)
                year = 2010  # CD 论文最早归档于 2010 年底
                pdf_url = self.wayback_url(orig, ts)
                papers_from_pdf.append(
                    self.make_paper(
                        title=f"CD Paper: {paper_code}",
                        year=year,
                        section_code=section,
                        section_name=f"{section} (CD)",
                        paper_code=f"PharmaSUG-{year}-CD-{paper_code}",
                        pdf_url=pdf_url,
                        source_url=orig,
                    )
                )
                continue

            # 匹配年度索引页
            m = YEAR_RE.search(orig)
            if m:
                year = int(m.group(1))
                index_pages[year].append((orig, ts))
                continue

            m = OLD_INDEX_RE.search(orig)
            if m:
                year = int(m.group(1))
                index_pages[year].append((orig, ts))

        log.info(
            "[pharmasug-wayback] 从 PDF URL 提取 %d 篇, 发现 %d 个年份的索引页",
            len(papers_from_pdf), len(index_pages),
        )

        # 4. 去重 PDF 提取的论文
        all_papers: list[Paper] = []
        for p in papers_from_pdf:
            if p.id not in seen_ids:
                seen_ids.add(p.id)
                all_papers.append(p)

        # 5. 抓取索引页,获取标题/作者(覆盖 PDF 提取的占位标题)
        for year, pages in sorted(index_pages.items()):
            for page_url, ts in pages:
                log.info("[pharmasug-wayback] %d 年索引页 -> %s", year, page_url)
                papers = self._scrape_archived_page(page_url, ts, year)
                for p in papers:
                    if p.id not in seen_ids:
                        seen_ids.add(p.id)
                        all_papers.append(p)
                    else:
                        # 更新已有论文的标题(如果索引页有更好的标题)
                        for existing in all_papers:
                            if existing.id == p.id and p.title and len(p.title) > len(existing.title):
                                existing.title = p.title
                                if p.authors:
                                    existing.authors = p.authors
                                break

        log.info("[pharmasug-wayback] 共恢复 %d 篇旧论文", len(all_papers))
        return all_papers

    def _scrape_archived_page(self, page_url: str, timestamp: str, expected_year: int) -> list[Paper]:
        """抓取并解析归档的 proceedings 页面。"""
        wayback_url = f"https://web.archive.org/web/{timestamp}id_/{page_url}"
        html = self.fetch_html(wayback_url)
        if not html:
            return []

        soup = self.soup(html)
        papers: list[Paper] = []
        seen_urls: set[str] = set()

        # 建立 section 代码 -> 名称映射(来自锚点链接)
        section_names: dict[str, str] = {}
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("#") and len(href) > 1:
                code = href[1:].upper()
                name = a.get_text(strip=True)
                if name and len(code) <= 6:
                    section_names[code] = name

        # 提取所有 PDF 链接
        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = a.get_text(strip=True)

            # 匹配标准 PDF 链接
            m = PAPER_RE.search(href)
            if m:
                p_year, section, paper_code = m.group(1), m.group(2).upper(), m.group(3)
            else:
                m = PAPER_RE_OLD.search(href)
                if m:
                    p_year, paper_code = m.group(1), m.group(2)
                    section = ""
                else:
                    continue

            try:
                year = int(p_year)
            except ValueError:
                continue

            if year != expected_year:
                continue

            # 构造 PDF URL
            pdf_url = self._resolve_pdf_url(href, page_url, timestamp)
            if not pdf_url or pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)

            if not title or len(title) < 3:
                title = paper_code

            papers.append(
                self.make_paper(
                    title=title,
                    year=year,
                    section_code=section,
                    section_name=section_names.get(section, section) if section else "Proceedings",
                    paper_code=paper_code,
                    pdf_url=pdf_url,
                    source_url=page_url,
                )
            )

        if papers:
            log.info(
                "[pharmasug-wayback] %d 年: 解析出 %d 篇 (来源 %s)",
                expected_year, len(papers), page_url,
            )

        return papers

    def _resolve_pdf_url(self, href: str, page_url: str, timestamp: str) -> str:
        """将归档页面中的相对/绝对 PDF 链接解析为可访问的 Wayback URL。"""
        if "web.archive.org" in href:
            return href

        href = href.split("#")[0]

        if href.startswith("http"):
            original = href
        elif href.startswith("/"):
            original = f"https://pharmasug.org{href}"
        else:
            base = page_url.rstrip("/")
            original = f"{base}/{href}"

        return self.wayback_url(original, timestamp)
