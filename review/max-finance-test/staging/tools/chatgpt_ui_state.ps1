Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$rows = @()
foreach ($e in $all) {
    try {
        $type = $e.Current.ControlType.ProgrammaticName
        $name = $e.Current.Name
        $enabled = $e.Current.IsEnabled
        if ($type -match 'Edit|Button' -and ($name -match 'Отправ|Спросить|файл|ChatGPT|Send|Attach' -or $type -match 'Edit')) {
            $value = ""
            if ($type -eq 'ControlType.Edit') {
                try { $vp = $e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern); $value = " LEN=" + $vp.Current.Value.Length } catch {}
            }
            $rows += "$type | $name | enabled=$enabled$value"
        }
    } catch {}
}
$rows | Select-Object -Last 30
