Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Файл")
$menu = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
if ($menu) {
    try { $menu.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() } catch {}
    try { $menu.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() } catch {}
}
Start-Sleep -Seconds 2
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($e in $all) {
    try {
        $type = $e.Current.ControlType.ProgrammaticName
        $name = $e.Current.Name
        if ($type -match 'MenuItem') {
            Write-Output ("$type | $name | acc=" + $e.Current.AcceleratorKey + " | access=" + $e.Current.AccessKey)
        }
    } catch {}
}
