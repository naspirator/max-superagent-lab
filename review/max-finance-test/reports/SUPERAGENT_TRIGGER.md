# Как запустить независимую проверку Superagent

Superagent уже работает: WSL-дистрибутив `Ubuntu-Superagent`, панель
`http://127.0.0.1:3082`, источник GitHub включён. PR #38 создан.

## Почему проверка не запустилась сама

Проверены фактические настройки и код источника GitHub, а не только
предположения:

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

Итог: комментарий в Issue #39 не сработает ни как новый Issue, ни как
человеческий триггер. Нужен **новый Issue**, созданный человеком.

## Что нужно сделать человеку

Открыть новый Issue в репозитории:

https://github.com/naspirator/max-superagent-lab/issues/new

От аккаунта `naspirator` (или другого аккаунта, добавленного в
`policy.sources.github.allowed`), например:

Заголовок:

```text
Review PR #38 (MAX FINANCE TEST) independently
```

Текст:

```text
@max535max please review PR #38 independently. Check the code, tests and the
B01/B03-B05/M03/M12-M13 fixes. Do not change the PR and do not publish a public
review.
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
2. Проверит код, тесты и исправления B01, B03–B05, M03, M12–M13.
3. Оставит отзыв в Issue/PR или вернёт результат в свою панель.

## Чего делать нельзя

- комментировать от `max535max` и ждать human-триггера — он будет пропущен;
- ждать триггер от комментария в Issue #39 при выключенном `observeComments`;
- выдавать собственную проверку за Superagent-ревью;
- вносить изменения в PROD до APPROVE и согласования владельца.
