"""PharmaSUG China proceedings spider。

数据来源:
  1. pharmasug.com.cn 官方 API(PSUG_SECTION_BYYEAR → PROCEEDINGS 正文,2023 起)
  2. Wayback Machine 缓存的 lexjansen.com/pharmasug-cn/{year}/ 列表页(旧年份兜底)
  3. pharmasug.org/proceedings/china{year}/ 直链(旧年份)
  4. Wayback Machine 缓存的 xsl_transform.php 动态列表页

PharmaSUG China 自 2012 年起举办,论文以英文为主。

官方 API(2023+):
  POST https://www.pharmasug.com.cn/api/general/v1/query-sug-with-sp.php
  body: action=csp&procedureName=PSUG_SECTION_BYYEAR&param-count=1&param1={year}
  records[] 中 SUB_CATEGORY=PROCEEDINGS 的 BODYTEXT 为会议论文 HTML 列表。

历年 PROCEEDINGS 页面 HTML 格式不一,条目需兼容:
  2023: <b>AA101.</b> <a href=pdf>Title</a><br />Author, Affiliation
  2024: <a href=pdf><b>AA10013.</b>Title</a><br/>Author (Affil)   (部分条目无 href)
  2025/2026: <b>AP134. </b> <a href=pdf>Title</a><br/>Author: Name (Affil)
"""
from __future__ import annotations

import re
import json
import time
from datetime import datetime

import httpx

from base import BaseSpider, log
from models import Paper

# 官方 API
API_URL = "https://www.pharmasug.com.cn/api/general/v1/query-sug-with-sp.php"

# PROCEEDINGS 条目锚点: <b>编号.</b>,编号 = section 代码 + 数字,如 AA101 / AP10006 / HoW10065
CODE_RE = re.compile(
    r"<b>\s*([A-Za-z]+\d+)\.?\s*</b>",
    re.IGNORECASE,
)

# 顶部目录: <a ... href="#AP"...>Advanced Programming (AP)</a>(2024 的 href 无引号)
TOC_RE = re.compile(
    r"<a[^>]*href=[\"']?#([A-Za-z]{2,4})[\"']?[^>]*>([^<]+)</a>",
    re.IGNORECASE,
)

# 无 PDF 条目降级展示用的会议年份页(SPA hash 路由)
def _source_url(year: int) -> str:
    return f"https://www.pharmasug.com.cn/#/{year}"

# 论文链接匹配: 匹配 pharmasug-cn 或 china 路径下的 PDF 链接
PDF_RE = re.compile(
    r"(?:pharmasug-cn|china\d{4})/.*?\.pdf",
    re.IGNORECASE,
)

# 从论文文件名提取 section 和编号
# 例: PharmaSUG-China-2024-AP10006_Final_Paper.pdf -> section=AP, code=AP10006
#     pharmasug-china-2019-dv66.pdf -> section=DV, code=dv66
#     PharmaSUG-China-2017-SP01.pdf -> section=SP, code=SP01
SECTION_FROM_FILENAME = re.compile(
    r"(?:china[-_]?)?\d{4}[-_]?([A-Z]{2,4})[-_]?(\w+)",
    re.IGNORECASE,
)

# Section 代码 -> 名称映射 (与 PharmaSUG US 相同)
SECTION_NAMES = {
    "AD": "Advanced Programming",
    "AP": "Advanced Programming",
    "BB": "Advanced Programming",
    "CC": "Advanced Programming",
    "CD": "Career Development",
    "DA": "Data Analysis",
    "DG": "Advanced Programming",
    "DM": "Data Management",
    "DS": "Data Standards",
    "DV": "Data Visualization & Reporting",
    "EP": "Emerging Technologies",
    "FF": "Foundational Fundamentals",
    "HA": "Health Authority",
    "HO": "Hands-On Training",
    "HS": "Health Outcomes",
    "IB": "Advanced Programming",
    "JP": "Jump Start",
    "KS": "Keynote",
    "LD": "Leadership Development",
    "LS": "Career Development, Leadership & Soft Skills",
    "MA": "Marketing Analytics",
    "MD": "Medical Devices",
    "MM": "Data Visualization & Reporting",
    "MS": "Metadata Management",
    "OS": "Open Source",
    "PG": "Programming & Coding",
    "PK": "PK/PD/ADA and Quantitative Pharmacology",
    "PO": "ePosters",
    "QT": "Statistics and Analytics",
    "REG": "Regulatory",
    "RW": "Real World Evidence and Big Data",
    "SA": "Advanced Statistical Methods",
    "SD": "Study Data Integration & Analysis",
    "SI": "Strategic Implementation & Innovation",
    "SP": "Advanced Statistical Methods",
    "SS": "Submission Standards",
    "ST": "Statistics",
    "TA": "Therapeutic Areas",
    "TF": "Advanced Programming",
    "TT": "Tools, Tech & Innovation",
    "TU": "Tutorials",
    # PharmaSUG China 特有 section 代码
    "AA": "Advanced Programming",
    "AT": "Advanced Programming",
    "CR": "Career Development",
    "HOW": "Hands-On Training",
    "HW": "Hands-On Training",
    "KN": "Keynote",
    "MC": "Marketing Analytics",
    "PS": "Programming & Coding",
    "PT": "Programming & Coding",
    "SR": "Statistics",
    # 2023+ 官网新 section
    "AI": "Artificial Intelligence",
}


class PharmaSUGChinaSpider(BaseSpider):
    conference = "pharmasug-cn"
    base_url = "https://www.lexjansen.com"
    rate_limit = 1.0

    # 官方 API 自 2023 年起有数据;更早年份靠 Wayback/lexjansen 兜底
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.YEARS = list(range(2012, datetime.now().year + 1))

    def collect(self) -> list[Paper]:
        papers: list[Paper] = []
        for year in self.YEARS:
            log.info("[pharmasug-cn] 尝试抓取 %d 年...", year)
            year_papers = self._scrape_year(year)
            if year_papers:
                papers.extend(year_papers)
                log.info("[pharmasug-cn] %d 年: %d 篇", year, len(year_papers))
            else:
                log.info("[pharmasug-cn] %d 年: 无数据", year)
        log.info("[pharmasug-cn] 共 %d 篇", len(papers))
        return papers

    def _scrape_year(self, year: int) -> list[Paper]:
        """尝试多种来源抓取某年论文。"""
        # 策略 1: pharmasug.com.cn 官方 API(2023+ 权威来源)
        papers = self._scrape_official_api(year)
        if papers:
            return papers

        # 策略 2: Wayback Machine 缓存的 lexjansen 列表页
        papers = self._scrape_lexjansen_wayback(year)
        if papers:
            return papers

        # 策略 3: pharmasug.org 直接访问
        papers = self._scrape_pharmasug_org(year)
        if papers:
            return papers

        # 策略 4: Wayback CDX 搜索 PDF 直链
        papers = self._scrape_cdx_pdfs(year)
        return papers

    # ---- 策略 1: 官方 API ----

    def _scrape_official_api(self, year: int) -> list[Paper]:
        """通过 pharmasug.com.cn 官方 API 获取 PROCEEDINGS 正文并解析。"""
        form = {
            "action": "csp",
            "procedureName": "PSUG_SECTION_BYYEAR",
            "param-count": "1",
            "param1": str(year),
        }
        text = ""
        for attempt in range(3):
            self._throttle()
            try:
                resp = self._client.post(API_URL, data=form)
                if resp.status_code == 200:
                    text = resp.text
                    break
                if resp.status_code in (503, 502, 429):
                    time.sleep(3 * (attempt + 1))
                    continue
                log.warning("[pharmasug-cn] 官方 API %d 年 -> HTTP %s", year, resp.status_code)
                return []
            except httpx.HTTPError as exc:
                log.warning("[pharmasug-cn] 官方 API %d 年 -> %s (attempt %d)", year, exc, attempt + 1)
                time.sleep(2 * (attempt + 1))
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("[pharmasug-cn] 官方 API %d 年返回非 JSON", year)
            return []

        body = ""
        for rec in data.get("records", []):
            if rec.get("SUB_CATEGORY") == "PROCEEDINGS":
                body = rec.get("BODYTEXT") or ""
                break
        if not body:
            return []
        return self._parse_official_proceedings(body, year)

    def _parse_official_proceedings(self, body: str, year: int) -> list[Paper]:
        """解析官方 PROCEEDINGS 正文(兼容 2023-2026 各年格式)。

        条目锚点为 <b>编号.</b>,PDF 链接与标题可能出现在其前、后或包裹它的 <a> 中,
        且个别 <a> 未闭合(2026 DS173),故按"条目起点切分片段"逐段解析。
        解析前剥离 HTML 注释——官网用注释撤销论文链接(2026 LS192),注释内的链接不应收录。
        """
        body = re.sub(r"<!--.*?-->", " ", body, flags=re.DOTALL)

        # 顶部目录: section 代码 -> 官方名称
        section_names: dict[str, str] = {}
        for m in TOC_RE.finditer(body):
            code, name = m.group(1).upper(), m.group(2)
            if code in ("TOP",):
                continue
            name = re.sub(r"^\d+\s+", "", name).strip()  # "9 Coder's Corner" -> "Coder's Corner"
            name = re.sub(r"\s*\(" + code + r"\)\s*$", "", name, flags=re.IGNORECASE).strip()
            if name:
                section_names.setdefault(code, name)

        def clean_text(html: str) -> str:
            t = re.sub(r"<[^>]+>", " ", html)
            t = t.replace("&amp;", "&").replace("&nbsp;", " ")
            t = re.sub(r"\*+\s*BEST\s+PAPER\s*\*+", " ", t, flags=re.IGNORECASE)
            return re.sub(r"\s+", " ", t).strip()

        codes = list(CODE_RE.finditer(body))
        papers: list[Paper] = []
        for i, m in enumerate(codes):
            code = m.group(1).upper()
            section_code = re.match(r"[A-Z]+", code).group(0)
            seg_end = codes[i + 1].start() if i + 1 < len(codes) else len(body)
            seg = body[m.end(): seg_end]

            href = ""
            title_html = ""
            if re.match(r"\s*[^<]+</a\s*>", seg):
                # 2024: 锚点开在 <b> 之前(<a href=pdf><b>编号.</b>标题</a>),片段以 标题</a> 开头
                title_html = seg.split("<", 1)[0]
                prefix = body[max(0, m.start() - 300): m.start()]
                last_a = None
                for am in re.finditer(r"<a\b[^>]*>", prefix, re.IGNORECASE):
                    last_a = am
                if last_a is not None and "</a>" not in prefix[last_a.end():]:
                    hm = re.search(r'href=["\']?([^"\'>\s]+)', last_a.group(0), re.IGNORECASE)
                    if hm:
                        href = hm.group(1)
            else:
                # 找片段内指向 PDF 资源的锚点(忽略 Back to Top / #section 等导航链接)
                pdf_a = None
                for am in re.finditer(r"<a\b[^>]*>", seg, re.IGNORECASE):
                    hm = re.search(r'href=["\']?([^"\'>\s]+)', am.group(0), re.IGNORECASE)
                    if hm and (hm.group(1).lower().endswith(".pdf") or "/resources/" in hm.group(1)):
                        pdf_a = am
                        href = hm.group(1)
                        break
                if pdf_a is not None:
                    close_pos = seg.find("</a>", pdf_a.end())
                    if close_pos != -1:
                        title_html = seg[pdf_a.end(): close_pos]
                    else:
                        # 锚点未闭合(2026 DS173): 标题取到首个 <br
                        br_m = re.search(r"<br\b", seg[pdf_a.end():], re.IGNORECASE)
                        end = pdf_a.end() + br_m.start() if br_m else len(seg)
                        title_html = seg[pdf_a.end(): end]
                else:
                    # 无锚点条目(未提交版权/已撤销等): 纯文本标题
                    title_html = seg.split("<", 1)[0]
            pdf_url = href if (href.lower().endswith(".pdf") or "/resources/" in href) else ""

            title = clean_text(title_html)
            if not title or len(title) < 3:
                title = code

            # 作者: 标题之后按 <br 分块,取第一个有效文本行(跳过空行/BEST PAPER/Back to Top)
            after = seg[seg.find(title_html) + len(title_html):] if title_html in seg else seg
            authors: list[str] = []
            for part in re.split(r"<br\s*/?>", after, flags=re.IGNORECASE)[:4]:
                t = clean_text(part)
                if not t or "Back to Top" in t:
                    continue
                t = re.sub(r"^Author[s]?\s*[:：]\s*", "", t, flags=re.IGNORECASE).strip()
                if not t or len(t) < 3:
                    continue
                authors = [a.strip() for a in t.split(";") if a.strip()]
                break

            papers.append(self.make_paper(
                title=title,
                authors=authors,
                paper_code=f"PharmaSUG-CN-{year}-{code}",
                section_code=section_code,
                section_name=section_names.get(section_code) or SECTION_NAMES.get(section_code, section_code),
                year=year,
                pdf_url=pdf_url,
                source_url=_source_url(year),
            ))

        # 去重
        seen = set()
        unique = []
        for p in papers:
            if p.id not in seen:
                seen.add(p.id)
                unique.append(p)
        return unique

    def _scrape_lexjansen_wayback(self, year: int) -> list[Paper]:
        """通过 Wayback Machine 获取 lexjansen.com/pharmasug-cn/{year}/ 列表页。"""
        list_url = f"https://www.lexjansen.com/pharmasug-cn/{year}/"
        html = self.fetch_wayback(list_url)
        if not html:
            # 也试试 xsl_transform.php
            xsl_url = f"https://www.lexjansen.com/cgi-bin/xsl_transform.php?x=pharmasug-cn&year={year}"
            html = self.fetch_wayback(xsl_url)
        if not html:
            return []

        return self._parse_list_page(html, year, "lexjansen")

    def _scrape_pharmasug_org(self, year: int) -> list[Paper]:
        """直接访问 pharmasug.org/proceedings/china{year}/"""
        url = f"https://www.pharmasug.org/proceedings/china{year}/"
        html = self.fetch_html(url)
        if not html:
            # 试试 Wayback
            html = self.fetch_wayback(url)
        if not html:
            return []
        return self._parse_list_page(html, year, "pharmasug_org")

    def _scrape_cdx_pdfs(self, year: int) -> list[Paper]:
        """通过 CDX API 搜索 pharmasug-cn 的 PDF 直链。

        修复: 同时搜索 lexjansen.com 和 pharmasug.org 两个来源并合并,
        而非只在 lexjansen 无结果时才搜索 pharmasug.org。
        """
        # 搜索两个来源
        all_results: list[dict] = []

        # 来源 1: lexjansen.com
        pattern1 = f"www.lexjansen.com/pharmasug-cn/{year}/*"
        results1 = self.wayback_cdx_search(pattern1, limit=500)
        all_results.extend(results1)

        # 来源 2: pharmasug.org (始终搜索,不只在 lexjansen 无结果时)
        pattern2 = f"www.pharmasug.org/proceedings/china{year}/*"
        results2 = self.wayback_cdx_search(pattern2, limit=500)
        all_results.extend(results2)

        if not all_results:
            return []

        # 按 URL 去重 (保留 lexjansen 优先)
        seen_urls: set[str] = set()
        papers: list[Paper] = []
        seen_ids: set[str] = set()

        for r in all_results:
            original = r.get("original", "")
            timestamp = r.get("timestamp", "")
            if not original or not original.lower().endswith(".pdf"):
                continue

            url_key = original.lower().rstrip("/")
            if url_key in seen_urls:
                continue
            seen_urls.add(url_key)

            title, section_code, section_name, paper_code = self._extract_from_url(original, year)
            pdf_url = self.wayback_url(original, timestamp) if timestamp else original

            pid = Paper.make_id(self.conference, paper_code)
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            papers.append(self.make_paper(
                title=title,
                paper_code=paper_code,
                section_code=section_code,
                section_name=section_name,
                year=year,
                pdf_url=pdf_url,
                source_url=f"https://www.pharmasug.org/proceedings/china{year}/",
            ))
        return papers

    def _parse_list_page(self, html: str, year: int, source: str) -> list[Paper]:
        """解析列表页 HTML,提取论文信息。"""
        soup = self.soup(html)
        papers = []

        # 查找所有 PDF 链接
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.lower().endswith(".pdf"):
                continue

            # 匹配 pharmasug-cn 或 china 路径
            if "pharmasug-cn" not in href.lower() and "china" not in href.lower():
                continue

            # 构建完整 URL
            if source == "lexjansen":
                if href.startswith("/"):
                    pdf_url = f"https://www.lexjansen.com{href}"
                elif href.startswith("http"):
                    pdf_url = href
                else:
                    pdf_url = f"https://www.lexjansen.com/pharmasug-cn/{year}/{href}"
                # 如果是 Wayback 页面,需要用 Wayback URL
                # (fetch_wayback 返回的是原始内容,链接是原始 URL)
            else:  # pharmasug_org
                if href.startswith("/"):
                    pdf_url = f"https://www.pharmasug.org{href}"
                elif href.startswith("http"):
                    pdf_url = href
                else:
                    pdf_url = f"https://www.pharmasug.org/proceedings/china{year}/{href}"

            title = a.get_text(strip=True) or ""
            if not title or len(title) < 3:
                title, sc, sn, pc = self._extract_from_url(pdf_url, year)
            else:
                _, sc, sn, pc = self._extract_from_url(pdf_url, year)

            if not title:
                title = pc or "Untitled"

            papers.append(self.make_paper(
                title=title,
                paper_code=pc,
                section_code=sc,
                section_name=sn,
                year=year,
                pdf_url=pdf_url,
                source_url=f"https://www.lexjansen.com/pharmasug-cn/{year}/",
            ))

        # 去重
        seen = set()
        unique = []
        for p in papers:
            if p.id not in seen:
                seen.add(p.id)
                unique.append(p)
        return unique

    def _extract_from_url(self, url: str, year: int) -> tuple:
        """从 URL 中提取 section 代码、section 名称和论文编号。

        修复: 支持单字母编号 (d2, p1 等),避免 2012 年论文 ID 碰撞。
        修复: 使用 URL hash 作为兜底,确保每篇 PDF 有唯一 ID。
        修复: 从文件名生成可读标题,而非返回空字符串。
        """
        import hashlib

        # 从 URL 路径中提取 section (2-4 字母)
        section_code = ""
        path_parts = url.split("/")
        for part in path_parts:
            if re.match(r"^[A-Za-z]{2,4}$", part) and 2 <= len(part) <= 4:
                section_code = part.upper()
                break

        # 从文件名提取论文编号
        filename = url.rsplit("/", 1)[-1] if "/" in url else url
        filename = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)

        # 提取编号: AP10006, SP01, dv66, d2, p1 等
        # 模式 1: 2-4 字母 + 数字 (标准格式)
        code_match = re.search(r"(?:[-_])([A-Za-z]{2,4})(\d+)", filename)
        paper_code = ""
        if code_match:
            sc = code_match.group(1).upper()
            num = code_match.group(2)
            paper_code = f"PharmaSUG-CN-{year}-{sc}{num}"
            if not section_code:
                section_code = sc
        else:
            # 模式 2: 单字母 + 数字 (d2, p1, t3 等)
            code_match2 = re.search(r"(?:[-_])([a-zA-Z])(\d+)", filename)
            if code_match2:
                sc = code_match2.group(1).upper()
                num = code_match2.group(2)
                paper_code = f"PharmaSUG-CN-{year}-{sc}{num}"
                if not section_code:
                    section_code = sc
            else:
                # 模式 3: 无分隔符的 2-4 字母 + 数字 (如 SS03.pdf)
                code_match3 = re.search(r"([A-Za-z]{2,4})(\d+)", filename)
                if code_match3:
                    sc = code_match3.group(1).upper()
                    num = code_match3.group(2)
                    paper_code = f"PharmaSUG-CN-{year}-{sc}{num}"
                    if not section_code:
                        section_code = sc
                else:
                    # 模式 4: 纯数字编号 (如 PharmaSUG-China-2015-08.pdf)
                    num_match = re.search(r"[-_](\d+)$", filename)
                    if num_match:
                        num = num_match.group(1)
                        paper_code = f"PharmaSUG-CN-{year}-{num}"
                    else:
                        # 兜底: 使用 URL hash 确保唯一性 (不截断文件名)
                        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                        paper_code = f"PharmaSUG-CN-{year}-{url_hash}"

        section_name = SECTION_NAMES.get(section_code, section_code or "Other")

        # 从文件名生成可读标题 (而非空字符串)
        title = filename.replace("_", " ").replace("-", " ")
        title = re.sub(r"\s+", " ", title).strip()
        title = re.sub(r"^pharmasug\s*china\s*\d{4}\s*", "", title, flags=re.IGNORECASE)
        title = re.sub(r"^pharmasug\s*china\s*", "", title, flags=re.IGNORECASE)
        title = re.sub(r"^final\s*paper\s*", "", title, flags=re.IGNORECASE)
        if title:
            title = title[0].upper() + title[1:]
        if not title or len(title) < 3:
            # 兜底: 使用论文编号
            m = re.search(r"([A-Z]+)(\d+)", paper_code, re.IGNORECASE)
            title = f"{m.group(1).upper()}{m.group(2)}" if m else paper_code

        return title, section_code, section_name, paper_code
