# Как запустить независимую проверку Superagent

Superagent работает: WSL-дистрибутив `Ubuntu-Superagent`, панель
`http://127.0.0.1:3082`, источник GitHub включён. PR #38 создан, вершина
`cad6262` (последний коммит с кодом; дальше только CI и отчёты).

## Почему проверка не запустилась сама

Проверены фактические настройки и код источника GitHub, а не предположения:

1. В политике разрешены два аккаунта:
   `{"github":{"allowed":[{"id":"naspirator"},{"id":"max535max"}]}}`.
2. Включён только поток Issues:
   `observeIssues: true`, `observePulls: false`, `observeComments: false`.
   Значит, комментарии к Issue/PR **не** создают триггер; новый Issue — создаёт.
3. Поток Issues стартовал `2026-11-27T16:08:34Z`, а Issue #39 создан
   `16:07:56Z` — то есть **до** старта потока и уже не считается новым.
4. `src/sources/github.ts:227` пропускает элементы, автор которых совпадает с
   логином агента (`if sameName(item.user.login, login) continue`), а
   `github-trigger.ts:63` ставит для self-authored `human=false`.

Итог: ни комментарий, ни Issue #39 (создан агентом `max535max`) проверку не
запустят. Нужен **новый Issue от аккаунта `naspirator`**.

## Что нужно сделать человеку

Открыть новый Issue: https://github.com/naspirator/max-superagent-lab/issues/new

Формат ниже — тот же, что в сработавших триггерах #34 (PR #31) и #37 (PR #36):
там отзыв появлялся именно после такого Issue от `naspirator`.

**Заголовок:**

```text
MAX Review: PR #38 @cad6262757b5
```

**Текст:**

```text
@max535max You are MAX Reviewer, an independent reviewer. Do not modify files, push, approve or merge.
Review pull request #38 at commit cad6262757b507a88bb031080e882b3958822c3b (last code commit; everything after it is reports/CI only - verify with: git log --name-only cad6262..origin/review/max-finance-test-20261127) in naspirator/max-superagent-lab against main.

Original task:
Модернизировать действующий проект MAX FINANCE (Telegram-бот распознавания
рукописных финансовых отчётов шиномонтажа с записью в Google Таблицы): найти
проект, фотобазу и сервер; сделать полную резервную копию; реализовать
изолированный режим «MAX FINANCE TEST» в том же боте с полным ручным
редактированием, линией распознавания, словарём сотрудников и базой
подтверждённых примеров; провести тестирование, независимую проверку Superagent
и независимую приёмку ChatGPT, не внедряя изменения в PROD без явного
согласования владельца.

Where to look:
- Reports: review/max-finance-test/reports/ — MAX_FINANCE_TEST_REPORT.md,
  FINAL_STATUS.md, REVIEW_RESPONSE.md, REQUIREMENTS_TRACEABILITY.md, ci-run.txt
- Code: review/max-finance-test/staging/ (bot.py, maxfinance_test/*)
- Tests: review/max-finance-test/staging/tests + tests_baseline
- Deploy: review/max-finance-test/staging/deploy/ (install-test-mode.sh, rollback-production.sh, backup-production.sh)
- Diff: gh pr diff 38 --repo naspirator/max-superagent-lab (85 files, ~12.8k lines; most volume is the report files)

Actions:
- Read the diff and the code. Check: mode isolation (separate TEST sheet, separate
  SQLite, no PROD sync/polling), manual editing (signs, split/merge, order, undo),
  recognition line (minus sign, struck rows, bbox), employee dictionary, confirmed
  examples/holdout, backup/restore, fail-closed behaviour.
- Check that tests actually cover the claims. If useful:
  cd review/max-finance-test/staging && python -m pip install -r requirements.txt && python -m pytest tests tests_baseline
- Post exactly one comment on PR #38:
  gh pr comment 38 --repo naspirator/max-superagent-lab --body "..."
- Verdict format: first line VERDICT: APPROVE | REVISE | BLOCKED, then only new
  BLOCKER/MAJOR findings with file and line. Do not publish review and do not
  change the PR.
```

Новый Issue будет создан после старта потока Issues, поэтому Superagent его
увидит и создаст тикет.

## Альтернатива: включить комментарии

В панели Superagent можно включить `observeComments` (и/или `observePulls`) в
настройках источника GitHub, после чего комментарий человека в существующем
Issue/PR тоже станет триггером. Это изменение конфигурации Superagent, а не
PROD-бота MAX FINANCE.

## Что произойдёт дальше

1. Superagent увидит human-триггер и возьмёт Issue/PR в работу.
2. Проверит код, тесты и отчёты, при возможности прогонит набор.
3. Оставит отзыв в PR/Issue или вернёт результат в свою панель.

## Чего делать нельзя

- комментировать от `max535max` и ждать human-триггера — он будет пропущен;
- ждать триггер от комментария в Issue #39 при выключенном `observeComments`;
- выдавать собственную проверку за Superagent-ревью;
- вносить изменения в PROD до APPROVE и согласования владельца.
