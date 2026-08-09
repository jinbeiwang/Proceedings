"""R/Pharma proceedings spider。

数据源: rinpharma/data-pipelines 项目通过 GitHub Pages 发布的结构化 CSV。
  - CSV 直链: https://rinpharma.github.io/data-pipelines/output/processed_talks.csv
  - 覆盖 2018–2025 全部年份,622+ 条演讲记录
  - 字段: ID, Event, Abstract, Type, APAC, Year, Date, Start, End,
          Speaker, Affiliation, Title, Slides, Video, Abstract_Sanitzed, Missing_Content

本 spider 下载 CSV 并解析为 Paper 对象。Slides 字段提供 GitHub PDF 直链。
"""
from __future__ import annotations

import csv
import io
import re

from base import BaseSpider, log
from models import Paper


class RPharmaSpider(BaseSpider):
    conference = "r-pharma"
    base_url = "https://rinpharma.com"
    rate_limit = 1.0

    CSV_URL = "https://rinpharma.github.io/data-pipelines/output/processed_talks.csv"

    def collect(self) -> list[Paper]:
        log.info("[r-pharma] 下载演讲数据 CSV -> %s", self.CSV_URL)
        try:
            resp = self._client.get(self.CSV_URL, timeout=30.0)
            if resp.status_code != 200:
                log.warning("[r-pharma] CSV 下载失败: HTTP %s", resp.status_code)
                return []
        except Exception as exc:
            log.warning("[r-pharma] CSV 下载异常: %s", exc)
            return []

        papers: list[Paper] = []
        reader = csv.DictReader(io.StringIO(resp.text))

        for row in reader:
            title = (row.get("Title") or "").strip()
            if not title:
                continue

            year_str = (row.get("Year") or "").strip()
            try:
                year = int(year_str)
            except ValueError:
                continue

            # 演讲类型作为 section
            section_name = (row.get("Type") or "Talk").strip()
            section_code = _type_to_code(section_name)

            # 演讲者(多位用 " | " 分隔)
            speakers_raw = (row.get("Speaker") or "").strip()
            authors = [a.strip() for a in re.split(r"\s*\|\s*", speakers_raw) if a.strip()]

            # PDF/Slides 链接
            slides_url = (row.get("Slides") or "").strip()
            pdf_url = slides_url if slides_url and slides_url != "NA" else ""

            # 如果 Slides 是 GitHub blob 链接,转为 raw 链接以便直接下载
            if pdf_url and "github.com" in pdf_url and "/blob/" in pdf_url:
                pdf_url = pdf_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

            # 视频链接作为备用
            video_url = (row.get("Video") or "").strip()
            if video_url and video_url != "NA" and not pdf_url:
                pdf_url = video_url  # 退化为视频链接

            # 论文编号
            talk_id = (row.get("ID") or "").strip()
            paper_code = f"RPharma-{year}-{talk_id}" if talk_id else f"RPharma-{year}-{len(papers)+1:03d}"

            # 摘要
            abstract = (row.get("Abstract_Sanitzed") or row.get("Abstract") or "").strip()
            if abstract == "NA":
                abstract = ""

            papers.append(
                self.make_paper(
                    title=title,
                    authors=authors,
                    year=year,
                    section_code=section_code,
                    section_name=section_name,
                    paper_code=paper_code,
                    pdf_url=pdf_url,
                    source_url=self.CSV_URL,
                    abstract=abstract,
                )
            )

        log.info("[r-pharma] 共 %d 篇", len(papers))
        return papers


def _type_to_code(type_name: str) -> str:
    """将演讲类型映射为简短代码。"""
    mapping = {
        "Keynote": "KN",
        "Talk": "TK",
        "Workshop": "WS",
        "Panel": "PN",
        "Remarks": "RM",
        "On-Demand": "OD",
        "Schedule only": "SC",
        "Coffee session": "CF",
    }
    return mapping.get(type_name, "TK")
