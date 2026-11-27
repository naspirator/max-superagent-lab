param(
    [Parameter(Mandatory=$true)][string]$PromptFile,
    [Parameter(Mandatory=$true)][string]$OutputFile,
    [int]$TimeoutSeconds = 600,
    [switch]$NoNewChat
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes

$proc = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $proc) { Write-Output "NO_CHATGPT_WINDOW"; exit 1 }
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$proc.MainWindowHandle)

function Find-Name([string]$name) {
    $c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $name)
    return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
}
function Find-All-Name([string]$name) {
    $c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $name)
    return $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $c)
}
function Invoke-El($el) { $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }

if (-not $NoNewChat) {
    $file = Find-Name "Файл"
    try { $file.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() } catch { try { Invoke-El $file } catch {} }
    Start-Sleep -Milliseconds 700
    $item = Find-Name "Новый чат Ctrl+N"
    if (-not $item) { Write-Output "NO_NEW_CHAT_ITEM"; exit 1 }
    try { Invoke-El $item } catch { $item.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() }
    Start-Sleep -Seconds 3
}

$edits = Find-All-Name "Спросить ChatGPT"
if ($edits.Count -eq 0) { $edits = Find-All-Name "Ask ChatGPT" }
if ($edits.Count -eq 0) { Write-Output "NO_EDIT"; exit 2 }
$edit = $edits[0]
$edit.SetFocus()
$prompt = [System.IO.File]::ReadAllText($PromptFile, [System.Text.Encoding]::UTF8)
$vp = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$vp.SetValue($prompt)
Start-Sleep -Seconds 4
try { Write-Output ("INPUT_LENGTH=" + $vp.Current.Value.Length) } catch {}

$send = $null
for ($i = 0; $i -lt 30; $i++) {
    $buttons = Find-All-Name "Отправить"
    if ($buttons.Count -eq 0) { $buttons = Find-All-Name "Send" }
    foreach ($b in $buttons) {
        try { if ($b.Current.IsEnabled) { $send = $b; break } } catch {}
    }
    if ($send) { break }
    Start-Sleep -Seconds 1
}
if (-not $send) { Write-Output "NO_SEND"; exit 3 }
Invoke-El $send
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
