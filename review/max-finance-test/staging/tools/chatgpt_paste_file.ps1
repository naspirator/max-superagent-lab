param([Parameter(Mandatory=$true)][string]$PromptFile)
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class FgWin { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd); }
"@
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
[FgWin]::SetForegroundWindow([IntPtr]$p.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 500
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
$edit = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
if (-not $edit) { Write-Output "NO_EDIT"; exit 1 }
$edit.SetFocus()
Start-Sleep -Milliseconds 500
$prompt = [System.IO.File]::ReadAllText($PromptFile, [System.Text.Encoding]::UTF8)
[System.Windows.Forms.Clipboard]::SetText($prompt)
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 200
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Seconds 3
try { $vp = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern); Write-Output ("VALUE_LEN=" + $vp.Current.Value.Length) } catch { Write-Output "NO_VALUE" }
