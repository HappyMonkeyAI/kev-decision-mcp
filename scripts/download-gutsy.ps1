$ErrorActionPreference = 'Stop'
$revision = 'bb1dde4c571b2588801c27d155da005a87d05285'
$root = Join-Path (Split-Path $PSScriptRoot -Parent) '.cache/gutsy'
$metadata = Invoke-RestMethod "https://huggingface.co/api/models/kouhxp/gutsy/revision/$revision"
$files = @($metadata.siblings.rfilename | Where-Object { $_ -match '^gutsy-inference/(gutsy_inference/[^/]+\.py|pyproject.toml|README.md)$' })
$files += 'gutsy-0.8b-v04-q8_0.gguf', 'gutsy-0.8b-v04.calibration.json'
foreach ($file in $files) {
    $relative = if ($file.StartsWith('gutsy-inference/')) { 'runtime/' + $file.Substring(16) } else { 'models/' + $file }
    $target = Join-Path $root $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
    if (-not (Test-Path -LiteralPath $target)) {
        Write-Output "Downloading $file"
        Invoke-WebRequest "https://huggingface.co/kouhxp/gutsy/resolve/$revision/$file" -OutFile "$target.partial"
        Move-Item -LiteralPath "$target.partial" -Destination $target
    }
}
$hashes = @{}
Get-ChildItem -LiteralPath $root -File -Recurse | Where-Object { $_.Name -ne 'provenance.json' } | ForEach-Object {
    $hashes[$_.FullName.Substring($root.Length + 1)] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()
}
@{ repository='kouhxp/gutsy'; revision=$revision; sha256=$hashes } | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $root 'provenance.json')
Write-Output 'Gutsy runtime and Q8_0 model downloaded; revision and hashes saved.'
