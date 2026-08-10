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

## 三、如何确认部署成功 / 排查失败

- **Actions 标签页**(`仓库页顶部 → Actions`):
  - 绿色 ✅ = 成功;红色 ❌ = 失败;黄色转圈 = 正在跑。
- 点进某条记录,左侧是各步骤(拉取代码 → 安装依赖 → 运行抓取 → 提交数据 → 部署),点步骤可看日志。
- 最后一步 `deploy` 成功 = 网站已发布。

---

## 四、哪些改动需要 push?

| 改动内容 | 需要 push 吗 | 说明 |
|---|---|---|
| `site/` 前端(html/css/js) | ✅ 需要 | push 后 Actions 自动部署新界面 |
| `scraper/` 抓取脚本 | ✅ 需要 | 新脚本推上去后,云端才会用它抓 |
| `.github/workflows/` 工作流 | ✅ 需要 | 同上 |
| `site/data/papers.json` 论文数据 | ❌ 不需要 | Actions 每月自动抓取、自动提交、自动部署 |
| README、文档 | 随意 | 想备份就 push |

---

## 五、常见报错自查

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
cd g:\test\proceedings
git status
git add -A
git commit -m "这里写你的改动说明"
git push
```
