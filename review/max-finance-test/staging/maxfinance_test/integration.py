"""Подключение тестового режима к действующему боту.

Модуль не запускает второго polling-обработчика и не создаёт второго бота.
Он добавляет маршруты и отдельное хранилище внутрь существующего процесса.
"""
from __future__ import annotations

import os
from pathlib import Path

from .handlers import ModeHandlers
from .store import ModeStore


def create_test_handlers(base: Path | str, prod_db: Path | str | None,
                         prod_sheet_id: str | None, client, admin_id: int) -> ModeHandlers:
    root = Path(os.getenv("FINANCE_TEST_DIR", str(Path(base) / "test-mode"))).resolve()
    test_sheet_id = os.getenv("TEST_GOOGLE_SHEET_ID") or None
    store = ModeStore(
        root,
        prod_db=prod_db,
        prod_sheet_id=prod_sheet_id,
        test_sheet_id=test_sheet_id,
    )
    store.initialize()
    store.audit(None, "test_mode_initialized", f"root={root}")
    return ModeHandlers(store, client, admin_id)


__all__ = ["create_test_handlers"]
