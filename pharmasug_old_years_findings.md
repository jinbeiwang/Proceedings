# PharmaSUG 旧年份论文 (2007-2010) Wayback Machine CDX API 调研报告

## 调研背景
当前爬虫只能找到 2011 年及以后的 PharmaSUG 论文。本调研通过 Wayback Machine CDX API
搜索 2007-2010 年的旧论文归档。

## 调研方法
使用 httpx (timeout=60s, follow_redirects=True) 查询 CDX API:
```
http://web.archive.org/cdx/search/cdx?url={pattern}&output=json&fl=timestamp,original,statuscode&filter=statuscode:200&collapse=urlkey&limit=5000
```

查询的 URL 模式:
- `pharmasug.org/proceedings/2007*` ~ `2010*` (特定年份)
- `pharmasug.org/*` 和 `www.pharmasug.org/*` (广覆盖)
- `pharmasug.org/2007/*` ~ `2010/*` (旧路径结构)
- `pharmasug.org/proceedings/*` (所有 proceedings 路径)
- `pharmasug.org/cd/*` (CD 论文路径)
- `pharmasug.org/download/*` (下载路径)

## 关键发现

### 1. `/proceedings/` 路径结构从 2011 年才开始
`/proceedings/*` 路径下只包含以下年份:
- 2011-2026 (主会议)
- china2014-2022, japan2020-2023, tokyo2018-2019, wuhan2019 (区域会议)

**2007-2010 年完全没有 `/proceedings/2007*` ~ `/proceedings/2010*` 的记录。**
这就是爬虫只能找到 2011+ 论文的根本原因。

### 2. 旧年份网站归档极少
`/2007/*` ~ `/2010/*` 路径模式的归档情况:
- `/2007/*`: 仅 2 条记录 (index.html, images/logo.gif)
- `/2008/*`: 0 条记录
- `/2009/*`: 0 条记录
- `/2010/*`: 仅 1 条记录 (2010-exhibitor-sponsor-application)

较早年份 (2003-2006) 反而有更多归档:
- `/2003/`: 77 条, `/2004/`: 65 条, `/2005/`: 28 条, `/2006/`: 29 条

### 3. 发现 PharmaSUG 2008 最佳论文 (20 个 PDF)
路径: `/download/bestpapers2008/{category}/{paper}.pdf`

完整列表 (20 个 PDF):
| # | 时间戳 | URL |
|---|--------|-----|
| 1 | 20081121204127 | /download/bestpapers2008/ad/AD01.pdf |
| 2 | 20081121212625 | /download/bestpapers2008/ad/AD08.pdf |
| 3 | 20081121190653 | /download/bestpapers2008/ad/AD19.pdf |
| 4 | 20081121195422 | /download/bestpapers2008/cc/CC10.pdf |
| 5 | 20081121202508 | /download/bestpapers2008/cc/CC17.pdf |
| 6 | 20081121195559 | /download/bestpapers2008/cc/CC20.pdf |
| 7 | 20081121215757 | /download/bestpapers2008/dm/DM06.pdf |
| 8 | 20081121215254 | /download/bestpapers2008/ma/MA02.pdf |
| 9 | 20081121211433 | /download/bestpapers2008/po/PO10.pdf |
| 10 | 20081121203255 | /download/bestpapers2008/po/PO12.pdf |
| 11 | 20081121205536 | /download/bestpapers2008/po/PO16.pdf |
| 12 | 20081121212326 | /download/bestpapers2008/pr/PR03.pdf |
| 13 | 20081121185820 | /download/bestpapers2008/rs/RS04.pdf |
| 14 | 20081121214239 | /download/bestpapers2008/rs/RS07.pdf |
| 15 | 20081121190121 | /download/bestpapers2008/sp/SP05.pdf |
| 16 | 20081121191246 | /download/bestpapers2008/sp/SP10.pdf |
| 17 | 20081121210534 | /download/bestpapers2008/tt/TT03.pdf |
| 18 | 20081121202126 | /download/bestpapers2008/tt/TT07.pdf |
| 19 | 20081121194836 | /download/bestpapers2008/tu/TU04.pdf |
| 20 | 20081121205802 | /download/bestpapers2008/tu/TU09.pdf |

### 4. 发现 `/cd/papers/` 路径 (66 个 PDF，年份未知)
路径: `/cd/papers/{category}/{paper}.pdf`

这 66 个 PDF 没有 URL 中包含年份信息，但最早归档时间戳为 2010 年。
可能来自 2010 年或更早的会议论文 (CD-ROM 分发方式)。

归档年份分布:
- 2010: 4 个 (最早)
- 2012: 4 个
- 2017: 53 个 (大量补档)
- 2021-2024: 5 个

论文分类统计:
- AD: 15, CC: 7, CD: 7, DM: 2, HW: 3, IB: 4
- MA: 6, PO: 6, SAS: 4, SP: 1, TT: 9, TU: 2

最早归档的 4 个 (2010年):
- [20101223230344] /cd/papers/AD/AD12.pdf
- [20101223230356] /cd/papers/CC/CC19.pdf
- [20101123010814] /cd/papers/TT/TT01.pdf
- [20101230200944] /cd/papers/SP/SP05.pdf

### 5. download/ 路径中的其他旧年份文档
- /download/Conference_Committee_19Nov2007.pdf (2007年委员会文档)
- /download/Conference_Committee[1]_21Jan2008.pdf (2008年委员会文档)
- /download/PharmaSUG_2009_20Planning.pdf (2009年规划文档)
- /download/tri-folder-PharmaSUG2009-final.pdf (2009年会议三折页)

## 站点路径结构分析 (pharmasug.org/* 前 5000 条)
| 路径段 | URL 数量 | 说明 |
|--------|----------|------|
| proceedings/ | 2678 | 论文 (仅 2011+) |
| images/ | 738 | 图片资源 |
| download/ | 402 | 下载文件 (含 bestpapers2008) |
| china/ | 171 | 中国区域会议 |
| content/ | 126 | 内容页面 |
| media/ | 86 | 媒体资源 |
| ads/ | 82 | 广告 |
| 2003/ | 77 | 2003年会议网站 |
| cd/ | 66 | CD论文 (年份未知) |
| 2004/ | 65 | 2004年会议网站 |
| 2006/ | 29 | 2006年会议网站 |
| 2005/ | 28 | 2005年会议网站 |
| 2007/ | 2 | 2007年会议网站 (极少) |

广覆盖查询中共 3148 个 PDF，但几乎全部来自 2011+ 的 proceedings/ 路径。

## 结论与建议

1. **根本原因**: PharmaSUG 网站在 2011 年才开始使用 `/proceedings/YYYY/` 的 URL 结构。
   2007-2010 年的论文使用不同的分发方式 (CD-ROM、bestpapers 下载等)。

2. **可获取的旧论文**:
   - 2008 年最佳论文: 20 个 PDF (`/download/bestpapers2008/`)
   - 年份未知的 CD 论文: 66 个 PDF (`/cd/papers/`)，可能来自 2010 年或更早

3. **无法获取的旧论文**:
   - 2007 年: Wayback Machine 中几乎没有论文归档
   - 2009 年: 仅有规划文档，无论文
   - 2010 年: `/cd/papers/` 中的 66 个 PDF 可能部分属于 2010 年

4. **爬虫改进建议**:
   - 添加 `/download/bestpapers*/` 路径扫描
   - 添加 `/cd/papers/` 路径扫描
   - 对于 `/cd/papers/` 中的论文，需要下载后检查 PDF 内容来确定年份
   - 考虑查询其他归档源 (如 lexjansen.com 可能有这些旧论文的镜像)
