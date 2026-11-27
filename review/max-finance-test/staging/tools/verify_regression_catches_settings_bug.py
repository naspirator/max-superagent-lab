"""Отрицательный контроль к тесту на потерю таблицы `settings`.

Тест `tests/test_dispatch_isolation.py::
test_dispatcher_blocks_when_meta_survives_but_settings_table_is_lost` должен
падать на реализации `_has_schema()` из `ccee903`, иначе он ничего не
доказывает: проверка шестого цикла показала, что прежняя версия теста
стартовала с уже восстановленной базы (`recovered=True`) и проходила на
любой реализации.

Запуск (из каталога staging):

    python tools/verify_regression_catches_settings_bug.py

Ожидаемый вывод: `NEGATIVE_CONTROL=OK`, код возврата 0.
Те же утверждения есть в самом наборе тестов:
`test_old_schema_check_would_let_user_back_into_work`.
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGING = HERE.parent
sys.path.insert(0, str(STAGING))

from maxfinance_test.store import ModeStore  # noqa: E402

TEST_NAME = "test_dispatcher_blocks_when_meta_survives_but_settings_table_is_lost"


def load_tests():
    path = STAGING / "tests" / "test_dispatch_isolation.py"
    spec = importlib.util.spec_from_file_location("test_dispatch_isolation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_case(test) -> str:
    tmp = Path(tempfile.mkdtemp(prefix="negctl-"))
    try:
        test(tmp)
        return "PASS"
    except AssertionError:
        return "FAIL"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    module = load_tests()
    test = getattr(module, TEST_NAME)
    old_has_schema = module.old_has_schema

    current = ModeStore._has_schema
    try:
        ModeStore._has_schema = old_has_schema
        old_result = run_case(test)
    finally:
        ModeStore._has_schema = current
    new_result = run_case(test)

    print(f"OLD_IMPLEMENTATION={old_result} (ожидается FAIL)")
    print(f"CURRENT_IMPLEMENTATION={new_result} (ожидается PASS)")
    ok = old_result == "FAIL" and new_result == "PASS"
    print("NEGATIVE_CONTROL=" + ("OK" if ok else "BROKEN"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
