# Scrape all open job-posting tabs from Chrome using the DevTools Protocol.
# Runs natively on Windows (no WSL networking needed).
#
# Usage from WSL:
#   python3 scripts/scrape_open_tabs.py
# (which calls this script automatically)
#
# Or run directly from Windows PowerShell:
#   powershell.exe -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\ytmikey\projects\job-search-agent\scripts\chrome_scrape.ps1"

param(
    [string]$OutFile = "$env:TEMP\job_scrape_results.json",
    [int]$Port = 9222
)

# ── 1. Ensure Chrome is running with remote debugging ──────────────────────

$chromeExe = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $chromeExe) {
    Write-Error "Chrome not found."; exit 1
}

function Test-Port($p) {
    try {
        $t = [System.Net.Sockets.TcpClient]::new("127.0.0.1", $p)
        $t.Close(); return $true
    } catch { return $false }
}

if (-not (Test-Port $Port)) {
    Write-Host "Chrome not running with debug port."

    # Kill ALL Chrome processes and wait until none remain
    $running = Get-Process chrome -ErrorAction SilentlyContinue
    if ($running) {
        Write-Host "Closing $($running.Count) Chrome process(es)..."
        $running | Stop-Process -Force
        Write-Host "Waiting for Chrome to fully exit..."
        $deadline = (Get-Date).AddSeconds(15)
        while (Get-Process chrome -ErrorAction SilentlyContinue) {
            if ((Get-Date) -gt $deadline) {
                Write-Error "Chrome did not exit within 15 seconds. Try closing it manually and re-running."; exit 1
            }
            Start-Sleep -Milliseconds 300
        }
        Write-Host "Chrome exited."
    }

    Start-Sleep -Seconds 1
    Write-Host "Launching Chrome with remote debugging on port $Port..."
    Start-Process $chromeExe -ArgumentList @(
        "--remote-debugging-port=$Port",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "--restore-last-session"
    )

    # Wait until the debug port is actually listening (up to 30s)
    Write-Host "Waiting for Chrome debug port to open..."
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-Port $Port)) {
        if ((Get-Date) -gt $deadline) {
            Write-Error "Chrome debug port did not open within 30 seconds."; exit 1
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "Chrome is ready!"
    Write-Host ""
    Write-Host "Please open all your job posting tabs, then press Enter here to scrape them..."
    Read-Host | Out-Null
}

# ── 2. Get tab list via HTTP ───────────────────────────────────────────────

$tabs = $null
for ($i = 0; $i -lt 10; $i++) {
    try {
        $tabs = Invoke-RestMethod "http://localhost:$Port/json/list" -ErrorAction Stop
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $tabs) {
    Write-Error "Could not reach Chrome CDP at port $Port after retries."; exit 1
}

Write-Host "Found $($tabs.Count) open tab(s)."

# ── 3. Filter to job-posting tabs ─────────────────────────────────────────

$jobPatterns = @(
    "linkedin\.com/(jobs/view|comm/jobs/view)/",
    "boards\.greenhouse\.io/",
    "jobs\.lever\.co/",
    "jobs\.ashbyhq\.com/",
    "/jobs/",
    "/careers/",
    "myworkdayjobs\.com/"
)

$jobTabs = $tabs | Where-Object {
    $url = $_.url
    $jobPatterns | Where-Object { $url -match $_ }
}

Write-Host "Found $($jobTabs.Count) job tab(s)."

# ── 4. Extract content via WebSocket CDP ──────────────────────────────────

function Invoke-CDP($wsUrl, $method, $params = @{}) {
    $ws = [System.Net.WebSockets.ClientWebSocket]::new()
    $cts = [System.Threading.CancellationTokenSource]::new(10000)
    $ws.ConnectAsync([Uri]$wsUrl, $cts.Token).Wait()

    $msg = @{ id = 1; method = $method; params = $params } | ConvertTo-Json -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($msg)
    $seg = [ArraySegment[byte]]::new($bytes)
    $ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cts.Token).Wait()

    $buf = [byte[]]::new(1MB)
    $result = ""
    do {
        $recv = $ws.ReceiveAsync([ArraySegment[byte]]::new($buf), $cts.Token).Result
        $result += [System.Text.Encoding]::UTF8.GetString($buf, 0, $recv.Count)
    } while (-not $recv.EndOfMessage)

    $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "", $cts.Token).Wait()
    return $result | ConvertFrom-Json
}

function Get-PageText($tab) {
    try {
        # Try LinkedIn-specific selectors first, fall back to body text
        $js = @"
(function() {
    function t(sels) {
        for (var s of sels) {
            var el = document.querySelector(s);
            if (el && el.innerText.trim()) return el.innerText.trim();
        }
        return '';
    }
    var url = window.location.href;
    if (url.includes('linkedin.com')) {
        return JSON.stringify({
            title:    t(['h1.job-details-jobs-unified-top-card__job-title','h1.topcard__title','h1']),
            company:  t(['.job-details-jobs-unified-top-card__company-name a',
                         '.job-details-jobs-unified-top-card__company-name',
                         '.topcard__org-name-link']),
            location: t(['.job-details-jobs-unified-top-card__primary-description-without-url',
                         '.topcard__flavor--bullet']),
            description: t(['#job-details','.jobs-description__content',
                            '.show-more-less-html__markup']) || document.body.innerText
        });
    }
    return JSON.stringify({
        title:       document.title.split(/[|\-–]/)[0].trim(),
        company:     document.title.split(/[|\-–]/)[1]?.trim() || '',
        location:    '',
        description: document.body.innerText
    });
})()
"@
        $resp = Invoke-CDP $tab.webSocketDebuggerUrl "Runtime.evaluate" @{
            expression    = $js
            returnByValue = $true
        }
        return $resp.result.result.value | ConvertFrom-Json
    } catch {
        Write-Warning "  Error scraping $($tab.url): $_"
        return $null
    }
}

# ── 5. Collect results and write JSON ─────────────────────────────────────

$results = @()
foreach ($tab in $jobTabs) {
    Write-Host "  Scraping: $($tab.url.Substring(0, [Math]::Min(80,$tab.url.Length)))"
    $data = Get-PageText $tab
    if ($data -and $data.title) {
        $results += @{
            url         = $tab.url
            title       = $data.title
            company     = $data.company
            location    = $data.location
            description = $data.description
        }
        Write-Host "    title: $($data.title)"
        Write-Host "    company: $($data.company)"
        Write-Host "    desc_len: $($data.description.Length)"
    } else {
        Write-Warning "  Could not extract content from $($tab.url)"
    }
}

$results | ConvertTo-Json -Depth 5 | Set-Content -Path $OutFile -Encoding UTF8
Write-Host "`nWrote $($results.Count) result(s) to $OutFile"
