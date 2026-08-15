# GitHub 推送与更新操作指南(新手版)

本项目两个位置:

- **本地文件夹**:`g:\test\proceedings`(你的电脑上的"原件")
- **GitHub 仓库**:`https://github.com/jinbeiwang/Proceedings`(云端备份 + 自动发布机)
- **网站地址**:`https://jinbeiwang.github.io/Proceedings/`

工作原理一句话:你在本地改代码 → `git push` 上传到 GitHub → GitHub Actions(自动程序)自动抓取新论文并重新发布网站。**论文数据不需要你管,会自动更新;代码/前端改动需要你 push。**

---

## 一、一次性设置:开启 GitHub Pages(只需做一次)

> ⚠️ 注意:GitHub 有两个 "Pages" 页面。**账号级**的(头像 → Settings → Pages)是用来绑定自定义域名的,不是这里要设置的。要设置的是**仓库级**的。

1. 浏览器打开仓库主页:`https://github.com/jinbeiwang/Proceedings`
2. 在仓库页面**顶部菜单栏**最右边,点击 **⚙ Settings**(齿轮图标)。
   认准标志:页面左上角显示的是 `jinbeiwang / Proceedings` 仓库名,而不是你的头像。
3. 进入后看**左侧边栏**,在 "Code and automation" 分组下点击 **Pages**。
4. 右侧 "Build and deployment" 区域,找到 **Source** 下拉框,选择 **GitHub Actions**。
5. 选完即生效,没有保存按钮。

验证:等 Actions 运行完成(见第三节)后,打开 `https://jinbeiwang.github.io/Proceedings/` 能看到网站即成功。

---

## 二、每次推送更新:6 步标准流程

### 第 1 步:打开 PowerShell(命令行窗口)

- 方法 A:按键盘 `Win + R`,输入 `powershell`,回车;
- 方法 B:开始菜单搜索 "powershell",点击打开。

打开后是一个蓝色/黑色窗口,提示符类似 `PS C:\Users\jinbe>`。

### 第 2 步:进入项目文件夹

```powershell
cd g:\test\proceedings
```

- `cd` = change directory,切换文件夹的意思;
- 回车后提示符变成 `PS G:\test\proceedings>`,说明已进入。

### 第 3 步:查看有哪些改动(可选,但推荐)

```powershell
git status
```

- 带 `modified:` 的行 = 被修改的文件;
- 带 `??` 的行 = 新增的文件;
- 显示 `working tree clean` = 没有任何改动,不用推送,可以关窗口了。

### 第 4 步:把所有改动加入"待提交清单"

```powershell
git add -A
```

`-A` = all,全部加入。执行完通常没有输出,正常。

### 第 5 步:写一句说明,在本地保存为一个"版本"

```powershell
git commit -m "redesigned 首页卡片样式"
```

- 引号里写你自己的说明,比如 `"修复搜索框错位"`、`"新增 XX 会议爬虫"`;
- 如果提示 `nothing to commit`,说明第 3 步就没改动,到此为止即可。

### 第 6 步:上传到 GitHub

```powershell
git push
```

- 看到 `master -> master` 字样 = 上传成功;
- 本机必须走 SSH(已配置好),**不要**改成 `https://` 开头的地址(本机网络会 reset)。

### 推送之后

1. 打开 `https://github.com/jinbeiwang/Proceedings/actions`,会看到一条新的运行记录,状态是黄色转圈(进行中);
2. 等 2–5 分钟变成绿色 ✅,网站即已更新;
3. 浏览器没变化就按 `Ctrl + F5` 强制刷新。

---

## 三、更省事:一键自动推送(推荐)

不想记命令?双击项目根目录的 **`auto-push.bat`**,脚本自动完成全部事情:

1. `git add -A` 加入所有改动;
2. 没有改动 → 提示“不需要推送”并结束;
3. 有改动 → 自动写一条带时间戳的提交说明并 commit;
4. `git pull --rebase` 先同步云端(避免被 Actions 的数据提交顶回来);
5. `git push` 上传。

全程中文提示,成功会显示“推送成功!网站将在 2-5 分钟内自动更新”。

想自定义提交说明,就在 PowerShell 里运行(而不是双击):

```powershell
.\auto_push.ps1 "新增资源网站 XX"
```

---

## 四、如何确认部署成功 / 排查失败

- **Actions 标签页**(`仓库页顶部 → Actions`):
  - 绿色 ✅ = 成功;红色 ❌ = 失败;黄色转圈 = 正在跑。
- 点进某条记录,左侧是各步骤(拉取代码 → 安装依赖 → 运行抓取 → 提交数据 → 部署),点步骤可看日志。
- 最后一步 `deploy` 成功 = 网站已发布。

---

## 五、哪些改动需要 push?

| 改动内容 | 需要 push 吗 | 说明 |
|---|---|---|
| `site/` 前端(html/css/js) | ✅ 需要 | push 后 Actions 自动部署新界面 |
| `scraper/` 抓取脚本 | ✅ 需要 | 新脚本推上去后,云端才会用它抓 |
| `.github/workflows/` 工作流 | ✅ 需要 | 同上 |
| `site/data/papers.json` 论文数据 | ❌ 不需要 | Actions 每月自动抓取、自动提交、自动部署 |
| `site/data/resources.json` 资源网站 | ✅ 需要 | Resources 页数据,人工维护,见第五节 |
| README、文档 | 随意 | 想备份就 push |

---

## 六、给 Resources 页添加新资源网站(零代码)

Resources 页的数据全部在一个文件里:`site\data\resources.json`。加网站 = 在这个文件里加一段,**完全不用碰代码**。

### 操作步骤

1. 用记事本或 VS Code 打开 `g:\test\proceedings\site\data\resources.json`;
2. 复制任意一个现有的 `{ ... }` 块(连结尾的逗号一起),粘贴到最后一个 `}` 之前;
3. 改成新网站的信息,保存。

一段长这样:

```json
  {
    "name": "Example Org",
    "url": "https://example.org",
    "desc": "One-sentence English description of the site.",
    "category": "opensource",
    "tags": ["R", "Tools"],
    "lang": "EN"
  },
```

### 字段说明

| 字段 | 显示位置 | 怎么填 |
|---|---|---|
| `name` | 卡片标题 | 网站名 |
| `url` | 点击跳转 | 必须以 `https://` 开头 |
| `desc` | 卡片描述 | 一句英文,建议 20 个词以内 |
| `category` | 所属分区 | 只能填这 5 个之一:`standards`(标准与监管)/ `opensource`(开源与 R)/ `community`(社区与组织)/ `sas`(SAS 相关)/ `learning`(学习资源) |
| `tags` | 筛选标签 | 可写多个,如 `["R", "Docs"]`,尽量复用已有标签 |
| `lang` | 语言角标 | 一般填 `EN` |

### 三个常见错误

1. **漏逗号**:两个 `{ }` 块之间必须有英文逗号 `,`(最后一块后面不要);
2. **中文引号**:所有引号必须是英文半角 `"`,中文引号会让整个文件失效;
3. **category 写错**:填了 5 个值以外的词,该网站不会显示在任何分区。

改完后双击 `auto-push.bat`(或按第二节手动 6 步)推送,2–5 分钟自动上线。

> 想加一个全新的"分类"(而不是新网站)才需要改代码(`site\assets\js\app.js` 里的 `RES_CATEGORIES`)。不懂代码就把网站放进最接近的现有分类。

---

## 七、常见报错自查

1. **`fatal: unable to access ... Connection was reset`**
   本机网络封了 HTTPS。本项目已配置 SSH,若 remote 被改坏,用下面命令恢复:
   ```powershell
   git remote set-url origin git@github.com:jinbeiwang/Proceedings.git
   ```
2. **`error: remote origin already exists`**
   地址已设置过。改地址用 `git remote set-url origin <新地址>`,**不要**重复 `git remote add`。
3. **`nothing to commit, working tree clean`**
   没有改动,无需推送。
4. **push 成功但网站没变**
   ① Actions 还没跑完(等几分钟);② 浏览器缓存,按 `Ctrl + F5`;③ 第一节 Pages 的 Source 没选 GitHub Actions。
5. **想本地预览网站再推送**
   ```powershell
   cd g:\test\proceedings\site
   python -m http.server 8765
   ```
   浏览器打开 `http://localhost:8765/` 预览;看完回命令行按 `Ctrl + C` 停掉。

---

## 附:命令速查表(整段复制即可)

```powershell
# 懒人方式:直接双击 auto-push.bat,等于下面 4 条命令
cd g:\test\proceedings
git status
git add -A
git commit -m "这里写你的改动说明"
git push
```
