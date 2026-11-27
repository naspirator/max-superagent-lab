Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Добавить файлы и другое")
$b = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
if (-not $b) { Write-Output "NO_ATTACH_BUTTON"; exit 1 }
$pattern = $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$pattern.Invoke()
Start-Sleep -Seconds 1
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($e in $all) {
    try {
        $type = $e.Current.ControlType.ProgrammaticName
        $name = $e.Current.Name
        if ($type -match 'Button|MenuItem|ListItem' -and $name) {
            Write-Output ("$type | $name | " + $e.Current.AutomationId)
        }
    } catch {}
}
