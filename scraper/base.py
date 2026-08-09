"""BaseSpider:所有会议 spider 的公共基类。

负责 HTTP 请求(带浏览器 UA、限速、重试)、HTML 解析、缓存与日志。
子类只需实现 collect() 返回 Paper 列表。
"""
from __future__ import annotations

import time
import logging
import hashlib
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from models import Paper, CONFERENCES

log = logging.getLogger("scraper")

# 浏览器风格请求头,避免被部分站点拦截(PharmaSUG 对默认 UA 返回 403)。
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
}


class BaseSpider:
    """会议抓取基类。"""

    # 子类覆盖以下属性
    conference: str = ""             # CONFERENCES 键
    base_url: str = ""
    rate_limit: float = 1.5          # 请求间隔(秒)

    def __init__(self, cache_dir: Optional[Path] = None, client: Optional[httpx.Client] = None):
        self.meta = CONFERENCES.get(self.conference, {})
        self.cache_dir = cache_dir
        self._client = client or httpx.Client(
            headers=HEADERS, timeout=30.0, follow_redirects=True
        )
        self._last_request = 0.0

    # ---- HTTP 辅助 ----
    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.time()

    def _cache_path(self, key: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        h = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{self.conference}_{h}.html"

    def fetch_html(self, url: str, force: bool = False) -> str:
        """抓取 HTML 文本,带磁盘缓存与限速重试。"""
        cache = self._cache_path(url)
        if cache and cache.exists() and not force:
            return cache.read_text(encoding="utf-8", errors="replace")

        for attempt in range(3):
            self._throttle()
            try:
                resp = self._client.get(url)
                if resp.status_code == 200:
                    text = resp.text
                    if cache:
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        cache.write_text(text, encoding="utf-8")
                    return text
                if resp.status_code in (503, 502, 429):
                    wait = 3 * (attempt + 1)
                    log.warning("[%s] %s -> HTTP %d, %ds 后重试", self.conference, url, resp.status_code, wait)
                    time.sleep(wait)
                    continue
                log.warning("[%s] %s -> HTTP %s", self.conference, url, resp.status_code)
                if resp.status_code in (403, 404):
                    return ""
            except httpx.HTTPError as exc:
                log.warning("[%s] %s -> %s (attempt %d)", self.conference, url, exc, attempt + 1)
                time.sleep(2 * (attempt + 1))
        return ""

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    def absurl(self, url: str) -> str:
        return urljoin(self.base_url, url)

    # ---- Wayback Machine 辅助 ----
    def fetch_wayback(self, url: str, timestamp: str = "") -> str:
        """从 Wayback Machine 获取归档页面 HTML(原始内容,无 Wayback 改写)。"""
        if not timestamp:
            # CDX 查询最近成功的快照(带重试)
            for attempt in range(3):
                cdx_url = (
                    f"http://web.archive.org/cdx/search/cdx?url={url}"
                    f"&output=json&limit=1&filter=statuscode:200"
                )
                try:
                    resp = self._client.get(cdx_url, timeout=20.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        if len(data) > 1:
                            timestamp = data[1][1]
                            break
                    elif resp.status_code in (503, 502, 429):
                        time.sleep(min(3 * (2 ** attempt), 15))
                        continue
                    else:
                        break
                except Exception:
                    if attempt < 2:
                        time.sleep(min(3 * (2 ** attempt), 15))
            if not timestamp:
                return ""
        wayback_url = f"https://web.archive.org/web/{timestamp}id_/{url}"
        return self.fetch_html(wayback_url)

    def wayback_cdx_search(self, url_pattern: str, limit: int = 5000) -> list[dict]:
        """通过 CDX API 搜索 Wayback Machine 归档的 URL 列表。

        带指数退避重试(最多 5 次),应对 Wayback 频繁的 503/超时。
        """
        import json as _json

        cdx_url = (
            f"http://web.archive.org/cdx/search/cdx?"
            f"url={url_pattern}&output=json"
            f"&fl=timestamp,original,statuscode"
            f"&filter=statuscode:200&collapse=urlkey&limit={limit}"
        )

        max_retries = 5
        for attempt in range(max_retries):
            try:
                resp = self._client.get(cdx_url, timeout=45.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if len(data) <= 1:
                        return []
                    keys = data[0]
                    return [dict(zip(keys, row)) for row in data[1:]]
                elif resp.status_code in (503, 502, 429):
                    wait = min(3 * (2 ** attempt), 30)
                    log.warning(
                        "[%s] CDX 查询 HTTP %d, %ds 后重试 (%d/%d)",
                        self.conference, resp.status_code, wait, attempt + 1, max_retries,
                    )
                    time.sleep(wait)
                    continue
                else:
                    log.warning("[%s] CDX 查询 HTTP %d", self.conference, resp.status_code)
                    return []
            except (httpx.HTTPError, _json.JSONDecodeError, Exception) as exc:
                wait = min(3 * (2 ** attempt), 30)
                log.warning(
                    "[%s] CDX 查询异常: %s, %ds 后重试 (%d/%d)",
                    self.conference, exc, wait, attempt + 1, max_retries,
                )
                time.sleep(wait)

        log.error("[%s] CDX 查询 %d 次后仍失败: %s", self.conference, max_retries, url_pattern)
        return []

    @staticmethod
    def wayback_url(original_url: str, timestamp: str) -> str:
        """构造 Wayback Machine 可访问的 URL。"""
        return f"https://web.archive.org/web/{timestamp}/{original_url}"

    # ---- 子类实现 ----
    def collect(self) -> list[Paper]:
        raise NotImplementedError

    # ---- 公共工具 ----
    def make_paper(self, **kw) -> Paper:
        """填充会议元数据与时间戳。"""
        from datetime import datetime, timezone
        kw.setdefault("conference", self.conference)
        kw.setdefault("conference_name", self.meta.get("name", self.conference))
        kw.setdefault("region", self.meta.get("region", ""))
        kw.setdefault("lang", self.meta.get("lang", "en"))
        kw.setdefault("added_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        paper_code = kw.get("paper_code", "")
        kw.setdefault("id", Paper.make_id(self.conference, paper_code))
        return Paper(**kw)
