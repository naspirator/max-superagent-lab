Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $p) { Write-Output "NO_CHATGPT_WINDOW"; exit 1 }
Write-Output ("WINDOW=" + $p.MainWindowTitle + " HANDLE=" + $p.MainWindowHandle)
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$rows = @()
foreach ($e in $all) {
    try {
        $type = $e.Current.ControlType.ProgrammaticName
        $name = $e.Current.Name
        $auto = $e.Current.AutomationId
        if ($name -or $auto) {
            $rows += [pscustomobject]@{ Type = $type; Name = $name; Auto = $auto }
        }
    } catch {}
}
$rows | Select-Object -First 120 | Format-Table -AutoSize -Wrap | Out-String -Width 240
