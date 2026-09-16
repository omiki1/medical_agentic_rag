# Prepare slim model directory for upload (ASCII-only to avoid PS 5.1 encoding issues).
# Usage: powershell -ExecutionPolicy Bypass -File deploy\prepare-models.ps1
$ErrorActionPreference = 'Stop'

$dst = Join-Path $PSScriptRoot 'models'
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
New-Item -ItemType Directory -Force -Path $dst | Out-Null

$models = @(
    @{
        Src         = 'C:\model\paraphrase-multilingual-MiniLM-L12-v2'
        Name        = 'paraphrase-multilingual-MiniLM-L12-v2'
        RemoveFiles = @('tf_model.h5', 'pytorch_model.bin')
        RemoveDirs  = @('onnx', 'openvino', '.cache')
    },
    @{
        Src         = 'C:\model\bge-reranker-large'
        Name        = 'bge-reranker-large'
        RemoveFiles = @('pytorch_model.bin', 'tf_model.h5')
        RemoveDirs  = @('onnx', 'openvino', '.cache')
    }
)

$total = 0
foreach ($m in $models) {
    if (-not (Test-Path -LiteralPath $m.Src)) { throw "Source dir missing: $($m.Src)" }
    $target = Join-Path $dst $m.Name

    Write-Host "Copying $($m.Name) ..."
    Copy-Item -LiteralPath $m.Src -Destination $target -Recurse -Force

    foreach ($d in $m.RemoveDirs) {
        $p = Join-Path $target $d
        if (Test-Path -LiteralPath $p) {
            Remove-Item -LiteralPath $p -Recurse -Force
            Write-Host "  - removed dir $d"
        }
    }
    foreach ($f in $m.RemoveFiles) {
        $found = Get-ChildItem -LiteralPath $target -Recurse -File -Filter $f -ErrorAction SilentlyContinue
        foreach ($item in $found) {
            Remove-Item -LiteralPath $item.FullName -Force
            Write-Host ("  - removed {0} ({1:N0} MB)" -f $item.Name, ($item.Length / 1MB))
        }
    }
    Get-ChildItem -LiteralPath $target -Recurse -Force -Filter '.git*' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    $size = (Get-ChildItem -LiteralPath $target -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB
    $total += $size
    Write-Host ("{0,-46} {1,8:N0} MB" -f $m.Name, $size)
}

$must = @(
    'paraphrase-multilingual-MiniLM-L12-v2\model.safetensors',
    'paraphrase-multilingual-MiniLM-L12-v2\config.json',
    'paraphrase-multilingual-MiniLM-L12-v2\modules.json',
    'paraphrase-multilingual-MiniLM-L12-v2\tokenizer_config.json',
    'paraphrase-multilingual-MiniLM-L12-v2\1_Pooling\config.json',
    'bge-reranker-large\model.safetensors',
    'bge-reranker-large\config.json',
    'bge-reranker-large\tokenizer.json',
    'bge-reranker-large\tokenizer_config.json'
)
foreach ($rel in $must) {
    $p = Join-Path $dst $rel
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Required file missing: $rel" }
}
Write-Host "Required-file check passed" -ForegroundColor Green

$forbidden = @(
    'paraphrase-multilingual-MiniLM-L12-v2\tf_model.h5',
    'paraphrase-multilingual-MiniLM-L12-v2\pytorch_model.bin',
    'bge-reranker-large\pytorch_model.bin'
)
foreach ($rel in $forbidden) {
    $p = Join-Path $dst $rel
    if (Test-Path -LiteralPath $p) { throw "Redundant file still present: $rel" }
}
Write-Host "Redundant-weight check passed" -ForegroundColor Green

Write-Host ""
Write-Host ("Total model size: {0:N0} MB -> {1}" -f $total, $dst) -ForegroundColor Green
