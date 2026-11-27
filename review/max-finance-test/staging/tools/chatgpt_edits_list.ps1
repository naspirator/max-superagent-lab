Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
$edits = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $c)
$i = 0
foreach ($e in $edits) {
    $i++
    $name = $e.Current.Name
    $off = $e.Current.IsOffscreen
    $r = $e.Current.BoundingRectangle
    $len = -1
    try { $vp = $e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern); $len = $vp.Current.Value.Length } catch {}
    Write-Output ("EDIT $i name=$name offscreen=$off rect=$r valueLen=$len")
}
