# Drive the game in PCSX2 with the keyboard pad profile set by pcsx2_pad.py, then screenshot.
# Usage: powershell -File pcsx2_input.ps1 -Keys "O,wait2,DOWN,O" [-Shot]
#   Buttons: O (Circle) X (Cross) Q (Square) T (Triangle) START SELECT L1 R1 UP DOWN LEFT RIGHT
#   waitN = sleep N seconds; TURBO toggles fast-forward (Tab).
#   Prints the screenshot path when -Shot is given (PCSX2's own F8 hotkey, never desktop capture).
param([string]$Keys = "", [switch]$Shot)
Add-Type -Name K -Namespace W -MemberDefinition @'
[DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
'@
# Must match the bindings pcsx2_pad.py writes.
$map = @{ O=0x43; X=0x58; Q=0x5A; T=0x53; START=0x0D; SELECT=0x08; L1=0x31; R1=0x33;
          UP=0x26; DOWN=0x28; LEFT=0x25; RIGHT=0x27; F8=0x77; TURBO=0x09 }
$p = Get-Process pcsx2-qt -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { Write-Error "PCSX2 is not running"; exit 1 }
$null = [W.K]::SetForegroundWindow($p.MainWindowHandle)
Start-Sleep -Milliseconds 400
function Press($vk) {
    $ext = 0; if ($vk -ge 0x25 -and $vk -le 0x28) { $ext = 1 }   # arrows: extended keys, else they read as numpad
    [W.K]::keybd_event($vk, 0, $ext, [UIntPtr]::Zero); Start-Sleep -Milliseconds 120
    [W.K]::keybd_event($vk, 0, ($ext -bor 2), [UIntPtr]::Zero); Start-Sleep -Milliseconds 300
}
foreach ($k in ($Keys -split ',')) {
    $k = $k.Trim().ToUpper()
    if ($k -eq '') { continue }
    if ($k -like 'WAIT*') { Start-Sleep -Seconds ([double]$k.Substring(4)); continue }
    if (-not $map.ContainsKey($k)) { Write-Error "unknown key $k"; exit 1 }
    Press $map[$k]
}
if ($Shot) {
    $dir = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "PCSX2\snaps"
    $before = (Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    Press $map['F8']
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 250
        if ((Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count -gt $before) { break }
    }
    Start-Sleep -Milliseconds 300
    (Get-ChildItem $dir -Recurse -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
}
