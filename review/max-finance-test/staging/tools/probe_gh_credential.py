import subprocess
import urllib.request
import json

env = {
    "GCM_INTERACTIVE": "never",
    "GIT_TERMINAL_PROMPT": "0",
    "PATH": __import__("os").environ.get("PATH", ""),
}
data = "protocol=https\nhost=github.com\nusername=naspirator\n\n"
try:
    result = subprocess.run(
        ["git", "credential", "fill"], input=data, text=True,
        capture_output=True, timeout=15, env=env,
    )
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    token = fields.get("password")
    username = fields.get("username")
    print("credential_found", bool(token), "username", username)
    if token:
        request = urllib.request.Request(
            "https://api.github.com/user",
            headers={"Authorization": "token " + token, "User-Agent": "max-finance-test"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        print("LOGIN", payload.get("login"))
except Exception as exc:
    print("ERROR", type(exc).__name__, str(exc)[:200])
