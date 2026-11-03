<#
Deletes everything deploy.ps1 created, so nothing keeps using lab credits.
The database and all uploaded files are deleted permanently.

  .\infra\teardown.ps1          # asks for confirmation
  .\infra\teardown.ps1 -Yes     # no prompt
#>
param(
    [string]$Region = "us-east-1",
    [string]$Project = "predictwise",
    [switch]$Yes
)

$ErrorActionPreference = "Stop"

function Aws {
    & aws.exe @args --region $Region
    if ($LASTEXITCODE -ne 0) { throw "aws $($args[0]) $($args[1]) failed (exit $LASTEXITCODE)" }
}

function Stack-Exists([string]$Name) {
    $ErrorActionPreference = "Continue"
    $out = & aws.exe cloudformation describe-stacks --stack-name "$Project-$Name" --region $Region 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0) { return $true }
    # Only "does not exist" means gone. Any other error (expired credentials,
    # network) must stop the teardown, or it would wrongly report success.
    if ($out -match "does not exist") { return $false }
    throw "Could not check $Project-${Name}: $($out.Trim())"
}

function Remove-Stack([string]$Name) {
    if (-not (Stack-Exists $Name)) { Write-Host "$Project-$Name not found, skipping"; return }
    Write-Host "Deleting $Project-$Name ..." -ForegroundColor Cyan
    Aws cloudformation delete-stack --stack-name "$Project-$Name"
    Aws cloudformation wait stack-delete-complete --stack-name "$Project-$Name"
}

function Clear-Bucket([string]$Bucket) {
    # The bucket is versioned, so every old version and delete marker must go too.
    Write-Host "Emptying s3://$Bucket ..."
    $tmp = Join-Path $env:TEMP "predictwise-delete.json"
    while ($true) {
        $page = (Aws s3api list-object-versions --bucket $Bucket --max-items 500 --output json) -join "`n" | ConvertFrom-Json
        $objects = @()
        foreach ($v in @($page.Versions) + @($page.DeleteMarkers)) {
            if ($v) { $objects += @{ Key = $v.Key; VersionId = $v.VersionId } }
        }
        if ($objects.Count -eq 0) { break }
        # ASCII: Windows PowerShell's UTF-8 adds a byte-order mark the AWS CLI rejects.
        (@{ Objects = $objects; Quiet = $true } | ConvertTo-Json -Depth 4 -Compress) | Set-Content -Encoding Ascii $tmp
        Aws s3api delete-objects --bucket $Bucket --delete "file://$tmp" | Out-Null
    }
}

$ErrorActionPreference = "Continue"
& aws.exe sts get-caller-identity --region $Region 2>&1 | Out-Null
$ok = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $ok) {
    throw "AWS credentials are missing or expired. Start the Learner Lab, paste the new AWS CLI block into $HOME\.aws\credentials, then run this again. Nothing was deleted."
}

if (-not $Yes) {
    $answer = Read-Host "Delete ALL PredictWise AWS resources, including the database and uploaded files? Type yes"
    if ($answer -ne "yes") { Write-Host "Cancelled."; exit 1 }
}

Remove-Stack "monitoring"
Remove-Stack "app"
if (Stack-Exists "data") {
    $bucket = Aws cloudformation describe-stacks --stack-name "$Project-data" --output text `
        --query "Stacks[0].Outputs[?OutputKey=='DataBucket'].OutputValue | [0]"
    if ($bucket -and $bucket -ne "None") { Clear-Bucket $bucket }
}
Remove-Stack "data"
# Deleted secrets wait 7+ days for recovery by default, which would block a
# later redeploy with the same names. Purge them now.
foreach ($s in "$Project/db", "$Project/app") {
    $ErrorActionPreference = "Continue"
    & aws.exe secretsmanager delete-secret --secret-id $s --force-delete-without-recovery --region $Region 2>&1 | Out-Null
    $ErrorActionPreference = "Stop"
}
Remove-Stack "network"
Write-Host "`nAll PredictWise resources deleted." -ForegroundColor Green
