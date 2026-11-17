param([string]$Python='.venv/Scripts/python.exe',[string]$PreviousVersion='')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$sourceCommit=(& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceCommit -notmatch '^[a-f0-9]{40}$') { throw 'A committed source revision is required' }
if (& git status --porcelain) { throw 'Commit all reviewed source before building' }
if ($PreviousVersion -and $PreviousVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid previous release version' }
$releaseManifest=Get-Content -LiteralPath packaging/release-inputs.json -Raw | ConvertFrom-Json
$releaseVersion=$releaseManifest.releaseVersion
$releaseKind=if ($PreviousVersion) { 'patch' } else { 'release' }
$compilerArgs=@("/DAppVersion=$releaseVersion")
if ($PreviousVersion) {
 $previous=[version]$PreviousVersion; $next=[version]$releaseVersion
 if ($next.Major -ne $previous.Major -or $next.Minor -ne $previous.Minor -or $next.Build -ne ($previous.Build+1)) { throw 'A patch must increment only the patch number by one' }
 $compilerArgs+="/DPatchFromVersion=$PreviousVersion"
}
& $Python tools/verify_release_inputs.py
if ($LASTEXITCODE -ne 0) { throw 'Release provenance is incomplete or changed' }
& $Python tools/dependency_policy.py
if ($LASTEXITCODE -ne 0) { throw 'Dependency policy failed' }
& $Python -m PyInstaller --noconfirm --distpath packaging/dist --workpath packaging/build packaging/companion.spec
if ($LASTEXITCODE -ne 0) { throw 'Companion build failed' }
& $Python packaging_audit.py packaging/dist/ClipBotCompanion
if ($LASTEXITCODE -ne 0) { throw 'Bundle audit failed' }
& packaging/tools/compiler/ISCC.exe @compilerArgs packaging/clipbot-companion.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
$artifact=Get-Item -LiteralPath packaging/dist/ClipBotCompanionSetup.exe
$installerSigned=(Get-AuthenticodeSignature -LiteralPath $artifact.FullName).Status -eq 'Valid'
@{version=$releaseVersion;channel='internal';releaseKind=$releaseKind;previousVersion=$PreviousVersion;sourceCommit=$sourceCommit;provenanceVerified=$true;cleanMachineAccepted=$false;sha256=(Get-FileHash -LiteralPath $artifact.FullName -Algorithm SHA256).Hash.ToLower();sizeBytes=$artifact.Length;signed=$installerSigned} | ConvertTo-Json | Set-Content -LiteralPath packaging/dist/manifest.json
