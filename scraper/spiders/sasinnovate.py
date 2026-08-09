"""SAS Innovate proceedings spider(SGF 2021 后的继任会议,2025 起)。

资料托管在 GitHub,每年一个组织,每个仓库对应一场 session(2026-08 实地核实):
  - 2025: https://github.com/SAS-Innovate-2025  (30 个仓库,Hands-On 实验为主,无 PDF)
  - 2026: https://github.com/SASInnovate2026    (46 个仓库,README + 演示 PDF + 代码)

仓库 README 结构(2026):
  # 标题
  摘要段落…
  # Session Information
  Format: HOW / 时长 / Presented By: 姓名, 职务, 单位

提取:title(H1)/abstract(首段)/authors(Presented By 行)/section(Format)/
pdf_url(根目录首个 .pdf 的 GitHub 链接)/source_url(仓库主页)。
2025 仓库 README 无 Presented By,authors 留空(contributors 是仓库维护者,
并非讲者,不作数)。
"""
from __future__ import annotations

import base64
import json
import os
import re
import time

from base import BaseSpider, log
from models import Paper

# 年份 -> GitHub 组织名(命名不规律,逐年登记)
ORGS: dict[int, str] = {
    2025: "SAS-Innovate-2025",
    2026: "SASInnovate2026",
}
API = "https://api.github.com"
GH_HEADERS = {"User-Agent": "ClinProc-Scraper",
              "Accept": "application/vnd.github+json"}
SKIP_REPOS = {".github"}

# "Presented By: Carleigh Jo Crabtree, Technical Training Consultant, SAS Institute"
PRESENTED_RE = re.compile(r"Presented\s+By\s*:\s*(.+)", re.IGNORECASE)
FORMAT_RE = re.compile(r"^Format\s*:\s*(.+)", re.IGNORECASE | re.MULTILINE)
# 大写的姓名 token(可含 . 与连字符),用于从 "姓名, 职务, 单位" 里切出姓名
NAME_RE = re.compile(
    r"^[A-Z][\w'.\-]*(?:\s+[A-Z][\w'.\-]*)*(?:\s+(?:van|de|der|den|la|le)\s+[A-Z][\w'.\-]*)*$"
)
# 职务/单位特征词:命中即认为姓名结束(2026 README 常见
# "Presented By: 姓名, Technical Training Consultant, SAS Institute" 格式)
ROLE_WORDS = {
    "consultant", "manager", "specialist", "director", "engineer", "principal",
    "lead", "developer", "architect", "scientist", "analyst", "advisor",
    "professor", "instructor", "trainer", "president", "officer", "head",
    "member", "fellow", "associate", "senior", "technical", "advisory",
    "institute", "university", "college", "inc", "ltd", "llc", "corp",
    "group", "team", "solutions", "services", "enablement", "learning",
    "global", "offices", "office",
}


class SASInnovateSpider(BaseSpider):
    conference = "sas-innovate"
    base_url = "https://github.com"
    rate_limit = 1.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.years_filter: set[int] | None = None
        # GitHub API 走独立 client(需要 Accept 头),不复用 BaseSpider 的缓存
        import httpx
        headers = dict(GH_HEADERS)
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._gh = httpx.Client(timeout=30.0, headers=headers)
        # 每个 repo 的原始数据(readme/tree/contributors)落盘缓存,
        # 避免被限流中断后重跑重复消耗 API 配额(匿名限流仅 60 次/小时)
        self._repo_cache_dir = self.cache_dir / "sasinnovate"
        self._repo_cache_dir.mkdir(parents=True, exist_ok=True)

    def set_years(self, years: set[int]) -> None:
        self.years_filter = years

    def _gh_get(self, url: str, _wait: bool = True, **params):
        self._throttle()
        try:
            r = self._gh.get(url, params=params or None)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (403, 429):
                reset = r.headers.get("X-RateLimit-Reset")
                remaining = r.headers.get("X-RateLimit-Remaining")
                if remaining == "0" and reset and _wait:
                    wait = max(int(reset) - int(time.time()), 0) + 15
                    log.warning("[sas-innovate] API 限流,等待 %d 秒后继续", wait)
                    time.sleep(wait)
                    return self._gh_get(url, _wait=False, **params)
            log.warning("[sas-innovate] GitHub API %s -> %s", url, r.status_code)
        except Exception as e:
            log.warning("[sas-innovate] GitHub API 失败 %s: %s", url, e)
        return None

    def _repo_cached(self, full_name: str) -> dict | None:
        path = self._repo_cache_dir / f"{full_name.replace('/', '__')}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def _repo_cache_save(self, full_name: str, data: dict) -> None:
        path = self._repo_cache_dir / f"{full_name.replace('/', '__')}.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def collect(self) -> list[Paper]:
        papers: list[Paper] = []
        try:
            for year, org in ORGS.items():
                if self.years_filter and year not in self.years_filter:
                    continue
                log.info("[sas-innovate] 抓取 %d (%s)", year, org)
                got = self._scrape_org(year, org)
                log.info("[sas-innovate] %d 年 %d 场 session", year, len(got))
                papers.extend(got)
        finally:
            self._gh.close()
        log.info("[sas-innovate] 共 %d 篇", len(papers))
        return papers

    def _scrape_org(self, year: int, org: str) -> list[Paper]:
        repos = self._list_repos(org)
        papers: list[Paper] = []
        for repo in repos:
            name = repo["name"]
            if name in SKIP_REPOS:
                continue
            full = f"{org}/{name}"
            try:
                p = self._repo_to_paper(year, full, repo)
            except Exception:
                log.exception("[sas-innovate] 解析 %s 失败,跳过", full)
                continue
            if p:
                papers.append(p)
        return papers

    def _list_repos(self, org: str) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            batch = self._gh_get(f"{API}/orgs/{org}/repos",
                                 per_page=100, page=page)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return out

    def _repo_to_paper(self, year: int, full_name: str,
                       repo: dict) -> Paper | None:
        # 优先用落盘缓存(限流中断重跑时不再重复消耗 API 配额)
        data = self._repo_cached(full_name)
        if data and data.get("paper"):
            return Paper(**data["paper"])
        if data is None:
            readme = self._fetch_readme(full_name)
            files = self._list_files(full_name)
            if not readme and not files:
                # 整体失败(多半是限流),不落盘,下次重跑重试
                data = {"readme": "", "files": []}
            else:
                data = {"readme": readme, "files": files}
                self._repo_cache_save(full_name, data)
        readme = data.get("readme", "")
        title, abstract, presented, fmt = self._parse_readme(readme)
        if not title:
            title = (repo.get("description") or "").strip() or repo["name"]
        if not abstract:
            abstract = (repo.get("description") or "").strip()

        authors = self._parse_presenters(presented)
        # README 无 Presented By 时 authors 留空——contributors 是仓库
        # 维护者(SAS EDU 团队账号),不是讲者,写入会产生脏作者数据

        pdf_url = ""
        for f in data.get("files", []):
            if f.get("type") == "file" and f["name"].lower().endswith(".pdf"):
                pdf_url = f.get("html_url", "")
                break

        code = repo["name"]
        paper = self.make_paper(
            id=Paper.make_id(self.conference, f"{year}-{code}"),
            title=title,
            authors=authors,
            year=year,
            conference=self.conference,
            section_code=fmt[:20] if fmt else "",
            section_name=fmt or "",
            paper_code=f"{code}-{year}",
            pdf_url=pdf_url,
            source_url=repo.get("html_url", f"https://github.com/{full_name}"),
            abstract=abstract[:1500],
        )
        # 解析结果落盘,后续重跑直接命中缓存、不再消耗 API 配额
        data["paper"] = paper.to_dict()
        self._repo_cache_save(full_name, data)
        return paper

    def _fetch_readme(self, full_name: str) -> str:
        data = self._gh_get(f"{API}/repos/{full_name}/readme")
        if not data or not data.get("content"):
            return ""
        try:
            return base64.b64decode(data["content"]).decode("utf-8", "replace")
        except Exception:
            return ""

    @staticmethod
    def _parse_readme(md: str) -> tuple[str, str, str, str]:
        """返回 (title, abstract, presented_by 行, format)。"""
        title, abstract, presented, fmt = "", "", "", ""
        if not md:
            return title, abstract, presented, fmt
        paras: list[str] = []
        for block in re.split(r"\n\s*\n", md):
            block = block.strip()
            if not block:
                continue
            for line in block.splitlines():
                m = PRESENTED_RE.search(line)
                if m and not presented:
                    presented = m.group(1).strip()
            if block.startswith("#"):
                first = block.splitlines()[0].lstrip("#").strip()
                if not title and first:
                    title = first
                continue
            paras.append(re.sub(r"\s+", " ", block))
        # 摘要:首个非标题块;跳过纯免责/链接块
        for para in paras:
            if para.startswith(("http", "![")) or len(para) < 40:
                continue
            if "should not be considered a replacement" in para:
                continue
            abstract = para
            break
        m = FORMAT_RE.search(md)
        if m:
            fmt = m.group(1).strip()
        return title, abstract, presented, fmt

    @staticmethod
    def _parse_presenters(text: str) -> list[str]:
        """'Carleigh Jo Crabtree, Technical Training Consultant, SAS Institute'
        -> 取大写姓名段,遇到职务/单位即停。支持 'A, B' 多讲者与
        markdown 链接 '**[Rob Collum](url)**' 形式。"""
        if not text:
            return []
        # 去 markdown 链接/加粗/裸 URL
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[*_`]", "", text)
        text = re.sub(r"https?://\S+", "", text)
        # 'A and B' 视为多讲者
        text = re.sub(r"\s+and\s+", ", ", text)
        authors: list[str] = []
        for part in text.split(","):
            part = part.strip(" \t;*")
            if not part:
                continue
            words = [w.strip(".,") for w in part.lower().split()]
            if any(w in ROLE_WORDS for w in words):
                break  # 首个职务/单位段,其后全部丢弃
            if NAME_RE.match(part):
                authors.append(part)
            elif authors:
                break
        return authors

    def _list_files(self, full_name: str) -> list[dict]:
        data = self._gh_get(f"{API}/repos/{full_name}/contents/")
        return data if isinstance(data, list) else []
