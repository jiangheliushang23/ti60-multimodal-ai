param([ValidateSet('interface','map','pnr','pgm')][string]$Flow = 'interface')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$project = Join-Path $root 'ti60_multimodal'
$evidence = Join-Path $root 'ti60_multimodal/validation'
$runner = 'C:/Efinity/2026.1/bin/efx_run.bat'
$name = 'Ti60_Multimodal'
if ($Flow -eq 'pgm') {
    $timingPath = Join-Path $project ('outflow/' + $name + '.timing.rpt')
    $timingText = Get-Content -LiteralPath $timingPath -Raw
    $summary = ($timingText -split 'Clock Relationship Summary \(begin\)')[1] -split 'Clock Relationship Summary \(end\)'
    $rows = [regex]::Matches($summary[0], '(?m)^\S+\s+\S+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\([RF]-[RF]\)')
    if ($rows.Count -lt 16) { throw 'Timing summary is incomplete; do not generate a bitstream.' }
    foreach ($row in $rows) {
        if ([double]::Parse($row.Groups[2].Value, [Globalization.CultureInfo]::InvariantCulture) -lt 0) {
            throw ('Negative timing slack: ' + $row.Value)
        }
    }
}
if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString() -ne 'X64') {
    throw 'This launcher has only been checked on the current x64 Windows host.'
}
# Local child-process environment only; no installation or machine settings are changed.
$env:PROCESSOR_ARCHITECTURE = 'AMD64'
$env:PYTHONDONTWRITEBYTECODE = '1'
$started = Get-Date
$stamp = $started.ToString('yyyyMMdd_HHmmss')
$log = Join-Path $evidence ($Flow + '_' + $stamp + '.log')
$oldLocation = Get-Location
$exitCode = -1
try {
    Set-Location -LiteralPath $project
    if ($Flow -eq 'pgm') {
        # The Efinity wrapper makes --source absolute, which its Windows
        # bitstream generator cannot decode on this non-ASCII workspace.
        # Use the same generator and project options with relative file paths.
        [xml]$xml = Get-Content -LiteralPath ($name + '.xml') -Raw
        $ns = [Xml.XmlNamespaceManager]::new($xml.NameTable)
        $ns.AddNamespace('e', 'http://www.efinixinc.com/enf_proj')
        $allowed = @('mode','width','enable_roms','spi_low_power_mode','io_weak_pullup',
                     'oscillator_clock_divider','bitstream_compression','enable_external_master_clock',
                     'active_capture_clk_edge','jtag_usercode','release_tri_then_reset','four_byte_addressing')
        $opts = @('--interface_designer_settings', ('outflow/' + $name + '_or.ini'),
                  '--periph', "outflow/$name.lpf", '--family', 'Titanium', '--device', 'Ti60F225',
                  '--source', "work_pnr/$name.lbf", '--dest', "outflow/$name.hex")
        $nodes = $xml.SelectNodes('//e:bitstream_generation/e:param', $ns)
        foreach ($key in $allowed) {
            $node = @($nodes | Where-Object { $_.name -eq $key })
            if ($node.Count -ne 1) { throw "Missing or ambiguous bitstream option: $key" }
            $opts += "--$key=$($node[0].value)"
        }
        # No --program, USB or JTAG argument is supplied.
        $env:EFINITY_HOME = 'C:/Efinity/2026.1'
        & 'C:/Efinity/2026.1/bin/efx_pgm.exe' @opts 2>&1 | Tee-Object -FilePath $log
    } else {
        & $runner ($name + '.xml') --flow $Flow 2>&1 | Tee-Object -FilePath $log
    }
    $exitCode = $LASTEXITCODE
} finally {
    Set-Location -LiteralPath $oldLocation.Path
    [ordered]@{flow=$Flow;started=$started.ToString('o');finished=(Get-Date).ToString('o');
        exit_code=$exitCode;log=$log;project=$project;hardware_access=$false} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence ($Flow + '_' + $stamp + '.json')) -Encoding utf8
}
if ($exitCode -ne 0) { throw "Efinity $Flow failed with exit code $exitCode; see $log" }
$masterLog = Join-Path $project ('outflow/' + $name + '.log')
if ((Get-Content -LiteralPath $masterLog -Raw) -match 'Skipping Interface Designer step') {
    throw 'Interface Designer was skipped; this is not a successful build.'
}
$suffix = @{interface='.pt.rpt';map='.map.rpt';pnr='.timing.rpt';pgm='.bit'}[$Flow]
$artifact = Get-Item -LiteralPath (Join-Path $project ('outflow/' + $name + $suffix))
if ($artifact.LastWriteTime -lt $started.AddSeconds(-2)) { throw "Expected a fresh artifact: $($artifact.FullName)" }
Write-Output "Verified fresh $Flow artifact: $($artifact.FullName)"
Write-Output 'A successful command does not replace reviewing warnings and timing slack.'
