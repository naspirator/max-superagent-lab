Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
function Find-Name([string]$n) {
    $c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $n)
    return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
}
$file = Find-Name "Файл"
try { $file.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() } catch { try { $file.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() } catch {} }
Start-Sleep -Milliseconds 800
$item = Find-Name "Новый чат Ctrl+N"
if (-not $item) { Write-Output "NO_NEW_CHAT_ITEM"; exit 1 }
try {
    $item.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
} catch {
    $item.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
}
Write-Output "NEW_CHAT_MENU_INVOKED"
Start-Sleep -Seconds 3
