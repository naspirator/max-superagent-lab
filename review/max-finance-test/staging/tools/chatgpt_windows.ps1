Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinEnum {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
}
"@
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
function Find-Name([string]$n) {
    $c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $n)
    return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
}
$file = Find-Name "Файл"
try { $file.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() } catch {}
Start-Sleep -Milliseconds 600
$item = Find-Name "Новый чат Ctrl+N"
if ($item) { $item.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
Start-Sleep -Seconds 3
$fg = [WinEnum]::GetForegroundWindow()
$pid2 = 0
[WinEnum]::GetWindowThreadProcessId($fg, [ref]$pid2) | Out-Null
Write-Output ("FOREGROUND=" + $fg + " PID=" + $pid2)
Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
    Write-Output ("PROC " + $_.Id + " HANDLE=" + $_.MainWindowHandle + " TITLE=" + $_.MainWindowTitle + " START=" + $_.StartTime)
}
