param(
    [Parameter(Mandatory=$true)][string]$PromptFile,
    [Parameter(Mandatory=$true)][string]$OutputFile,
    [int]$TimeoutSeconds = 240
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

$proc = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $proc) { Write-Output "NO_CHATGPT_WINDOW"; exit 1 }
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$proc.MainWindowHandle)

function Find-ByName([string]$name, [string]$type = "") {
    $condition = New-Object System.Windows.Automation.AndCondition(
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $name)),
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::IsEnabledProperty, $true))
    )
    return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
}

function Invoke-Element($element) {
    if (-not $element) { throw "Element not found" }
    $pattern = $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $pattern.Invoke()
}

$newChat = Find-ByName "Новый чат"
if (-not $newChat) { $newChat = Find-ByName "New chat" }
if ($newChat) { Invoke-Element $newChat; Start-Sleep -Milliseconds 1500 }

$edit = Find-ByName "Спросить ChatGPT"
if (-not $edit) { $edit = Find-ByName "Ask ChatGPT" }
if (-not $edit) { Write-Output "NO_EDIT"; exit 2 }
$edit.SetFocus()
Start-Sleep -Milliseconds 400

$prompt = [System.IO.File]::ReadAllText($PromptFile, [System.Text.Encoding]::UTF8)
[System.Windows.Forms.Clipboard]::SetText($prompt)
Start-Sleep -Milliseconds 300
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 5000

$send = Find-ByName "Отправить"
if (-not $send) { $send = Find-ByName "Send" }
if (-not $send) { Write-Output "NO_SEND"; exit 3 }
Invoke-Element $send
Write-Output "SENT"

$document = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)))
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$last = ""
$stable = 0
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $text = ""
    if ($document) {
        try {
            $pattern = $document.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
            $text = $pattern.DocumentRange.GetText(-1)
        } catch { $text = "" }
    }
    if ($text.Length -gt 0) {
        if ($text -eq $last) { $stable++ } else { $stable = 0; $last = $text }
        if ($stable -ge 3) { break }
    }
}
[System.IO.File]::WriteAllText($OutputFile, $last, [System.Text.Encoding]::UTF8)
Write-Output ("TRANSCRIPT_LENGTH=" + $last.Length)
