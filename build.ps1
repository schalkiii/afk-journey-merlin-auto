# 统一构建入口：check（编译 + 测试 + lint 基线比对）/ build（PyInstaller 打包）/ clean（清理缓存与产物）
# 用法：pwsh -NoProfile -File build.ps1 check
param(
    [ValidateSet('build', 'check', 'clean')]
    [string]$Target = 'check'
)

$ErrorActionPreference = 'Stop'
# 外部命令（ruff）以非 0 退出属于预期，不要在 PS7 里被自动提升为终止错误
$PSNativeCommandUseErrorActionPreference = $false

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $RepoRoot

$script:ExitCode = 0

function Invoke-Check {
    Write-Output '[check] 1/3 compileall（跳过 build/dist/__pycache__）'
    & python -m compileall -q -x 'build|dist|__pycache__' .
    if ($LASTEXITCODE -ne 0) {
        Write-Output "[check] compileall 失败，退出码 $LASTEXITCODE"
        $script:ExitCode = 1
        return
    }

    Write-Output '[check] 2/3 pytest'
    & python -m pytest -q -p no:cacheprovider
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
    foreach ($entry in Get-Content -LiteralPath $baselinePath) {
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
    $ruffOutput = & python -m ruff check . --output-format concise 2>&1
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
    Write-Output '[build] python -m PyInstaller goldenhandmaidens.spec --distpath . --workpath build --noconfirm'
    & python -m PyInstaller goldenhandmaidens.spec --distpath . --workpath build --noconfirm
    if ($LASTEXITCODE -ne 0) {
        Write-Output "[build] 打包失败，退出码 $LASTEXITCODE"
        $script:ExitCode = 1
        return
    }
    Write-Output '[build] 打包完成，产物在仓库根 goldenhandmaidens.exe'
}

function Invoke-Clean {
    # 只清已知的缓存/中间目录，绝不触碰根目录成品 exe 与 templates/
    $targets = @('build', 'dist', '.pytest_cache', '.ruff_cache')
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
