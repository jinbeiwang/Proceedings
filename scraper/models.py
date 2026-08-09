"""统一论文数据模型与会议元数据定义。

所有 spider 输出 Paper 对象列表，由 main.py 汇总为 JSON 供静态站点消费。
字段设计参考 clinyun.com/ppi 与 lexjansen 的索引维度。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Paper:
    """单篇会议论文的标准化记录。"""

    id: str                            # 唯一键: {conference}-{paper_code}
    title: str
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    conference: str = ""               # 会议代码,如 pharmasug-us
    conference_name: str = ""          # 展示名,如 PharmaSUG US
    section_code: str = ""             # section 代码,如 AP
    section_name: str = ""             # section 名,如 Advanced Programming
    paper_code: str = ""               # 原始编号,如 PharmaSUG-2025-AP-002
    pdf_url: str = ""                  # PDF 直链(绝对 URL)
    source_url: str = ""               # 发现该论文的索引页
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    lang: str = "en"                   # en / zh / ja
    region: str = ""                   # US / EU / CN / JP / APAC / Global
    added_at: str = ""                 # ISO8601 抓取时间

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def make_id(conference: str, paper_code: str) -> str:
        """生成稳定唯一键。"""
        return f"{conference}-{paper_code}".upper().replace(" ", "")


# 会议注册表:代码 -> 元数据。新增会议只需在此登记并实现对应 spider。
CONFERENCES: dict[str, dict] = {
    "pharmasug-us":    {"name": "PharmaSUG US",          "region": "US",    "lang": "en", "start": 1997},
    "pharmasug-cn":    {"name": "PharmaSUG China",       "region": "CN",    "lang": "zh", "start": 2012},
    "pharmasug-jp":    {"name": "PharmaSUG Japan",       "region": "JP",    "lang": "ja", "start": 2018},
    "phuse-eu":        {"name": "PHUSE EU Connect",      "region": "EU",    "lang": "en", "start": 2005},
    "phuse-us":        {"name": "PHUSE US Connect",      "region": "US",    "lang": "en", "start": 2018},
    "phuse-apac":      {"name": "PHUSE APAC Connect",    "region": "APAC",  "lang": "en", "start": 2026},
    "phuse-css":       {"name": "FDA/PHUSE CSS",         "region": "US",    "lang": "en", "start": 2012},
    "r-pharma":        {"name": "R/Pharma",              "region": "Global","lang": "en", "start": 2018},
    "sgf":             {"name": "SAS Global Forum",      "region": "Global","lang": "en", "start": 2007},
    "sugi":            {"name": "SUGI",                  "region": "Global","lang": "en", "start": 1976},
    "wuss":            {"name": "WUSS",                  "region": "US",    "lang": "en", "start": 1993},
    "sesug":           {"name": "SESUG",                 "region": "US",    "lang": "en", "start": 1993},
    "nesug":           {"name": "NESUG",                 "region": "US",    "lang": "en", "start": 1988},
    "mwsug":           {"name": "MWSUG",                 "region": "US",    "lang": "en", "start": 1990},
    "scsug":           {"name": "SCSUG",                 "region": "US",    "lang": "en", "start": 1991},
    "seugi":           {"name": "SEUGI",                 "region": "EU",    "lang": "en", "start": 1983},
    "basug":           {"name": "BASUG",                 "region": "US",    "lang": "en", "start": 1983},
    "pnwsug":          {"name": "PNWSUG",                "region": "US",    "lang": "en", "start": 1996},
    "psi":             {"name": "PSI",                   "region": "EU",    "lang": "en", "start": 2024},
    "posit-conf":      {"name": "posit::conf",           "region": "Global","lang": "en", "start": 2023},
    "sas-explore":     {"name": "SAS Explore",           "region": "Global","lang": "en", "start": 2022},
    "sas-innovate":    {"name": "SAS Innovate",          "region": "Global","lang": "en", "start": 2024},
    "pharmarug-cn":    {"name": "PharmaRUG China",       "region": "CN",    "lang": "zh", "start": 2023},
    "views":           {"name": "VIEWS",                 "region": "EU",    "lang": "en", "start": 2001},
}

# CRG test: add a comment

