# 兰台 0.1.19 快速回归：--server 模式 + Mock AI 全链路（上传→解析→问答）
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8000'
$mock = 'http://127.0.0.1:18000'
$venv = 'C:\code\lantai\backend\.venv\Scripts\python.exe'

# 0. 清理
Get-NetTCPConnection -LocalPort 8000,18000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

# 1. 启动 Mock AI
$m = Start-Process -FilePath $venv -ArgumentList 'C:\code\lantai\scripts\mock_ai_server.py','--port','18000' -PassThru -WindowStyle Hidden
# 2. 启动服务（--server 模式）
$s = Start-Process -FilePath $venv -ArgumentList 'C:\code\lantai\backend\run.py','--server' -PassThru -WorkingDirectory 'C:\code\lantai\backend' -WindowStyle Hidden
Start-Sleep -Seconds 8

# 3. 登录
$sess = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$login = Invoke-RestMethod -Uri "$base/api/settings/verify" -Method Post -Body (@{password='Admin#123'} | ConvertTo-Json) -ContentType 'application/json' -WebSession $sess
if ($login.code -ne 0) { throw "登录失败: $login" }

# 4. AI 配置指向 Mock
$cfg = @{}
foreach ($k in @('text','office','pdf_text','image','pdf_image','chat','embedding')) {
    $cfg[$k] = @{ provider='openai-compatible'; base_url=$mock; api_key='mock'; model= if($k -eq 'embedding'){'mock-embed'}else{'mock-chat'} }
}
$put = Invoke-RestMethod -Uri "$base/api/settings/ai" -Method Put -Body (@{items=$cfg} | ConvertTo-Json -Depth 4) -ContentType 'application/json' -WebSession $sess
if ($put.code -ne 0) { throw "AI 配置失败: $put" }
Write-Host "AI 配置已指向 Mock ✓"

# 5. 上传测试文档
$doc = 'C:\code\lantai\sample\_regress_019.txt'
Set-Content -Path $doc -Value "兰台测试文档：激光雷达点云分类方法研究。点云数据包含地面点、建筑物点和植被点，分类精度达到 95%。" -Encoding UTF8
$form = @{ file = Get-Item $doc }
$up = Invoke-RestMethod -Uri "$base/api/docs/upload" -Method Post -Form $form -WebSession $sess
if ($up.code -ne 0) { throw "上传失败: $up" }
$docId = $up.data.id
Write-Host "上传成功 doc=$docId ✓"

# 6. 轮询解析
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    $list = Invoke-RestMethod -Uri "$base/api/docs" -Method Get -WebSession $sess
    $d = $list.data | Where-Object { $_.id -eq $docId }
    if ($d.status -eq 'ready') { $ready = $true; break }
    if ($d.status -eq 'failed') { throw "解析失败: $d" }
}
if (-not $ready) { throw "解析超时" }
Write-Host "解析完成（状态 ready）✓"

# 7. 问答（非流式）
$q = Invoke-RestMethod -Uri "$base/api/chat" -Method Post -Body (@{question='点云分类有哪些类别？'} | ConvertTo-Json) -ContentType 'application/json' -WebSession $sess
if ($q.code -ne 0) { throw "问答失败: $q" }
$answer = $q.data.answer
Write-Host "问答回答: $answer"
if ($answer -notmatch 'mock' -and $answer -notmatch 'Mock' -and $answer -notmatch 'mock-chat') { Write-Host "（Mock 回复特征未命中，仅为提示）" }

# 8. 清理
Remove-Item $doc -Force -ErrorAction SilentlyContinue
Stop-Process -Id $s.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $m.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Write-Host "清理完成，8000 占用: $([bool](Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue))"
Write-Host "=== 回归通过 ==="
