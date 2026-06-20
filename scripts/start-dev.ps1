param(
    [int]$ApiPort = 8021,
    [int]$WebPort = 5175,
    [switch]$SkipApi,
    [switch]$SkipWeb
)

$script = Join-Path $PSScriptRoot "quant-dev.ps1"
& $script start -ApiPort $ApiPort -WebPort $WebPort -SkipApi:$SkipApi -SkipWeb:$SkipWeb
