param([string]$Text = "ПРОВЕРКА ВСТАВКИ 123")
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class MouseClick {
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    public const uint LEFTDOWN = 0x0002;
    public const uint LEFTUP = 0x0004;
}
"@
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
[MouseClick]::SetForegroundWindow([IntPtr]$p.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 500
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
$edit = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
if (-not $edit) { Write-Output "NO_EDIT"; exit 1 }
$r = $edit.Current.BoundingRectangle
$x = [int]($r.Left + $r.Width / 2)
$y = [int]($r.Top + $r.Height / 2)
Write-Output ("CLICK $x $y RECT $r")
[MouseClick]::SetCursorPos($x, $y) | Out-Null
[MouseClick]::mouse_event([MouseClick]::LEFTDOWN, 0, 0, 0, [UIntPtr]::Zero)
[MouseClick]::mouse_event([MouseClick]::LEFTUP, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 500
[System.Windows.Forms.Clipboard]::SetText($Text)
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 200
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Seconds 2
try { $vp = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern); Write-Output ("VALUE_LEN=" + $vp.Current.Value.Length) } catch { Write-Output "NO_VALUE" }
