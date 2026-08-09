# ClinProc · 临床编程会议论文索引

一个**纯静态、零服务器**的会议论文索引站,汇总 PharmaSUG、PHUSE、SAS Global Forum、R/Pharma 等临床编程会议论文,支持按会议 / 年份 / 主题分类浏览与全文检索。

灵感来自已离线的 [Lex Jansen](https://www.lexjansen.com/) 索引站,参考了 [clinyun.com/ppi](https://www.clinyun.com/ppi/) 与 [clinstandards.org](https://www.clinstandards.org/) 的资源组织方式。

## 工作原理

```
会议官网 ──抓取──▶ Python scraper ──▶ JSON 数据 ──▶ 静态站点 ──▶ GitHub Pages
                     ▲                                    │
                     │         GitHub Actions 定时触发      │
                     └───────────(每月 + 会议季后)────────┘
```

- **静态站点**:`site/` 目录,纯 HTML + CSS + JS,用 [Lunr.js](https://lunrjs.com/) 做客户端全文检索,无需任何后端。
- **动态抓取**:`scraper/` 用 Python 从各会议官网抓取论文元数据。静态站本身不能"运行时抓取",因此通过 **GitHub Actions 定时**运行抓取脚本,更新 JSON 后自动重新部署——这是"静态站 + 每年自动更新"的标准模式。
- **零成本**:全部托管在 GitHub Pages,免费、无需服务器或数据库。

## 目录结构

```
proceedings/
├── scraper/                  # Python 抓取脚本
│   ├── main.py               # 主入口:调度 spider、汇总去重、输出 JSON
│   ├── models.py             # Paper 数据模型 + 会议注册表
│   ├── base.py               # BaseSpider:HTTP/缓存/限速/解析基类
│   ├── spiders/
│   │   ├── pharmasug.py      # PharmaSUG(已实现,验证可用)
│   │   ├── phuse.py          # PHUSE(骨架,待补)
│   │   └── sasgf.py          # SAS Global Forum / SUGI(骨架,待补)
│   └── requirements.txt
├── site/                     # 静态网站
│   ├── index.html
│   ├── assets/css/style.css
│   ├── assets/js/app.js
│   └── data/                 # 抓取生成的 JSON(由 scraper 写入)
│       ├── papers.json
│       └── conferences.json
├── .github/workflows/
│   └── scrape-and-deploy.yml # 定时抓取 + 部署工作流
└── README.md
```

## 本地运行

### 1. 抓取数据

```powershell
cd scraper
pip install -r requirements.txt

# 抓取所有已实现的会议
python main.py

# 只抓 PharmaSUG US
python main.py -c pharmasug-us

# 限定年份(加快测试)
python main.py -c pharmasug-us --years 2025,2026
```

抓取结果写入 `site/data/papers.json` 与 `site/data/conferences.json`。HTML 缓存在 `scraper/.cache/`(加速重跑,已 gitignore)。

### 2. 本地预览站点

由于站点用 `fetch()` 加载 JSON,需通过 HTTP 服务器预览(不能直接 file:// 打开):

```powershell
cd site
python -m http.server 8765
# 浏览器访问 http://127.0.0.1:8765/
```

## 部署到 GitHub Pages

1. 将本项目推送到 GitHub 仓库。
2. 仓库 **Settings → Pages → Source** 设为 **GitHub Actions**。
3. 工作流 `.github/workflows/scrape-and-deploy.yml` 会自动:
   - 每月 1 日 + 会议季后的 6/7/11/12 月 15 日定时抓取;
   - 也可在 **Actions** 页面手动 **Run workflow**(可限定会议 / 年份)。
4. 抓取到新数据后自动提交并部署,站点即时更新。

## 新增一个会议

1. 在 `scraper/models.py` 的 `CONFERENCES` 注册表添加会议代码与元数据。
2. 在 `scraper/spiders/` 新建 spider,继承 `BaseSpider`,实现 `collect()` 返回 `Paper` 列表。
3. 在 `scraper/spiders/__init__.py` 的 `SPIDERS` 注册。
4. 本地跑 `python main.py -c <会议代码>` 验证。

每个 spider 只需关心:如何从该会议官网的 proceedings 页解析出论文标题、section、年份、PDF 链接。基类已处理 HTTP、限速、缓存、重试、元数据填充。

## 数据字段(Paper schema)

| 字段 | 说明 |
|---|---|
| `id` | 唯一键 `{conference}-{paper_code}` |
| `title` | 论文标题 |
| `authors` | 作者列表(部分会议需从 PDF 提取) |
| `year` | 年份 |
| `conference` / `conference_name` | 会议代码 / 展示名 |
| `section_code` / `section_name` | 主题分区代码 / 名称 |
| `paper_code` | 原始编号,如 `PharmaSUG-2025-AP-002` |
| `pdf_url` | PDF 直链(绝对 URL,指向会议官网) |
| `region` / `lang` | 地区 / 语言 |
| `added_at` | 抓取时间(ISO8601) |

## 当前覆盖情况

| 会议 | 状态 | 说明 |
|---|---|---|
| PharmaSUG US | ✅ 已实现 | 2022–2026 已抓取验证;旧年份(2011–2021)官网索引已下线,需 Wayback 恢复 |
| PHUSE / FDA-CSS | 🔲 骨架 | 待核实 phuse-events.org 结构后实现 |
| SAS Global Forum / SUGI | 🔲 骨架 | 待核实 support.sas.com 归档后实现 |
| 其余 20 个会议 | 🔲 已注册 | 待逐步补 spider |

> **关于旧年份**:PharmaSUG 新站仅托管近几年在线 proceedings 索引,2011–2021 的索引页会重定向到最新届。这正是 Lex Jansen 当年补齐的缺口。恢复旧年份的路径:通过 [Wayback Machine](https://web.archive.org/) 的 CDX API 抓取 lexjansen.com 旧索引作为种子,或抓取旧 PharmaSUG 站点快照。框架已支持,只需新增一个 Wayback spider。

## 合规说明

- 本站**仅做索引与链接**,论文 PDF 版权属于各会议与作者,点击直达官方原始 PDF。
- 抓取遵守各站 `robots.txt`,设限速,不抓取会员专有内容。
- 如需镜像 PDF 或抓取受限内容,请先获得会议方授权。

## 技术栈

- 抓取:Python 3 + httpx + BeautifulSoup4
- 站点:原生 HTML/CSS/JS(无构建步骤)
- 检索:Lunr.js(客户端全文索引)
- 自动化:GitHub Actions(cron + workflow_dispatch)
- 托管:GitHub Pages
