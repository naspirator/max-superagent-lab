param(
    [Parameter(Mandatory=$true)][string]$PromptFile,
    [Parameter(Mandatory=$true)][string]$OutputFile,
    [int]$TimeoutSeconds = 300,
    [switch]$NoNewChat
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

$proc = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $proc) { Write-Output "NO_CHATGPT_WINDOW"; exit 1 }
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$proc.MainWindowHandle)

function Find-All-ByName([string]$name) {
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $name)
    return $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
}
function Invoke-Element($element) {
    $pattern = $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $pattern.Invoke()
}

if (-not $NoNewChat) {
    $newChats = Find-All-ByName "Новый чат"
    if ($newChats.Count -eq 0) { $newChats = Find-All-ByName "New chat" }
    foreach ($candidate in $newChats) {
        try { if ($candidate.Current.IsEnabled) { Invoke-Element $candidate; break } } catch {}
    }
    Start-Sleep -Seconds 3
}

$edits = Find-All-ByName "Спросить ChatGPT"
if ($edits.Count -eq 0) { $edits = Find-All-ByName "Ask ChatGPT" }
if ($edits.Count -eq 0) { Write-Output "NO_EDIT"; exit 2 }
$edit = $edits[0]
$edit.SetFocus()
Start-Sleep -Milliseconds 600

$prompt = [System.IO.File]::ReadAllText($PromptFile, [System.Text.Encoding]::UTF8)
[System.Windows.Forms.Clipboard]::SetText($prompt)
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Seconds 6

$send = $null
for ($i = 0; $i -lt 30; $i++) {
    $buttons = Find-All-ByName "Отправить"
    if ($buttons.Count -eq 0) { $buttons = Find-All-ByName "Send" }
    foreach ($candidate in $buttons) {
        try { if ($candidate.Current.IsEnabled) { $send = $candidate; break } } catch {}
    }
    if ($send) { break }
    Start-Sleep -Seconds 1
}
if (-not $send) { Write-Output "NO_SEND"; exit 3 }
Invoke-Element $send
Write-Output "SENT"

$document = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)))
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$last = ""
$stable = 0
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 4
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
