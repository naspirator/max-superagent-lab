Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Новый чат")
$buttons = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
$invoked = $false
foreach ($b in $buttons) {
    try {
        if ($b.Current.IsEnabled) {
            $pattern = $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
            $pattern.Invoke()
            $invoked = $true
            break
        }
    } catch {}
}
Write-Output ("NEW_CHAT_INVOKED=" + $invoked + " COUNT=" + $buttons.Count)
Start-Sleep -Seconds 3
