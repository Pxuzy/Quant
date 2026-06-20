param(
    [int]$ApiPort = 8021,
    [int]$WebPort = 5175
)

$script = Join-Path $PSScriptRoot "quant-dev.ps1"
& $script start-bg -ApiPort $ApiPort -WebPort $WebPort
