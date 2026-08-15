# ClinProc 一键推送脚本
# 自动完成:git add -A → commit → pull --rebase → push
# 用法:双击 auto-push.bat;或在 PowerShell 中 .\auto_push.ps1 "自定义提交说明"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "  ClinProc Auto Push" -ForegroundColor Cyan
Write-Host "  ==================" -ForegroundColor Cyan
Write-Host ""

# 1) 加入所有改动
git add -A

# 2) 没有改动则直接退出
$status = git status --porcelain
if (-not $status) {
    Write-Host "[跳过] 本地没有任何改动,不需要推送。" -ForegroundColor Yellow
    exit 0
}

Write-Host "[1/4] 检测到以下改动:" -ForegroundColor Green
git status --short
Write-Host ""

# 3) 提交(可传参自定义说明,否则自动生成带时间戳的说明)
$msg = $args[0]
if (-not $msg) {
    $msg = "chore: auto push updates @ $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}
git commit -m $msg
if ($LASTEXITCODE -ne 0) {
    Write-Host "[失败] commit 出错,见上方信息。" -ForegroundColor Red
    exit 1
}
Write-Host "[2/4] 本地提交完成:$msg" -ForegroundColor Green

# 4) 先同步云端再推送(Actions 会自动提交数据,直接 push 可能被拒绝)
Write-Host "[3/4] 同步云端 (pull --rebase) ..." -ForegroundColor Green
git pull --rebase origin master
if ($LASTEXITCODE -ne 0) {
    Write-Host "[失败] pull 出错,见上方信息。" -ForegroundColor Red
    exit 1
}

Write-Host "[4/4] 推送到 GitHub ..." -ForegroundColor Green
git push origin master
if ($LASTEXITCODE -ne 0) {
    Write-Host "[失败] push 出错。注意:本机必须走 SSH 地址,见指南第七节。" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  推送成功!网站将在 2-5 分钟内自动更新。" -ForegroundColor Cyan
Write-Host "  进度查看:https://github.com/jinbeiwang/Proceedings/actions" -ForegroundColor DarkGray
Write-Host ""
exit 0
