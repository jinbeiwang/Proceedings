"""R/Medicine 会议 spider。

数据源: RConsortium 托管的 GitHub Pages 官网(域名规律):
  https://rconsortium.github.io/RMedicine_{YYYY}/Program.html
  日程为 gt 表格,内容格按 <br/> 分行:
    2024: 4 行 = "1A - Workshop" / 标题 / 作者 / 单位
    2025: 3 行 = "Demo" / 标题(<a> 链接 abstracts.html#anchor 或
          workshops.html#anchor) / "作者, 单位"
  摘要: abstracts.html / workshops.html 中带 id 的 section,
        与 Program 链接的 anchor 对应(2024 无逐篇摘要页)。

2024/2025 已验证存在;2023 及更早无 GitHub Pages 站。
"""
from __future__ import annotations

import re

from base import BaseSpider, log
from models import Paper

KNOWN_YEARS = (2024, 2025)

# 2025 行首的类型词(2024 的类型词跟在编号后)
_TYPE_WORDS = (
    "Keynote|Regular talk|Lightning Talk|Lightning talk|Demo|Workshop|"
    "Panel|Poster|Talk|Tutorial|Invited|Plenary|Intro|Welcome Back|Panel Discussion"
)
_TYPE_LINE_RE = re.compile(rf"^\s*({_TYPE_WORDS})\s*$", re.I)
_TYPE_LINE_RE_LOOSE = re.compile(rf"^\s*({_TYPE_WORDS})\b", re.I)
_NUM_TYPE_RE = re.compile(r"^\s*(\d+[A-Z]?)\s*[-–]\s*(.+?)\s*$")


class RMedicineSpider(BaseSpider):
    conference = "r-medicine"
    base_url = "https://rconsortium.github.io"
    rate_limit = 1.0

    def collect(self) -> list[Paper]:
        papers: list[Paper] = []
        for year in self.candidate_years():
            papers.extend(self._collect_year(year))
        log.info("[r-medicine] 共 %d 条", len(papers))
        return papers

    def candidate_years(self) -> list[int]:
        from datetime import date
        years = list(KNOWN_YEARS)
        for y in range(max(KNOWN_YEARS) + 1, date.today().year + 1):
            years.append(y)
        return years

    def _collect_year(self, year: int) -> list[Paper]:
        site = f"https://rconsortium.github.io/RMedicine_{year}/"
        prog_url = site + "Program.html"
        html = self.fetch_html(prog_url)
        if not html:
            log.info("[r-medicine] %d 年无 Program 页,跳过", year)
            return []
        abstracts = self._load_abstracts(site)

        soup = self.soup(html)
        papers: list[Paper] = []
        seen_keys: set[str] = set()
        for ti, table in enumerate(soup.find_all("table")):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 4:
                    continue
                last = cells[-1]
                lines = [l.strip() for l in last.get_text("\n").split("\n") if l.strip()]
                if len(lines) < 2 or len(" ".join(lines)) < 10:
                    continue

                # 行1: "1A - Workshop"(2024) 或 "Demo"(2025)
                code, talk_type, typed = _parse_first_line(lines[0])
                rest = lines[1:] if typed else lines
                if not rest:
                    continue
                title = rest[0]
                if not title or len(title) < 4:
                    continue

                authors = _parse_authors(rest[1:], style4=code != "")

                # anchor -> 摘要 + 稳定 paper_code
                anchor = ""
                link = last.find("a", href=True)
                if link:
                    m = re.search(r"#(.+)$", link["href"])
                    if m:
                        anchor = m.group(1)
                abstract = _find_abstract(abstracts, anchor, title)

                # paper_code 全局唯一: 年前缀 + 表序号/锚点/标题 slug
                # (2024 各天表格的行编号会重复,须加表序号;
                #  2025 容器级锚点如 #keynote-addresses 被多行共用,须消歧)
                if code:
                    key = f"t{ti + 1}-{code}"
                elif anchor:
                    key = anchor[:60]
                else:
                    key = _slug(title)[:40]
                if key in seen_keys:
                    base = f"{key}-{_slug(title)[:20]}"
                    alt, n = base, 2
                    while alt in seen_keys:
                        alt = f"{base}-{n}"
                        n += 1
                    key = alt
                seen_keys.add(key)
                papers.append(self.make_paper(
                    title=title,
                    authors=authors,
                    year=year,
                    section_code=_type_code(talk_type),
                    section_name=_norm_type(talk_type),
                    paper_code=f"RMed-{year}-{key}",
                    pdf_url="",
                    source_url=prog_url,
                    abstract=abstract[:2000],
                ))
        log.info("[r-medicine] %d 年 %d 条", year, len(papers))
        return papers

    def _load_abstracts(self, site: str) -> dict[str, str]:
        """abstracts.html / workshops.html 中带 id 的 section -> 文本。

        优先取最内层同名 id(外层容器包含整页目录)。
        """
        out: dict[str, str] = {}
        for page in ("abstracts.html", "workshops.html", "Abstracts.html"):
            html = self.fetch_html(site + page)
            if not html:
                continue
            soup = self.soup(html)
            for sec in soup.find_all("section", id=True):
                sid = sec.get("id", "")
                if not sid or len(sid) < 4:
                    continue
                # 跳过整页级容器
                parent_sec = sec.find_parent("section")
                text = _clean(sec.get_text(" ", strip=True))
                if not text or len(text) < 60:
                    continue
                if sid not in out or len(text) < len(out[sid]):
                    out[sid] = text
        return out


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _find_abstract(abstracts: dict[str, str], anchor: str, title: str) -> str:
    """锚点精确 -> 前缀 -> 标题 slug 兜底;取候选中最短文本(避免容器级 section)。"""
    cands: list[str] = []
    if anchor:
        if anchor in abstracts:
            cands.append(abstracts[anchor])
        else:
            for sid, txt in abstracts.items():
                if sid.startswith(anchor) or anchor.startswith(sid):
                    cands.append(txt)
    if not cands:
        tslug = _slug(title)
        for sid, txt in abstracts.items():
            sslug = _slug(sid)
            if sslug and (tslug.startswith(sslug) or sslug.startswith(tslug[:20])):
                cands.append(txt)
    return min(cands, key=len) if cands else ""


_TYPE_CANON = {
    "regular talk": "Regular talk", "lightning talk": "Lightning Talk",
    "demo": "Demo", "workshop": "Workshop", "keynote": "Keynote",
    "panel": "Panel", "panel discussion": "Panel",
    "poster": "Poster", "talk": "Talk", "tutorial": "Tutorial",
    "plenary": "Plenary", "intro": "Intro", "welcome back": "Intro",
    "closing remarks": "Closing", "contest winner": "Contest Winner",
}


def _norm_type(talk_type: str) -> str:
    return _TYPE_CANON.get((talk_type or "").strip().lower(), (talk_type or "Talk").strip())


def _parse_first_line(line: str) -> tuple[str, str, bool]:
    """行1 -> (编号代码, 类型词, 是否类型行)。"""
    m = _NUM_TYPE_RE.match(line)
    if m:
        return m.group(1), m.group(2).strip(), True
    m2 = _TYPE_LINE_RE.match(line)
    if m2:
        return "", m2.group(1).strip(), True
    return "", "", False


def _parse_authors(rest: list[str], style4: bool) -> list[str]:
    """剩余行 -> 作者列表。

    style4=True(2024): rest = [作者(纯人名, 逗号分隔), 单位, ...]
    style4=False(2025): rest = ["人名[, 单位]", ...] 一或多个混排行
    """
    if not rest:
        return []
    if style4:
        names = [p.strip() for p in re.split(r"[,;]", rest[0]) if p.strip()]
        aff = rest[1].strip() if len(rest) > 1 else ""
        return [f"{n} ({aff})" if aff else n for n in names]
    # 2025: 每行 "Name & Name, Affiliation"
    authors: list[str] = []
    for line in rest:
        line = line.strip()
        if not line:
            continue
        name_part, _, aff = line.partition(",")
        aff = aff.strip()
        for name in re.split(r"\s+&\s+|\s+and\s+", name_part):
            name = name.strip()
            if not name:
                continue
            authors.append(f"{name} ({aff})" if aff else name)
    return authors


def _type_code(talk_type: str) -> str:
    mapping = {
        "Keynote": "KN", "Demo": "DM", "Workshop": "WS", "Panel": "PN",
        "Poster": "PO", "Tutorial": "TU", "Plenary": "PL",
        "Regular talk": "TK", "Lightning Talk": "LT", "Lightning talk": "LT",
        "Talk": "TK", "Intro": "IN", "Welcome Back": "IN",
        "Panel Discussion": "PN",
    }
    return mapping.get(talk_type, "TK")
