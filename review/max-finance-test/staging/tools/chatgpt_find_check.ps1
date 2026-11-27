Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Проверка")
$items = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $c)
foreach ($e in $items) {
    Write-Output ("TYPE=" + $e.Current.ControlType.ProgrammaticName + " OFF=" + $e.Current.IsOffscreen + " RECT=" + $e.Current.BoundingRectangle)
    $patterns = $e.GetSupportedPatterns()
    foreach ($pt in $patterns) { Write-Output ("  PATTERN=" + $pt.ProgrammaticName) }
}
