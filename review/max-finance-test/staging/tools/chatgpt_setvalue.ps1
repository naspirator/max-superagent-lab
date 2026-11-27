Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$p = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$p.MainWindowHandle)
$c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Спросить ChatGPT")
$edit = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
if (-not $edit) { Write-Output "NO_EDIT"; exit 1 }
$edit.SetFocus()
$vp = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
try {
    $vp.SetValue("ТЕСТ 123")
    Write-Output "SET_OK"
} catch {
    Write-Output ("SET_FAIL " + $_.Exception.Message)
}
Start-Sleep -Seconds 1
try { Write-Output ("VALUE=" + $vp.Current.Value) } catch { Write-Output "NO_VALUE" }
