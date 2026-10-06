$ErrorActionPreference = 'Stop'
$lock = Get-Content (Join-Path $PSScriptRoot 'gutsy-lock.json') -Raw | ConvertFrom-Json
$revision = $lock.revision
$root = Join-Path (Split-Path $PSScriptRoot -Parent) '.cache/gutsy'
$metadata = Invoke-RestMethod "https://huggingface.co/api/models/kouhxp/gutsy/revision/$revision"
if ($metadata.sha -cne $revision) { throw "Hugging Face returned revision '$($metadata.sha)', expected '$revision'." }
$files = @($metadata.siblings.rfilename | Where-Object { $_ -match '^gutsy-inference/(gutsy_inference/[^/]+\.py|pyproject\.toml|README\.md)$' })
$files += 'gutsy-0.8b-v04-q8_0.gguf', 'gutsy-0.8b-v04.calibration.json'
$paths = @{}
foreach ($file in $files) {
    $relative = if ($file.StartsWith('gutsy-inference/')) { 'runtime/' + $file.Substring(16) } else { 'models/' + $file }
    $paths[$file] = $relative
}
$remotePaths = @($paths.Values | Sort-Object) -join "`n"
$lockedPaths = @($lock.sha256.PSObject.Properties.Name | Sort-Object) -join "`n"
if ($remotePaths -cne $lockedPaths) { throw 'Pinned file list does not match the locked SHA-256 manifest.' }

foreach ($file in $files) {
    $relative = $paths[$file]
    $target = Join-Path $root $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
    if (-not (Test-Path -LiteralPath $target)) {
        Write-Output "Downloading $file"
        $partial = "$target.partial"
        try {
            Invoke-WebRequest "https://huggingface.co/kouhxp/gutsy/resolve/$revision/$file" -OutFile $partial
            $actual = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
            $expected = $lock.sha256.$relative
            if ($actual -cne $expected) { throw "SHA-256 mismatch for ${file}: expected ${expected}, got ${actual}" }
            Move-Item -LiteralPath $partial -Destination $target
        } finally {
            Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
        }
    }
    $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    $expected = $lock.sha256.$relative
    if ($actual -cne $expected) { throw "SHA-256 mismatch for cached ${file}: expected ${expected}, got ${actual}" }
}

@{ repository=$lock.repository; revision=$revision; sha256=$lock.sha256 } |
    ConvertTo-Json -Depth 5 | Set-Content (Join-Path $root 'provenance.json')
Write-Output 'Gutsy runtime and Q8_0 model verified; provenance saved.'
