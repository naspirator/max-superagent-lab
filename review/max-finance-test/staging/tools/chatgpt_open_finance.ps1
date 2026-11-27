Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
function Find-Name([string]$n) {
    $c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $n)
    return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
}
$chat = Find-Name "Доработка MAX FINANCE"
if (-not $chat) { Write-Output "NO_CHAT"; exit 1 }
$chat.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Seconds 2
$edit = Find-Name "Спросить ChatGPT"
if (-not $edit) { Write-Output "NO_EDIT"; exit 1 }
$edit.SetFocus()
$vp = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$vp.SetValue("МАРКЕР ПРОВЕРКИ")
Write-Output ("VALUE_LEN=" + $vp.Current.Value.Length)
Start-Sleep -Seconds 1
