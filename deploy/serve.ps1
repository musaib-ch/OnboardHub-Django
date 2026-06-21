# Run OnboardHub in production mode behind a Cloudflare Tunnel (Windows).
#
#   .\deploy\serve.ps1
#
# Loads .env, applies migrations, collects static files, then serves the WSGI
# app with waitress on 127.0.0.1:8000 (the port cloudflared forwards to).

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

# Load .env into the process environment
if (Test-Path "$root\.env") {
    Get-Content "$root\.env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $k, $v = $line.Split("=", 2)
            [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim())
        }
    }
}

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# waitress is a pure-Python, cross-platform WSGI server (gunicorn is Linux-only).
python -m waitress --listen=127.0.0.1:8000 onboardhub.wsgi:application
