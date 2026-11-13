# 统一构建入口：check（编译 + 测试 + lint 基线比对）/ build（PyInstaller 打包）/ clean（清理缓存与产物）
# 用法：pwsh -NoProfile -File build.ps1 check
param(
    [ValidateSet('build', 'check', 'clean')]
    [string]$Target = 'check',
    # 依赖按 Python 3.13 实盘 pin；多版本共存时可用 -Python 显式指定解释器
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
# 外部命令（ruff）以非 0 退出属于预期，不要在 PS7 里被自动提升为终止错误
$PSNativeCommandUseErrorActionPreference = $false

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $RepoRoot

$script:ExitCode = 0

function Assert-Python {
    # 门禁结果必须可复现：不同 Python 版本装到的 cv2 / numpy 行为不同，
    # 用 PATH 里偶然解析到的解释器跑测试会让「全绿」失去意义。
    # 用 Write-Host 输出而非 Write-Output：PowerShell 函数会把 Write-Output 的内容
    # 一起返回给调用方，污染 `if (Assert-Python)` 的布尔判断。
    $version = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0 -or "$version".Trim() -ne '3.13') {
        Write-Host "[check] 需要 Python 3.13（requirements 按此版本 pin），当前解释器: $version"
        return $false
    }
    Write-Host "[check] Python $version"
    return $true
}

function Invoke-Check {
    if (-not (Assert-Python)) {
        $script:ExitCode = 1
        return
    }
    Write-Output '[check] 1/3 compileall（跳过 build/dist/__pycache__）'
    & $Python -m compileall -q -x 'build|dist|__pycache__' .
    if ($LASTEXITCODE -ne 0) {
        Write-Output "[check] compileall 失败，退出码 $LASTEXITCODE"
        $script:ExitCode = 1
        return
    }

    Write-Output '[check] 2/3 pytest'
    # 每次用一个全新的空 basetemp：固定目录或系统 %TEMP% 会让 pytest 在启动时批量清理
    # 历史临时文件，受限会话里的批量删除守卫会把它判成 SystemExit(1)，用例其实全绿。
    # 新目录不存在，pytest 只创建、不删除；累积的目录由 clean 目标清理。
    $runTag = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + (Get-Random -Maximum 9999)
    & $Python -m pytest -q -p no:cacheprovider --basetemp=".pytest_tmp/run_$runTag"
    if ($LASTEXITCODE -ne 0) {
        Write-Output "[check] pytest 未全绿，退出码 $LASTEXITCODE"
        $script:ExitCode = 1
        return
    }

    Write-Output '[check] 3/3 ruff 与 .ruff_baseline 逐文件比对'
    $baselinePath = Join-Path $RepoRoot '.ruff_baseline'
    if (-not (Test-Path -LiteralPath $baselinePath)) {
        Write-Output '[check] 缺少 .ruff_baseline，无法比对'
        $script:ExitCode = 1
        return
    }

    $baseline = @{}
    # 显式 UTF-8：.ruff_baseline 含中文注释，PS 5.1 的 Get-Content 默认按 GBK 解码，
    # 会把注释行与配置行搅在一起（实测 Goldenhandmaidens.py=3 被漏读，误报「新增告警」）。
    foreach ($entry in [System.IO.File]::ReadAllLines(
            $baselinePath, [System.Text.Encoding]::UTF8)) {
        $trimmed = $entry.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
        $pair = $trimmed -split '=', 2
        if ($pair.Count -ne 2 -or $pair[1].Trim() -notmatch '^\d+$') {
            Write-Output "[check] .ruff_baseline 格式错误：$trimmed"
            $script:ExitCode = 1
            return
        }
        $baseline[$pair[0].Trim()] = [int]$pair[1].Trim()
    }

    # ruff 有存量告警时退出码非 0，属预期；只解析告警行，按文件计数
    $ruffOutput = & $Python -m ruff check . --output-format concise 2>&1
    $counts = @{}
    foreach ($line in $ruffOutput) {
        $text = [string]$line
        if ($text -match '^(?<file>[^:]+):(?<line>\d+):(?<col>\d+): (?<code>[A-Z]+\d+) ') {
            $file = $Matches['file']
            if ($counts.ContainsKey($file)) { $counts[$file] += 1 } else { $counts[$file] = 1 }
        }
    }

    # ruff 无告警时输出 "All checks passed!"、不产生可解析行；若两者都不成立，说明
    # ruff 没装或根本没跑起来——此时不能把「0 条」误判成基线一致。
    $ruffText = ($ruffOutput | ForEach-Object { [string]$_ }) -join "`n"
    if ($counts.Count -eq 0 -and $ruffText -notmatch 'All checks passed') {
        Write-Output '[check] ruff 未产生可解析输出（未安装或运行失败）'
        $script:ExitCode = 1
        return
    }

    $violations = @()
    foreach ($file in $counts.Keys) {
        $expected = if ($baseline.ContainsKey($file)) { $baseline[$file] } else { 0 }
        if ($counts[$file] -gt $expected) {
            $violations += [pscustomobject]@{
                File     = $file
                Baseline = $expected
                Current  = $counts[$file]
            }
        }
    }

    if ($violations.Count -gt 0) {
        foreach ($item in ($violations | Sort-Object File)) {
            $delta = $item.Current - $item.Baseline
            Write-Output "[check] 新增告警：$($item.File) 基线 $($item.Baseline) 条，当前 $($item.Current) 条（+$delta）"
        }
        Write-Output "[check] ruff 基线不一致：$($violations.Count) 个文件新增告警"
        $script:ExitCode = 1
        return
    }

    $total = ($counts.Values | Measure-Object -Sum).Sum
    if ($null -eq $total) { $total = 0 }
    Write-Output "[check] ruff 基线一致（全仓 $total 条，基线覆盖 $($baseline.Count) 个文件）"
}

function Invoke-BuildTarget {
    if (-not (Assert-Python)) {
        $script:ExitCode = 1
        return
    }
    # 必须走本脚本打包：根目录 goldenhandmaidens.exe 是用户日常双击的成品，
    # `--distpath .` 固定写这里。直接调 PyInstaller 只会更新 dist/，根目录会静默
    # 停留在旧版（2026-11-13 事故：修复明明已合入，实跑却仍用 11-11 的包）。
    Write-Output '[build] python -m PyInstaller goldenhandmaidens.spec --distpath . --workpath build --noconfirm'
    # PyInstaller 把所有进度日志写在 stderr。PS 5.1 在 $ErrorActionPreference='Stop' 下
    # 会把原生命令的 stderr 当成终止错误（NativeCommandError），打包必然假失败；
    # PS 7 才认 $PSNativeCommandUseErrorActionPreference。这里临时降级，
    # 成败只看 $LASTEXITCODE。
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Python -m PyInstaller goldenhandmaidens.spec --distpath . --workpath build --noconfirm
    } finally {
        $ErrorActionPreference = $previousEap
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Output "[build] 打包失败，退出码 $LASTEXITCODE"
        $script:ExitCode = 1
        return
    }

    $rootExe = Join-Path $RepoRoot 'goldenhandmaidens.exe'
    $distDir = Join-Path $RepoRoot 'dist'
    if (-not (Test-Path -LiteralPath $distDir)) {
        New-Item -ItemType Directory -Path $distDir | Out-Null
    }
    $distExe = Join-Path $distDir 'goldenhandmaidens.exe'
    # 两份成品分叉 = 「改了代码却跑旧包」的假回归。强制同步并校验哈希。
    Copy-Item -LiteralPath $rootExe -Destination $distExe -Force
    $hashRoot = (Get-FileHash -LiteralPath $rootExe -Algorithm SHA256).Hash
    $hashDist = (Get-FileHash -LiteralPath $distExe -Algorithm SHA256).Hash
    if ($hashRoot -ne $hashDist) {
        Write-Output '[build] 根目录与 dist/ 成品哈希不一致，同步失败'
        $script:ExitCode = 1
        return
    }
    $stamp = (Get-Item -LiteralPath $rootExe).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
    Write-Output "[build] 成品: 根目录 goldenhandmaidens.exe（打包于 $stamp）"
    Write-Output "[build] 已同步 dist/，SHA256 $($hashRoot.Substring(0, 12))…"
}

function Invoke-Clean {
    # 只清已知的缓存/中间目录，绝不触碰根目录成品 exe 与 templates/
    $targets = @('build', 'dist', '.pytest_cache', '.pytest_tmp', '.ruff_cache')
    foreach ($name in $targets) {
        $path = Join-Path $RepoRoot $name
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
            Write-Output "[clean] 已清理 $name"
        }
    }

    $pycacheDirs = @(Get-ChildItem -LiteralPath $RepoRoot -Directory -Recurse -Force -Filter '__pycache__' -ErrorAction SilentlyContinue)
    foreach ($dir in $pycacheDirs) {
        Remove-Item -LiteralPath $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Output "[clean] 已清理 __pycache__ 目录 $($pycacheDirs.Count) 个"
}

switch ($Target) {
    'check' { Invoke-Check }
    'build' { Invoke-BuildTarget }
    'clean' { Invoke-Clean }
}

exit $script:ExitCode
