Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
$doc = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
if (-not $doc) { Write-Output "NO_DOC"; exit 1 }
$text = $doc.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern).DocumentRange.GetText(-1)
[System.IO.File]::WriteAllText("E:\MAX-FINANCE-TEST\reports\chatgpt-review-full.txt", $text, [System.Text.Encoding]::UTF8)
Write-Output ("LEN=" + $text.Length)
