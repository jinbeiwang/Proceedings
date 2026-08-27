"""useR! (The R User Conference) 演讲 spider。

数据源: 各届官网(域名规律 user{YYYY}.r-project.org):
  - 2025: https://user2025.r-project.org/program/in-person/ 与 /program/virtual/
    页面为 Quarto + gt 表格。单元格内容以 base64 编码藏在
    span[data-qmd-base64] 属性里,解码后即标题/摘要/演讲者 HTML。
    分组名(如 Morning tutorial)记录在 td 的 headers 属性前缀
    (注意: headers 是 HTML 多值属性,bs4 返回列表,需 join)。
  - 2022: https://user2022.r-project.org/program/talks/
    h3 标题格式 "演讲者 - 标题"(keynote/邀请报告),
    普通报告同格式 + 可选 "Speakers:"/"Co-authors:" 段落;
    h2 为日期+场次头,块边界为下一个 h3 或 h2;
    "Presentation: URL" 段落给讲义链接。
2024(Sheffield 域名)与 2023 当前 DNS 不可解析、2026 program 未发布,
 YEARS 表可随官网扩展手动追加。
"""
from __future__ import annotations

import base64
import re

from base import BaseSpider, log
from models import Paper

# 非演讲行(休息/餐饮/注册/会务公告)
_SKIP_TITLE = re.compile(
    r"(coffee|break|lunch|registration|networking|welcome reception|poster\s+session\s*booths?$"
    r"|enjoy some|sponsor|closing|^suggestion:|^head to|^heavy hors|nasher museum"
    r"|welcome reception)", re.I)


def _is_adjacent(a, b) -> bool:
    """b 是否紧跟在 a 之后(同为兄弟节点且中间无其他元素)。"""
    prev = b.find_previous_sibling()
    while prev is not None and getattr(prev, "name", None) is None:
        prev = prev.find_previous_sibling() if hasattr(prev, "find_previous_sibling") else None
    return prev is a


class UserConfSpider(BaseSpider):
    conference = "user-r"
    base_url = "https://user2025.r-project.org"
    rate_limit = 1.0

    # 年份 -> 日程页列表(抓取时逐页探测,失效页跳过)
    YEARS: dict[int, list[str]] = {
        2022: ["https://user2022.r-project.org/program/talks/"],
        2025: [
            "https://user2025.r-project.org/program/in-person/",
            "https://user2025.r-project.org/program/virtual/",
        ],
    }

    def collect(self) -> list[Paper]:
        papers: list[Paper] = []
        for year, pages in sorted(self.YEARS.items()):
            for page in pages:
                if year == 2025:
                    papers.extend(self._collect_2025_page(page, year))
                else:
                    papers.extend(self._collect_h3_page(page, year))
        log.info("[user-r] 共 %d 条", len(papers))
        return papers

    # ---- 2025: gt 表格 + base64 ----
    def _collect_2025_page(self, url: str, year: int) -> list[Paper]:
        html = self.fetch_html(url)
        if not html:
            return []
        soup = self.soup(html)
        papers: list[Paper] = []
        seq = 0
        # virtual 页单独编号(V 前缀),避免与 in-person 页 paper_code 撞车
        vtag = "V" if "/virtual/" in url else ""
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 4:
                    continue
                title_cell, pres_cell = cells[2], cells[3]
                title, abstract = _decode_title_cell(title_cell)
                presenters_raw = _decode_plain(pres_cell)
                if not title or _SKIP_TITLE.search(title):
                    continue
                if not presenters_raw:
                    continue  # 休息/餐饮行无演讲者
                section = _rowgroup(cells[2])
                seq += 1
                papers.append(self.make_paper(
                    title=title,
                    authors=_parse_presenters(presenters_raw),
                    year=year,
                    section_code=_section_code(section),
                    section_name=section,
                    paper_code=f"useR-{year}-{vtag}{seq:03d}",
                    pdf_url="",
                    source_url=url,
                    abstract=abstract,
                ))
        log.info("[user-r] %s -> %d 条", url, len(papers))
        return papers

    # ---- 2022: h3 "作者 - 标题" + 段落 ----
    def _collect_h3_page(self, url: str, year: int) -> list[Paper]:
        html = self.fetch_html(url)
        if not html:
            return []
        soup = self.soup(html)
        papers: list[Paper] = []
        seq = 0
        h3s = soup.find_all("h3")

        # h2 会话头 -> 每个谈话取最近的前置 h2 作 section
        def prev_h2(el):
            node = el
            while node is not None:
                prev = node.find_previous_sibling()
                if prev is None:
                    node = node.parent
                    if node is None or getattr(node, "name", None) in ("body", "[document]"):
                        return ""
                    continue
                if getattr(prev, "name", None) == "h2":
                    return _clean_title(prev.get_text(" ", strip=True))
                node = prev
            return ""

        # 相邻 h3(中间无内容元素)= 同一标题被拆成多段,分组拼接
        groups: list[list] = []
        for h3 in h3s:
            if groups and _is_adjacent(groups[-1][-1], h3):
                groups[-1].append(h3)
            else:
                groups.append([h3])

        for group in groups:
            title_full = _clean_title(" ".join(
                h.get_text(" ", strip=True) for h in group))
            h3 = group[-1]  # 内容块挂在组内最后一个 h3 之后
            # 块 = 该 h3 到下一个 h3/h2 之间的兄弟节点
            block = []
            node = h3
            while True:
                node = node.find_next_sibling()
                name = getattr(node, "name", None)
                if node is None or name in ("h3", "h2"):
                    break
                if name:
                    block.append(node)

            speakers, coauthors, abstract_parts, pres_url = "", [], [], ""
            for el in block:
                txt = el.get_text(" ", strip=True)
                m = re.match(r"^Speakers?:\s*(.+)$", txt, re.I)
                m2 = re.match(r"^Co-authors?:\s*(.+)$", txt, re.I)
                mp = re.match(r"^Presentation:\s*(\S+)$", txt, re.I)
                if m:
                    speakers = m.group(1)
                elif m2:
                    coauthors = _parse_presenters(m2.group(1))
                elif mp:
                    pres_url = mp.group(1)
                elif re.match(r"^Session chair:", txt, re.I):
                    continue
                elif re.match(r"^https?://\S+$", txt):
                    continue  # 裸链接(包主页/仓库)不入摘要
                else:
                    abstract_parts.append(txt)

            # "作者 - 标题": 取首个 " - " 分隔
            head, _, rest = title_full.partition(" - ")
            if rest and (speakers or re.match(r"^[A-Z]", head)):
                title, primary = _clean_title(rest), head
            else:
                title, primary = title_full, ""

            if not title or len(title) < 8 or _SKIP_TITLE.search(title):
                continue
            authors = _parse_presenters(speakers) if speakers else (
                [primary] if primary else [])
            authors = authors + [a for a in coauthors if a not in authors]
            if not authors:
                continue
            seq += 1
            papers.append(self.make_paper(
                title=title,
                authors=authors,
                year=year,
                section_code="KN" if any(
                    re.match(r"^Session chair:", el.get_text(" ", strip=True), re.I)
                    for el in block) else "TK",
                section_name=prev_h2(h3) or "Conference Talk",
                paper_code=f"useR-{year}-{seq:03d}",
                pdf_url=pres_url if pres_url.startswith("http") else "",
                source_url=url,
                abstract=" ".join(abstract_parts)[:2000],
            ))
        log.info("[user-r] %s -> %d 条", url, len(papers))
        return papers


# ---- 解析辅助 ----

def _decode_base64_attr(cell):
    el = cell.find(attrs={"data-qmd-base64": True})
    if not el:
        return ""
    try:
        return base64.b64decode(el["data-qmd-base64"]).decode("utf-8", "replace")
    except Exception:
        return ""


def _decode_title_cell(cell) -> tuple[str, str]:
    """gt 标题单元格 -> (标题, 摘要)。"""
    decoded = _decode_base64_attr(cell)
    if not decoded:
        return "", ""
    # 摘要在 <details><summary>More info</summary> 之后
    abstract = ""
    m = re.search(r"<summary>[^<]*</summary>(.*?)(?:</details>|$)", decoded, re.S | re.I)
    if m:
        abstract = _strip_tags(m.group(1))
    # 标题: 首个 <a> 或 details 前的全部文本
    head = re.split(r"<details", decoded, flags=re.I)[0]
    title = _strip_tags(head)
    return _clean_title(title), abstract[:2000]


def _decode_plain(cell) -> str:
    decoded = _decode_base64_attr(cell)
    if decoded:
        return _strip_tags(decoded)
    return cell.get_text(" ", strip=True)


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _clean_title(s: str) -> str:
    s = re.sub(r"[*`]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _rowgroup(cell) -> str:
    """td headers 属性前缀 = 行分组名,如 'Morning tutorial (...) stub_1_2 info'。

    headers 为 HTML 多值属性,bs4 get() 可能返回列表(AttributeValueList)。
    """
    h = cell.get("headers", "") or ""
    if isinstance(h, (list, tuple)):
        h = " ".join(str(x) for x in h)
    section = h.split(" stub_")[0].strip()
    # 去掉括号内的时段说明
    section = re.sub(r"\s*\(.*?\)\s*", " ", section)
    return _clean_title(section) or "Talk"


def _parse_presenters(raw: str) -> list[str]:
    """'Malcolm Barrett (Stanford University), Jane Doe (Acme)' -> 名字列表。"""
    if not raw:
        return []
    out = []
    for part in re.split(r"[;,]", raw):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", part)
        if m:
            out.append(f"{m.group(1).strip()} ({m.group(2).strip()})")
        else:
            out.append(part)
    return out


def _section_code(section: str) -> str:
    low = (section or "").lower()
    if "tutorial" in low:
        return "WS"
    if "keynote" in low:
        return "KN"
    if "poster" in low:
        return "PO"
    if "virtual" in low or "online" in low:
        return "VT"
    return "TK"
