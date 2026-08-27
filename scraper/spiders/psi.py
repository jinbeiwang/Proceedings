"""PSI (Statisticians in the Pharmaceutical Industry) 会议摘要 spider。

数据源: psiweb.org 官网 past-conferences 下的 individual abstracts 页。
  - 2026: /conferences/past-conferences/2026-conference-sessions/individual-abstracts-2026 (单页)
  - 2025: /conferences/past-conferences/2025-conference-sessions/individual-abstracts/{1,2} (分页)
  - 2024 及更早: 无 individual abstracts 页(404),仅会员可见的 session slides

页面为 Telerik Sitefinity CMS 静态 HTML,列表为一张表格:
  每行第 1 格含两个链接 [详情页, PDF 直链]。
真实标题/作者不在列表页,而在 PDF 首页文本中:
  首行=摘要编号,随后标题(可跨行),再后作者行(含上标单位号),
  最后 "1Org, City. 2Org..." 单位行。
本 spider 下载每个 PDF 提取标题与作者(带 JSON 缓存,幂等)。
"""
from __future__ import annotations

import hashlib
import io
import json
import re

import httpx

from base import BaseSpider, log
from models import Paper

# 列表页 URL 模板: 尝试两种已知格式,404/空页自动跳过
PAGE_PATTERNS = {
    "new": "https://www.psiweb.org/conferences/past-conferences/{year}-conference-sessions/individual-abstracts-{year}",
    "paged": "https://www.psiweb.org/conferences/past-conferences/{year}-conference-sessions/individual-abstracts/{n}",
}

KNOWN_YEARS = (2025, 2026)


class PSISpider(BaseSpider):
    conference = "psi"
    base_url = "https://www.psiweb.org"
    rate_limit = 0.6

    def collect(self) -> list[Paper]:
        papers: list[Paper] = []
        for year in self.candidate_years():
            papers.extend(self._collect_year(year))
        log.info("[psi] 共 %d 篇", len(papers))
        return papers

    def candidate_years(self) -> list[int]:
        """已知年份 + 顺延探测(2027 起若页面出现自动纳入)。"""
        from datetime import date
        years = list(KNOWN_YEARS)
        for y in range(max(KNOWN_YEARS) + 1, date.today().year + 2):
            years.append(y)
        return years

    def _collect_year(self, year: int) -> list[Paper]:
        entries: list[dict] = []
        # 格式 1: individual-abstracts-{year} 单页
        url = PAGE_PATTERNS["new"].format(year=year)
        entries = self._parse_list_page(url, year)
        # 格式 2: 分页 /individual-abstracts/{n}
        if not entries:
            for n in range(1, 6):
                purl = PAGE_PATTERNS["paged"].format(year=year, n=n)
                found = self._parse_list_page(purl, year)
                if not found:
                    break
                entries.extend(found)
        if not entries:
            log.info("[psi] %d 年无 abstracts 页(跳过)", year)
            return []

        papers: list[Paper] = []
        for e in entries:
            title, authors = self._title_authors_from_pdf(e["pdf_url"], year, e["code"])
            if not title:
                continue  # 列表页仅有文件名,PDF 不可解析时宁缺毋滥
            papers.append(self.make_paper(
                title=title,
                authors=authors,
                year=year,
                section_code=e["section_code"],
                section_name=e["section_name"],
                paper_code=f"PSI-{year}-{e['code']}",
                pdf_url=e["pdf_url"],
                source_url=e["detail_url"],
            ))
        log.info("[psi] %d 年 %d 篇(列表 %d 条)", year, len(papers), len(entries))
        return papers

    def _parse_list_page(self, url: str, year: int) -> list[dict]:
        html = self.fetch_html(url)
        if not html:
            return []
        soup = self.soup(html)
        out: list[dict] = []
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                links = [a for a in row.find_all("a", href=True) if a.get("href")]
                if len(links) < 2:
                    continue
                detail = self.absurl(links[0]["href"])
                pdf = self.absurl(links[-1]["href"])
                if ".pdf" not in pdf.lower():
                    continue
                code = pdf.rsplit("/", 1)[-1].split(".pdf")[0]
                out.append({
                    "code": code,
                    "pdf_url": pdf,
                    "detail_url": detail,
                    "section_code": _section_code(code),
                    "section_name": _section_name(code),
                })
        return out

    # ---- PDF 标题/作者提取(带磁盘缓存,幂等) ----
    def _title_authors_from_pdf(self, pdf_url: str, year: int, code: str) -> tuple[str, list[str]]:
        cache = None
        if self.cache_dir:
            h = hashlib.md5(pdf_url.encode()).hexdigest()
            cache = self.cache_dir / f"psi_pdf_{h}.json"
            if cache.exists():
                try:
                    d = json.loads(cache.read_text(encoding="utf-8"))
                    return d.get("title", ""), d.get("authors", [])
                except (json.JSONDecodeError, OSError):
                    pass

        title, authors = "", []
        text = self._pdf_first_page(pdf_url)
        if text:
            title, authors = _parse_abstract_pdf(text)
        if not title:
            # 兜底: 2026 文件名即标题
            title = _title_from_code(code)

        if cache and title:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(
                    json.dumps({"title": title, "authors": authors}, ensure_ascii=False),
                    encoding="utf-8")
            except OSError:
                pass
        return title, authors

    def _pdf_first_page(self, pdf_url: str) -> str:
        self._throttle()
        data = b""
        for attempt in range(2):
            try:
                resp = self._client.get(pdf_url, timeout=45.0)
                data = resp.content
                break
            except httpx.HTTPError:
                if attempt == 0:
                    import time
                    time.sleep(1.5)
        try:
            if not data.startswith(b"%PDF"):
                return ""
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data), strict=False)
            if not reader.pages:
                return ""
            return reader.pages[0].extract_text() or ""
        except Exception:
            return ""


# ---- 解析辅助 ----

_LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl"}


def _clean_line(ln: str) -> str:
    ln = re.sub(r"\s+", " ", ln).strip()
    for k, v in _LIGATURES.items():
        ln = ln.replace(k, v)
    return ln


def _looks_like_authors(ln: str) -> bool:
    """作者行: 'Name1,2, Name2 Org-less1' —— 逗号分段后多为 '人名+可选数字'。"""
    parts = [p.strip() for p in ln.split(",") if p.strip()]
    if len(parts) < 2:
        return False
    name_like = sum(1 for p in parts
                    if re.fullmatch(r"[A-Z][\w'’.-]*( [\w'’.-]+)*\d*", p)
                    or p.isdigit())
    return name_like >= max(2, len(parts) - 1)


def _parse_abstract_pdf(text: str) -> tuple[str, list[str]]:
    """从 PSI 摘要 PDF 首页文本解析 (标题, 作者)。"""
    lines = [_clean_line(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return "", []
    # 丢弃首行纯编号
    if re.fullmatch(r"\d{1,4}", lines[0]):
        lines = lines[1:]

    title_lines: list[str] = []
    authors_raw = ""
    i = 0
    while i < len(lines):
        ln = lines[i]
        if title_lines and _looks_like_authors(ln):
            authors_raw = ln
            i += 1
            break
        # 单位行 "1Novo Nordisk A/S..." / 传记段落 -> 截断
        if title_lines and re.match(r"^\d+[A-Z]", ln):
            break
        if title_lines and re.match(r"^(Please provide|Biography|Presenting author)", ln, re.I):
            break
        title_lines.append(ln)
        i += 1
        if len(title_lines) >= 6:
            break

    title = " ".join(title_lines).strip()
    if len(title) < 10:
        return "", []
    if re.match(r"^error (creating|while)", title, re.I):
        return "", []  # 服务端 PDF 生成失败的错误文本
    # 清理 2026 PDF 首页的 "15 June 11:00 Title:" 前缀
    title = re.sub(r"^\d{1,2}\s+\w+\s+\d{1,2}[:.]\d{2}\s+Title:\s*", "", title, flags=re.I)
    title = re.sub(r"^Title:\s*", "", title, flags=re.I)
    # 修复 pypdf 空格伪影: "Dose -Finding" -> "Dose-Finding"
    title = re.sub(r"(\S) -(\S)", r"\1-\2", title)
    title = re.sub(r"\s+([.,;:])", r"\1", title)
    authors = _split_authors(authors_raw)
    return title, authors


def _split_authors(raw: str) -> list[str]:
    """'Name1,2,3, Name3' -> ['Name', 'Name'](合并数字段,去上标号)。"""
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    merged: list[str] = []
    for p in parts:
        if p.isdigit() and merged:
            continue  # 上标单位号并入前一个名字,不单列
        merged.append(p)
    out = []
    for m in merged:
        m = re.sub(r"\d+$", "", m).strip()  # 去尾部上标号
        if m and len(m) >= 3:
            out.append(m)
    return out


def _title_from_code(code: str) -> str:
    """2026 文件名即标题: '15_june_1100_boin_vs_blrm_...' -> 可读标题。"""
    if re.match(r"^[a-z]?\d+-?abstract", code, re.I) or "-" in code and "_" not in code:
        return ""  # 't003-abstract-42' 类纯编号文件名不可读
    parts = code.split("_")
    # 丢弃前缀: 日_月_时间
    if len(parts) >= 3 and re.fullmatch(r"\d{1,2}", parts[0]) and parts[1].lower() in (
            "january", "february", "march", "april", "may", "june", "july",
            "august", "september", "october", "november", "december"):
        parts = parts[3:]
    if len(parts) < 2:
        return ""
    title = " ".join(parts).strip()
    return title if len(title) >= 10 else ""


def _section_code(code: str) -> str:
    m = re.match(r"^([A-Za-z]+)", code)
    return m.group(1).upper() if m else "AB"


def _section_name(code: str) -> str:
    prefix = _section_code(code)
    mapping = {
        "O": "Oral Presentation",
        "P": "Poster",
        "CYS": "Contributed Young Statistician",
        "IP": "Invited Presentation",
        "SP": "Sponsored Presentation",
        "PP": "Poster Pitch",
    }
    if prefix in mapping:
        return mapping[prefix]
    # 2026+: 文件名以日期开头,无类型前缀
    if re.match(r"^\d", code):
        return "Individual Abstract"
    return "Abstract"
