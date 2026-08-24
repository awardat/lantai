# 兰台单轨发布脚本（0.1.22 起，CH-041/CH-044）
# 用法：pwsh scripts/build_release.ps1 [-Version 0.1.24]
# 流程：PyInstaller 服务 one-dir（临时目录）→ 布局修正 → 组装壳目录 → 清理中间产物
#       → zip → 发行物校验（无 data/、无 settings.json、无服务版目录残留）
# 前置：shell 已 cargo build --release（壳 exe 在 shell/src-tauri/target/release/）
param([string]$Version = "0.1.23")

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tmpSvc = Join-Path $env:TEMP "lantai-svc-$Version"      # 服务 one-dir 临时目录
$svcOut = Join-Path $root "release\lantai-$Version-windows-x64"  # 中间目录（构建后即删）
$dst = Join-Path $root "release\lantai-shell-$Version-windows-x64"
$zip = "$dst.zip"

Write-Host "== 兰台单轨发布 $Version =="

# 1. 清理旧产物
foreach ($p in @($tmpSvc, $svcOut, $dst, $zip)) {
    if (Test-Path $p) { Remove-Item $p -Recurse -Force }
}

# 2. PyInstaller 服务 one-dir（临时目录）
Write-Host "[1/6] PyInstaller 服务 one-dir..."
& (Join-Path $root "backend\.venv\Scripts\python.exe") -m PyInstaller --noconfirm `
    --distpath $svcOut --workpath (Join-Path $root "scripts\build\build-work-$Version") `
    (Join-Path $root "scripts\build\lantai.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }

# 3. 布局修正（COLLECT 子目录上移）
$sub = Join-Path $svcOut "lantai"
if (Test-Path $sub) {
    Move-Item "$sub\*" $svcOut -Force
    Remove-Item $sub -Force
}

# 4. 运行说明（上一版复制 + 版本号替换）
$prev = Get-ChildItem (Join-Path $root "release") -Directory -Filter "lantai-shell-*" |
    Where-Object { $_.Name -match '(\d+\.\d+\.\d+)' -and $_.Name -notlike "*$Version*" } |
    Sort-Object Name | Select-Object -Last 1
if ($prev) {
    Copy-Item (Join-Path $prev.FullName "运行说明.txt") $svcOut -Force
    $t = Get-Content (Join-Path $svcOut "运行说明.txt") -Raw -Encoding UTF8
    $prevVer = [regex]::Match($prev.Name, '(\d+\.\d+\.\d+)').Groups[1].Value
    $t = $t -replace "v$prevVer", "v$Version"
    Set-Content (Join-Path $svcOut "运行说明.txt") $t -Encoding UTF8 -NoNewline
}

# 5. 组装壳目录（单轨：壳 + 服务一体）
Write-Host "[2/6] 组装壳目录..."
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item (Join-Path $root "shell\src-tauri\target\release\lantai-shell.exe") $dst
Copy-Item (Join-Path $root "shell\src-tauri\target\release\WebView2Loader.dll") $dst
New-Item -ItemType File -Path (Join-Path $dst "portable.marker") -Force | Out-Null
Copy-Item "$svcOut\*" $dst -Recurse -Force

# 6. 清理中间产物（单轨：不留服务版目录）
Write-Host "[3/6] 清理中间产物..."
Remove-Item $svcOut -Recurse -Force
Remove-Item (Join-Path $root "scripts\build\build-work-$Version") -Recurse -Force -ErrorAction SilentlyContinue

# 7. zip
Write-Host "[4/6] 打包 zip..."
Compress-Archive -Path $dst -DestinationPath $zip -Force

# 8. 发行物校验（硬性条款：无 data/、无 settings.json、无服务版目录）
Write-Host "[5/6] 发行物校验..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [System.IO.Compression.ZipFile]::OpenRead($zip)
$bad = $z.Entries | Where-Object { $_.FullName -match '/data/|settings\.json' }
$z.Dispose()
if ($bad) { throw "!! zip 含残留: $($bad.FullName -join ',')" }
if (Test-Path $svcOut) { throw "!! 服务版目录残留: $svcOut" }
Write-Host "    zip 干净 ✅ 服务版目录已清理 ✅"

# 9. 汇总
Write-Host "[6/6] 完成：$zip（$([math]::Round((Get-Item $zip).Length/1MB,1)) MB）"
Write-Host "== 记得：版本号同步（config/壳三处/README/API/版本记录/CH/AGENTS）+ 自测 + git 提交 =="
