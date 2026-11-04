<#
Deploys PredictWise AI to AWS in four CloudFormation stacks:
  network -> data -> app -> monitoring

  .\infra\deploy.ps1                                  # lean mode, ~$0.08/hour (first run: ~30 minutes)
  .\infra\deploy.ps1 -Mode full                       # NAT gateway + private app subnets, 2 servers minimum, ~$0.16/hour
  .\infra\deploy.ps1 -AlertEmail you@example.com      # also email alarm notifications
  .\infra\deploy.ps1 -GroqApiKey gsk_...              # store an LLM key in Secrets Manager
  .\infra\deploy.ps1 -SkipRelease                     # change infrastructure only, keep the running app version

Re-running is safe: unchanged stacks are skipped, and a new app version is
rolled out one server at a time (rolled back automatically if it is unhealthy).
Needs the AWS CLI with credentials (AWS Academy: AWS Details -> AWS CLI -> Show).
#>
param(
    [string]$Region = "us-east-1",
    [string]$Project = "predictwise",
    [string]$AlertEmail = "",
    [string]$GroqApiKey = "",
    [string]$AnthropicApiKey = "",
    # lean: no NAT gateway, app servers in public subnets, 1 server until load rises. Switching modes needs teardown.ps1 first.
    [ValidateSet("lean", "full")][string]$Mode = "lean",
    [ValidateSet("true", "false")][string]$EnableCdn = "false",   # Learner Lab accounts cannot use CloudFront
    [ValidateSet("t3.micro", "t3.small", "t3.medium", "t3.large")][string]$InstanceType = "t3.small",
    [switch]$SkipRelease
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Aws {
    # aws.exe, not aws: PowerShell names are case-insensitive, so "aws" would call this function again.
    # Native commands do not throw in PowerShell; stop on the first AWS CLI failure.
    & aws.exe @args --region $Region
    if ($LASTEXITCODE -ne 0) { throw "aws $($args[0]) $($args[1]) failed (exit $LASTEXITCODE)" }
}

function Deploy-Stack([string]$Name, [string]$Template, [string[]]$Params) {
    Write-Host "`n==> $Project-$Name" -ForegroundColor Cyan
    $all = @("Project=$Project") + $Params
    Aws cloudformation deploy --stack-name "$Project-$Name" --template-file (Join-Path $PSScriptRoot $Template) `
        --parameter-overrides @all --no-fail-on-empty-changeset --tags "Project=$Project"
}

function Stack-Output([string]$Name, [string]$Key) {
    Aws cloudformation describe-stacks --stack-name "$Project-$Name" --output text `
        --query "Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue | [0]"
}

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI not found. Install it (winget install Amazon.AWSCLI), then reopen the terminal."
}
$account = Aws sts get-caller-identity --query Account --output text
Write-Host "Account $account, region $Region, $Mode mode" -ForegroundColor Green

# 1. Network: VPC, subnets, gateways, security groups, NACLs
$lean = ($Mode -eq "lean")
Deploy-Stack "network" "1-network.yaml" @("CreateNatGateway=$(if ($lean) { 'false' } else { 'true' })")

# 2. Data: S3, RDS PostgreSQL, Secrets Manager (RDS creation takes ~10 minutes)
$dataParams = @()
if ($GroqApiKey) { $dataParams += "GroqApiKey=$GroqApiKey" }
if ($AnthropicApiKey) { $dataParams += "AnthropicApiKey=$AnthropicApiKey" }
Deploy-Stack "data" "2-data.yaml" $dataParams
$bucket = Stack-Output "data" "DataBucket"

# 3. Package the app source and the Lambda, upload both to S3
$appParams = @("EnableCdn=$EnableCdn", "InstanceType=$InstanceType", "MinSize=$(if ($lean) { 1 } else { 2 })")
$work = Join-Path $env:TEMP "predictwise-release"
New-Item -ItemType Directory -Force $work | Out-Null

$zip = Join-Path $work "upload_profiler.zip"
Compress-Archive -Force -Path (Join-Path $PSScriptRoot "lambda\upload_profiler.py") -DestinationPath $zip
$lambdaHash = (Get-FileHash (Join-Path $PSScriptRoot "lambda\upload_profiler.py")).Hash.Substring(0, 12).ToLower()
$lambdaKey = "releases/lambda-$lambdaHash.zip"
Aws s3 cp $zip "s3://$bucket/$lambdaKey" --only-show-errors
$appParams += "LambdaCodeKey=$lambdaKey"

# Windows PowerShell turns redirected stderr into a terminating error under "Stop".
$ErrorActionPreference = "Continue"
& aws.exe cloudformation describe-stacks --stack-name "$Project-app" --region $Region 2>&1 | Out-Null
$stackExists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"

if ($SkipRelease -and $stackExists) {
    Write-Host "Keeping the currently deployed app version (-SkipRelease)."
} else {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $archive = Join-Path $work "app-$stamp.tar.gz"
    Write-Host "Packaging app source -> $archive"
    & "$env:SystemRoot\System32\tar.exe" -czf $archive -C $Root `
        --exclude=node_modules --exclude=dist --exclude=__pycache__ --exclude=.pytest_cache `
        --exclude=uploads --exclude=cleaned --exclude=artifacts --exclude=*.db --exclude=.env `
        Dockerfile .dockerignore backend frontend
    if ($LASTEXITCODE -ne 0) { throw "tar failed" }
    $releaseKey = "releases/app-$stamp.tar.gz"
    Aws s3 cp $archive "s3://$bucket/$releaseKey" --only-show-errors
    $appParams += "ReleaseKey=$releaseKey"
}

# 4. App: ALB, Auto Scaling group of EC2 + Docker, CloudFront, Lambda (first run ~15-20 minutes)
Write-Host "Servers build the app on first boot; this step waits until they report healthy."
Deploy-Stack "app" "3-app.yaml" $appParams

# 5. Monitoring: dashboard, alarms, SNS
$monParams = @()
if ($AlertEmail) { $monParams += "AlertEmail=$AlertEmail" }
Deploy-Stack "monitoring" "4-monitoring.yaml" $monParams

Write-Host "`nDone." -ForegroundColor Green
Write-Host ("App:           " + (Stack-Output "app" "AppUrl"))
Write-Host ("Load balancer: " + (Stack-Output "app" "LoadBalancerUrl"))
Write-Host ("Dashboard:     " + (Stack-Output "monitoring" "DashboardUrl"))
if ($AlertEmail) { Write-Host "Check $AlertEmail and click the AWS confirmation link to receive alerts." }
