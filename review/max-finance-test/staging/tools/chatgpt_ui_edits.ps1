Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($e in $all) {
    try {
        $type = $e.Current.ControlType.ProgrammaticName
        if ($type -match 'Edit|Document|Button') {
            $name = $e.Current.Name
            $auto = $e.Current.AutomationId
            Write-Output ("$type | $name | $auto")
        }
    } catch {}
}
