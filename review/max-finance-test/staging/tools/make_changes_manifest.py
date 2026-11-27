import hashlib
from pathlib import Path

root = Path(r"E:\MAX-FINANCE-TEST")
diff = (root / "reports/bot.diff").read_text(encoding="utf-8").lstrip("\ufeff")
lines = [
    "# MAX FINANCE TEST — изменения относительно действующего кода",
    "",
    "Ниже: полный diff `bot.py` (единственный изменённый рабочий файл) и манифест",
    "новых файлов тестового режима. Новые файлы не входят в diff PROD; они лежат",
    "в `staging/maxfinance_test/` и не импортируются рабочим кодом без строки",
    "`import maxfinance_test` в `bot.py`.",
    "",
    "## Diff bot.py",
    "",
    "```diff",
    diff.rstrip(),
    "```",
    "",
    "## Новые файлы тестового режима",
    "",
    "| Файл | SHA-256 | Байт |",
    "|---|---:|---:|",
]
base = root / "staging"
skip_tools = {
    "chatgpt_attach_menu.ps1", "chatgpt_click_paste.ps1", "chatgpt_click_send.ps1",
    "chatgpt_dump_text.ps1", "chatgpt_edits_list.ps1", "chatgpt_enter.ps1",
    "chatgpt_enter2.ps1", "chatgpt_esc.ps1", "chatgpt_file_menu.ps1",
    "chatgpt_find_check.ps1", "chatgpt_flow.ps1", "chatgpt_focus.ps1",
    "chatgpt_newchat.ps1", "chatgpt_newchat2.ps1", "chatgpt_open_check.ps1",
    "chatgpt_open_finance.ps1", "chatgpt_paste_file.ps1", "chatgpt_screenshot.ps1",
    "chatgpt_send.ps1", "chatgpt_send2.ps1", "chatgpt_send3.ps1",
    "chatgpt_send4.ps1", "chatgpt_setvalue.ps1", "chatgpt_set_send.ps1",
    "chatgpt_submit.ps1", "chatgpt_ui_dump.ps1", "chatgpt_ui_edits.ps1",
    "chatgpt_ui_state.ps1", "chatgpt_windows.ps1", "make_chatgpt_prompt.py",
    "split_chatgpt_prompt.py", "show_snippet.py", "patch_failure_flag.py",
    "patch_handlers.py", "patch_mode.py", "patch_split.py", "patch_tests.py",
    "patch_cycle3_gaps.py", "patch_item_index_error.py", "probe_gh_credential.py",
    "read_naspirator_token.ps1", "make_changes_manifest.py",
    "update_reports_round3.py", "update_reports_round4.py",
    "update_reports_round5.py",
}
files = []
for p in sorted(base.rglob("*")):
    if not p.is_file():
        continue
    rel = p.relative_to(base)
    if "__pycache__" in rel.parts or rel.parts[0] in (
        ".venv", "reports", "review", ".pytest_cache",
    ):
        continue
    if rel.parts[0] == "tools" and p.name in skip_tools:
        continue
    files.append(p)
for p in files:
    rel = p.relative_to(base).as_posix()
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    lines.append(f"| `{rel}` | `{h}` | {p.stat().st_size} |")
(root / "reports/changes.diff").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("files", len(files), "bytes", (root / "reports/changes.diff").stat().st_size)
