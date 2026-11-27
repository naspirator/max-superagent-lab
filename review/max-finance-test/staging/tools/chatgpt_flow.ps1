param(
    [Parameter(Mandatory=$true)][string]$PromptFile,
    [Parameter(Mandatory=$true)][string]$OutputFile,
    [int]$TimeoutSeconds = 300
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class ClickWin {
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    public const uint LEFTDOWN = 0x0002;
    public const uint LEFTUP = 0x0004;
}
"@
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $p) { Write-Output "NO_WINDOW"; exit 1 }
[ClickWin]::SetForegroundWindow([IntPtr]$p.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 500
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)

# Клик по видимому полю ввода (координаты проверены скриншотом).
[ClickWin]::SetCursorPos(2790, 1033) | Out-Null
[ClickWin]::mouse_event([ClickWin]::LEFTDOWN, 0, 0, 0, [UIntPtr]::Zero)
[ClickWin]::mouse_event([ClickWin]::LEFTUP, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 500

$prompt = [System.IO.File]::ReadAllText($PromptFile, [System.Text.Encoding]::UTF8)
[System.Windows.Forms.Clipboard]::SetText($prompt)
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 200
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Seconds 8

$send = $null
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Отправить")
for ($i = 0; $i -lt 20; $i++) {
    $buttons = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
    foreach ($b in $buttons) {
        try { if ($b.Current.IsEnabled) { $send = $b; break } } catch {}
    }
    if ($send) { break }
    Start-Sleep -Seconds 1
}
if (-not $send) { Write-Output "NO_SEND"; exit 3 }
$send.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Write-Output "SENT"

$document = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)))
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$last = ""
$stable = 0
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 4
    $text = ""
    if ($document) {
        try { $text = $document.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern).DocumentRange.GetText(-1) } catch {}
    }
    if ($text.Length -gt 0) {
        if ($text -eq $last) { $stable++ } else { $stable = 0; $last = $text }
        if ($stable -ge 3) { break }
    }
}
[System.IO.File]::WriteAllText($OutputFile, $last, [System.Text.Encoding]::UTF8)
Write-Output ("TRANSCRIPT_LENGTH=" + $last.Length)
