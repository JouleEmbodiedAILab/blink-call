param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 2147483647)]
    [int]$TargetProcessId,

    [ValidateRange(1, 3600)]
    [int]$DurationSeconds = 120,

    [ValidateRange(1, 60)]
    [int]$IntervalSeconds = 2,

    [string]$OutFile = (Join-Path $env:TEMP ("blink_audio_threads_{0}.jsonl" -f (Get-Date -Format "yyyyMMdd_HHmmss")))
)

$ErrorActionPreference = "Stop"
$writer = [System.IO.StreamWriter]::new($OutFile, $false, [System.Text.UTF8Encoding]::new($false))
$writer.AutoFlush = $true
$clock = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host "Sampling PID $TargetProcessId for $DurationSeconds seconds. Output: $OutFile"

try {
    do {
        $sample = [ordered]@{
            timestamp_utc = [DateTime]::UtcNow.ToString("o")
            pid = $TargetProcessId
        }
        $process = Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            $sample.event = "process_missing"
            $writer.WriteLine(($sample | ConvertTo-Json -Compress -Depth 5))
            break
        }

        try {
            $sample.event = "process_snapshot"
            $sample.name = $process.ProcessName
            $sample.start_time_utc = $process.StartTime.ToUniversalTime().ToString("o")
            $sample.cpu_seconds = $process.TotalProcessorTime.TotalSeconds
            $sample.working_set_bytes = $process.WorkingSet64
            $sample.handles = $process.HandleCount
            $threads = @($process.Threads)
            $sample.thread_count = $threads.Count
            $sample.threads = @(
                foreach ($thread in $threads) {
                    $entry = [ordered]@{ native_tid = $thread.Id }
                    try {
                        $state = $thread.ThreadState
                        $entry.state = $state.ToString()
                        if ($state -eq [System.Diagnostics.ThreadState]::Wait) {
                            $entry.wait_reason = $thread.WaitReason.ToString()
                        }
                        $entry.cpu_seconds = $thread.TotalProcessorTime.TotalSeconds
                    } catch {
                        # A thread can exit between enumerating and reading it.
                        $entry.read_error = $_.Exception.Message
                    }
                    $entry
                }
            )
        } catch {
            $sample.event = "snapshot_error"
            $sample.error = $_.Exception.Message
        } finally {
            $process.Dispose()
        }

        $writer.WriteLine(($sample | ConvertTo-Json -Compress -Depth 5))
        $remaining = $DurationSeconds - $clock.Elapsed.TotalSeconds
        if ($remaining -gt 0) {
            Start-Sleep -Milliseconds ([int]([Math]::Min($IntervalSeconds, $remaining) * 1000))
        }
    } while ($clock.Elapsed.TotalSeconds -lt $DurationSeconds)
} finally {
    $writer.Dispose()
    Write-Host "Saved: $OutFile"
}
