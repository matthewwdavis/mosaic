# Installs (or updates) mosaic on Windows with one line in PowerShell:
#
#   irm https://raw.githubusercontent.com/matthewwdavis/mosaic/main/install.ps1 | iex
#
# It downloads the newest release into a temporary folder and runs that release's
# install-windows.bat, the same installer the README's step-by-step install uses, then deletes
# the temporary folder. A file downloaded this way isn't marked as coming from the internet, so
# Windows doesn't show its "protected your PC" warning.
#
# Everything runs inside one script block, so an error stops this script without closing the
# PowerShell window it was pasted into.
& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is many times slower while drawing its progress bar
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $url = 'https://github.com/matthewwdavis/mosaic/releases/latest/download/mosaic.zip'
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('mosaic-install-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        Write-Host ''
        Write-Host '==> Downloading the newest mosaic'
        $zip = Join-Path $tmp 'mosaic.zip'
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $tmp
        $dir = Get-ChildItem -Path $tmp -Directory -Filter 'mosaic-*' | Select-Object -First 1
        $bat = if ($dir) { Join-Path $dir.FullName 'install-windows.bat' } else { $null }
        if (-not $bat -or -not (Test-Path $bat)) {
            throw "The download didn't contain install-windows.bat; please report this (see the README's Feedback section)."
        }
        & $bat
    }
    finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}
