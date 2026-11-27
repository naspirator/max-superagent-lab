Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct CREDENTIAL {
    public int Flags;
    public int Type;
    public string TargetName;
    public string Comment;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
    public int CredentialBlobSize;
    public IntPtr CredentialBlob;
    public int Persist;
    public int AttributeCount;
    public IntPtr Attributes;
    public string TargetAlias;
    public string UserName;
}
public class CredReader {
    [DllImport("advapi32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    public static extern bool CredRead(string target, int type, int flags, out IntPtr credential);
    [DllImport("advapi32.dll", SetLastError=true)]
    public static extern void CredFree(IntPtr buffer);
    public static string Read(string target) {
        IntPtr ptr;
        if (!CredRead(target, 1, 0, out ptr)) return null;
        try {
            CREDENTIAL cred = (CREDENTIAL)Marshal.PtrToStructure(ptr, typeof(CREDENTIAL));
            if (cred.CredentialBlobSize <= 0) return "";
            return Marshal.PtrToStringUni(cred.CredentialBlob, cred.CredentialBlobSize / 2);
        } finally { CredFree(ptr); }
    }
}
"@
$target = "gh:github.com:naspirator"
$token = [CredReader]::Read($target)
if (-not $token) { Write-Output "NO_CREDENTIAL"; exit 1 }
Write-Output ("TOKEN_LENGTH=" + $token.Length)
$headers = @{ Authorization = "token $token"; "User-Agent" = "max-finance-test" }
try {
    $user = Invoke-RestMethod -Uri "https://api.github.com/user" -Headers $headers -TimeoutSec 30
    Write-Output ("LOGIN=" + $user.login)
} catch {
    Write-Output ("API_ERROR=" + $_.Exception.Message)
    exit 1
}
