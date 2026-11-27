Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Проверка")
$items = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $c)
foreach ($e in $items) {
    if ($e.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button) {
        $e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
        Write-Output "OPENED_CHECK"
        break
    }
}
Start-Sleep -Seconds 3
