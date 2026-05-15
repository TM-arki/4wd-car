$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$firmwareDir = Join-Path $repoRoot "firmware\pico_motor_controller"
$buildDir = Join-Path $firmwareDir "build"

cmake -S $firmwareDir -B $buildDir
cmake --build $buildDir
