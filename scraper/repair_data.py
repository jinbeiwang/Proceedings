"""数据修复工具:升级 Wayback 快照链接为官方在线直链,并从 PDF 首页提取真实标题/作者。

背景:
  - SUGI 1997-2006 / SGF 2007-2021 的论文 PDF 在 sas.com 官方镜像上仍然在线
    (旧 www2.sas.com 路径会 301 到 support.sas.com/resources/papers/proceedings/)
  - 历史记录中约 5600 条 pdf_url 指向 web.archive.org 快照,长期可靠性差
  - 约 2300 条记录只有占位标题(CDX 兜底产物),真实标题可从 PDF 首页提取

用法:
  python repair_data.py                    # 全量修复 papers.json(原地备份后写回)
  python repair_data.py --limit 30         # 只处理前 30 条(试跑)
  python repair_data.py --dry-run          # 不写文件,只打印统计
  python repair_data.py --file ../site/data/papers.json

处理策略(逐条):
  1. pdf_url 是 wayback 链接 -> 还原原始 URL -> 按镜像规则构造直链候选 -> HEAD 探测
     命中即替换 pdf_url(lexjansen 等无官方镜像的保持原样)。
  2. 标题为占位符且 pdf_url 为 sas.com 域直链 -> 下载 PDF,
     用 pypdf 提取首页文本,解析标题与作者。

幂等: 已是直链/真实标题的记录直接跳过。
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("repair")

HERE = Path(__file__).resolve().parent
DEFAULT_FILE = HERE.parent / "site" / "data" / "papers.json"

WAYBACK_RE = re.compile(r"https?://web\.archive\.org/web/\d+(?:id_)?/(https?://.*)$")
PLACEHOLDER_RE = re.compile(r"^(Paper\s+\d|SUGI\s+\d{4}\s+Paper\s)")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
}

# 全局限速(所有线程共享)
_lock = threading.Lock()
_last_req = [0.0]
RATE = 0.15


def throttle() -> None:
    with _lock:
        wait = RATE - (time.time() - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.time()


# ---- 直链候选构造 ----

def direct_candidates(original_url: str) -> list[str]:
    """根据原始 URL 构造官方在线直链候选(按优先级)。"""
    u = original_url.replace("http://", "https://")
    u = re.sub(r"//([^/:]+):(?:80|443)(/|$)", r"//\1\2", u)

    cands: list[str] = []
    # www2.sas.com/proceedings/{sugiN|forumYYYY}/... -> support.sas.com 官方镜像
    m = re.match(r"https://www2\.sas\.com/(proceedings/.+)$", u)
    if m:
        cands.append(f"https://support.sas.com/resources/papers/proceedings/proceedings/{m.group(1)}")
        cands.append(u)  # www2 本身也会 301 到镜像,作为兜底
    # www.sas.com content/dam(SGF 2015-2021): 优先用稳定的 support.sas.com 镜像
    elif "sas.com/content/dam" in u:
        dm = re.search(r"sas-global-forum-proceedings/(\d{4})/(\d+)-(\d{4})\.pdf", u)
        if dm:
            cands.append(f"https://support.sas.com/resources/papers/proceedings{dm.group(3)[2:]}/{dm.group(2)}-{dm.group(3)}.pdf")
        cands.append(u)
    # pharmasug.org 旧路径: 官网可能仍托管,原样探测
    elif "pharmasug.org" in u:
        cands.append(u)
    return cands


_probe_cache: dict[str, bool] = {}


def probe(client: httpx.Client, url: str) -> bool:
    with _lock:
        if url in _probe_cache:
            return _probe_cache[url]
    throttle()
    try:
        ok = client.head(url, follow_redirects=True).status_code == 200
    except httpx.HTTPError:
        ok = False
    with _lock:
        _probe_cache[url] = ok
    return ok


def upgrade_pdf_url(client: httpx.Client, rec: dict) -> str | None:
    """返回可用的直链;无则返回 None。"""
    pdf_url = rec.get("pdf_url", "")
    if "web.archive.org" not in pdf_url:
        return None
    m = WAYBACK_RE.match(pdf_url)
    if not m:
        return None
    original = m.group(1)
    for cand in direct_candidates(original):
        if probe(client, cand):
            return cand
    return None


# ---- PDF 首页标题/作者提取 ----

# 断路器: 某些主机下载会被网络中间设备截断(大 PDF 传几秒后 RST),
# 连续失败 3 次后跳过该主机,避免全量跑时白耗数小时。
_host_fails: dict[str, int] = {}


def extract_title_author(client: httpx.Client, pdf_url: str) -> tuple[str, list[str]]:
    """下载 PDF,提取首页文本并解析标题与作者。失败返回 ("", [])。

    注: 不用 Range 分段下载 —— pypdf 需要文件尾部的 xref 表,
    截断的字节流会导致解析失败;会议论文 PDF 通常 <1MB,全量下载更可靠。
    """
    host = re.match(r"https?://([^/]+)/", pdf_url)
    host = host.group(1) if host else ""
    if _host_fails.get(host, 0) >= 3:
        return "", []
    throttle()
    data = b""
    for attempt in range(2):
        try:
            resp = client.get(pdf_url, timeout=60.0)
            data = resp.content
            break
        except httpx.HTTPError:
            if attempt == 0:
                time.sleep(1.5)
    try:
        if not data.startswith(b"%PDF"):
            raise ValueError("not a pdf")
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=False)
        if not reader.pages:
            return "", []
        text = reader.pages[0].extract_text() or ""
    except Exception:
        _host_fails[host] = _host_fails.get(host, 0) + 1
        return "", []
    _host_fails[host] = 0
    return parse_first_page(text)


def parse_first_page(text: str) -> tuple[str, list[str]]:
    """从首页文本解析标题与作者。

    启发式: 逐行清洗后,标题=前几行中最长的"句子样"行;
    作者=紧随其后、包含人名样式的行。
    """
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return "", []

    # 在 ABSTRACT/INTRODUCTION 等章节标记处截断,避免正文长句被误认为标题
    for i, ln in enumerate(lines):
        if re.fullmatch(r"(ABSTRACT|INTRODUCTION|BACKGROUND|OVERVIEW|EXECUTIVE SUMMARY)\s*[:.]?", ln, re.I):
            lines = lines[:i]
            break
    if not lines:
        return "", []

    # 丢弃纯数字/单字符/页眉噪音行
    def noise(ln: str) -> bool:
        return (len(ln) < 4 or re.fullmatch(r"[\d\W_]+", ln)
                or re.fullmatch(r"SUGI\s+\d{2,4}.*", ln, re.I)
                or re.fullmatch(r"Paper\s+\d+[-_]\d+", ln, re.I)
                or re.fullmatch(r"\d{3,4}[-_]\d{4}", ln)
                or re.fullmatch(r"PharmaSUG\b[^,;:]*\d{4}[^,;:]{0,20}", ln, re.I))

    cands = [(i, ln) for i, ln in enumerate(lines[:15]) if not noise(ln)]
    if not cands:
        return "", []

    # 标题 = 第一个长行(>25 字符),否则退化为前 8 候选中最长行;
    # 随后贪心拼接续行(SAS 标题常跨行),遇作者样行/句子样行即停
    long_cands = [(i, ln) for i, ln in cands if len(ln) > 25]
    ti, title = (long_cands[0] if long_cands else max(cands[:8], key=lambda kv: len(kv[1])))
    if len(title) < 10:
        return "", []
    j = cands.index((ti, title)) + 1
    while j < len(cands):
        nxt = cands[j][1]
        # 作者行特征: 含逗号的短行("Name, Affiliation");无逗号的大写行视为标题续行
        if "," in nxt and _looks_like_authors(nxt):
            break
        if ((len(nxt) >= 48 and not nxt.isupper())
                or re.search(r"[.?]\s*$", nxt)):
            break
        if len(title) < 220:
            title += " " + nxt
        j += 1

    # 作者: 标题之后紧邻的 1-2 行中的作者样行
    authors: list[str] = []
    for _, ln in cands[j:j + 2]:
        if _looks_like_authors(ln):
            authors = _split_authors(ln)
            break
    return title.strip(), authors


def _looks_like_authors(line: str) -> bool:
    """人名行特征: 短、含逗号/'and'、多个首字母大写词,且不是问句/句子。"""
    if len(line) > 160 or line.endswith("?"):
        return False
    words = line.split()
    if not 2 <= len(words) <= 20:
        return False
    if re.search(r"\b(and|,)\b", line) and len(words) <= 16:
        return True
    cap = sum(1 for w in words if w[:1].isupper())
    return cap / len(words) >= 0.7 and not re.search(r"\b(the|with|using|for|via)\b", line, re.I)


AFFIL_RE = re.compile(
    r"\b(Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|Company|University|Hospital|Institute|"
    r"College|School|Agency|Laboratories?|Group|Association|Foundation|SAS\s+Institute)\b",
    re.I)


def _split_authors(line: str) -> list[str]:
    line = re.sub(r"\s*\b(and)\b\s*", ", ", line, flags=re.I)
    parts = [p.strip() for p in line.split(",")]
    out = []
    for p in parts:
        if not p or not re.search(r"[A-Za-z]", p):
            continue
        name = p.strip(" .")
        # "John Doe, ABC Inc, Cary, NC": 遇机构段即截断,后面的城市/州不再收集
        if AFFIL_RE.search(name):
            break
        if len(name.split()) > 5:  # 过长片段更像描述而非人名
            continue
        # 单个全大写短词多为城市/州缩写("RTP", "NC"),非人名
        if len(name.split()) == 1 and name.isupper() and len(name) <= 4:
            continue
        out.append(name)
    return out[:12]


# ---- 主流程 ----

def repair(file: Path, limit: int | None, dry_run: bool, workers: int) -> None:
    records = json.loads(file.read_text(encoding="utf-8"))
    log.info("加载 %d 条记录 <- %s", len(records), file)

    # 待处理: wayback 链接或占位标题
    todo = [r for r in records
            if "web.archive.org" in r.get("pdf_url", "")
            or PLACEHOLDER_RE.match(r.get("title", ""))]
    if limit:
        todo = todo[:limit]
    log.info("待处理 %d 条", len(todo))

    stats = {"url_upgraded": 0, "title_filled": 0, "author_filled": 0, "failed": 0}
    client = httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True)

    def work(rec: dict) -> None:
        # 1) 链接升级
        if "web.archive.org" in rec.get("pdf_url", ""):
            direct = upgrade_pdf_url(client, rec)
            if direct:
                rec["pdf_url"] = direct
                stats["url_upgraded"] += 1
        # 2) 标题补齐(sas.com / pharmasug.org 官方直链可下载)
        if PLACEHOLDER_RE.match(rec.get("title", "")) and re.search(
                r"sas\.com|pharmasug\.org", rec.get("pdf_url", "")):
            title, authors = extract_title_author(client, rec["pdf_url"])
            if title:
                rec["title"] = title
                stats["title_filled"] += 1
                if authors and not rec.get("authors"):
                    rec["authors"] = authors
                    stats["author_filled"] += 1
                rec["added_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            else:
                stats["failed"] += 1

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(work, r): r for r in todo}
            done = 0
            for fut in as_completed(futs):
                try:
                    fut.result()
                except Exception as exc:
                    stats["failed"] += 1
                    log.warning("记录处理异常: %s", exc)
                done += 1
                if done % 100 == 0:
                    log.info("进度 %d/%d | %s", done, len(todo), stats)
    finally:
        client.close()

    log.info("完成: %s", stats)
    if not dry_run:
        bak = file.with_suffix(".json.repair-bak")
        shutil.copy2(file, bak)
        file.write_text(json.dumps(records, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        log.info("已写回 %s (备份: %s)", file, bak.name)
    else:
        log.info("dry-run: 未写文件")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="papers.json 数据修复")
    ap.add_argument("--file", default=str(DEFAULT_FILE))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    repair(Path(args.file), args.limit, args.dry_run, args.workers)


if __name__ == "__main__":
    main()
