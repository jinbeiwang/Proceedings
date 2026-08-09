# auto_scrape_and_shutdown.ps1
# 自动运行所有爬虫任务,完成后关机
# 用法: powershell -ExecutionPolicy Bypass -File auto_scrape_and_shutdown.ps1

$ErrorActionPreference = "Continue"
$scraperDir = "d:\gpt_work\proceedings\scraper"
$logFile = "d:\gpt_work\proceedings\scrape_log.txt"

function Write-Log {
    param([string]$msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Write-Log "=========================================="
Write-Log "开始自动爬虫任务"
Write-Log "=========================================="

# Step 1: 运行 SGF spider (补充 2009-2021 年论文)
Write-Log "Step 1: 运行 SGF spider..."
Set-Location $scraperDir
python main.py -c sgf 2>&1 | ForEach-Object { 
    Write-Host $_
    Add-Content -Path $logFile -Value $_ -Encoding UTF8
}
Write-Log "SGF spider 完成"

# Step 2: 运行 Wayback PharmaSUG spider (恢复旧年份论文)
Write-Log "Step 2: 运行 Wayback PharmaSUG spider..."
python main.py -c pharmasug-wayback 2>&1 | ForEach-Object { 
    Write-Host $_
    Add-Content -Path $logFile -Value $_ -Encoding UTF8
}
Write-Log "Wayback PharmaSUG spider 完成"

# Step 3: 检查结果
Write-Log "Step 3: 检查结果..."
$papersFile = "d:\gpt_work\proceedings\site\data\papers.json"
if (Test-Path $papersFile) {
    $data = Get-Content $papersFile -Raw | ConvertFrom-Json
    Write-Log "总论文数: $($data.Count)"
    
    $byConf = $data | Group-Object conference | Sort-Object Count -Descending
    foreach ($group in $byConf) {
        Write-Log "  $($group.Name): $($group.Count) 篇"
    }
    
    $byYear = $data | Group-Object year | Sort-Object Name
    Write-Log "年份分布:"
    foreach ($group in $byYear) {
        Write-Log "  $($group.Name): $($group.Count) 篇"
    }
}

Write-Log "=========================================="
Write-Log "所有爬虫任务完成!"
Write-Log "=========================================="

# 等待 30 秒让用户看到结果
Write-Log "30 秒后关机..."
Start-Sleep -Seconds 30

# 关机
Write-Log "正在关机..."
shutdown /s /t 60 /c "爬虫任务完成,系统将在 60 秒后关机。如需取消,请运行 shutdown /a"
