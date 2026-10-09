# Aadesh SAM Deployment Script
$ErrorActionPreference = "Stop"

$SamCli = "C:\Program Files\Amazon\AWSSAMCLI\bin\sam.cmd"
$Region = "ap-south-1"
$StackName = "aadesh-dev"

Set-Location "C:\Users\clash\Documents\AADHESH\infra\aws"

Write-Host "Building..." -ForegroundColor Cyan
& $SamCli build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Deploying..." -ForegroundColor Cyan
& $SamCli deploy --stack-name $StackName --region $Region --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM --resolve-s3 --parameter-overrides "Environment=dev CorpusBackend=s3 ExplainBackend=deterministic"
exit $LASTEXITCODE
