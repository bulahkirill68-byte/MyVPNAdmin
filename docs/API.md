# HTTP API

База: `http://localhost:8000/api`. Схема OpenAPI: `GET /api/openapi.json` после входа. Cookie-сессия, все изменяющие методы кроме login требуют `X-CSRF-Token` из login/me. Результат ошибок FastAPI: `{ "detail": ... }`. Даты — Unix timestamp UTC, размеры — байты, `null` — бессрочно/безлимит.

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` (без /api) | Живой HTTP + доступность SQLite, не здоровье Xray |
| POST | `/login` | `{name,password}` → csrf и HttpOnly cookie |
| GET | `/me` | Имя и csrf |
| POST | `/logout` | Отзыв сессии |
| GET/POST | `/users` | Список / создание |
| PUT | `/users/{id}` | Полная замена полей UserInput, без смены UUID/email |
| POST | `/users/{id}/actions` | pause/resume/revoke/delete/rotate/renew/token/revoke_token |
| GET | `/users/{id}/renew-preview?days=30&mode=expiry` | Расчёт expires_at для подтверждения |
| GET | `/users/{id}/access` | Явное раскрытие uuid и link, событие в аудите |
| GET | `/users/{id}/routing/export` | Назначенный пресет + правила трёх слоёв |
| GET | `/dashboard` | Последнее состояние worker, ресурсы ОС, TCP 443, UTC-трафик |
| GET | `/traffic?user_id=1` | Почасовой трафик за 7 дней, user_id необязателен |
| GET | `/audit?user_id=1` | Последние 200 событий |
| GET | `/settings` | Публичные метаданные и имена backup |
| GET | `/setup` | Состояние root host-agent, задачи и импорта |
| POST | `/setup/install` | Свежая установка на хосте, `{ip,sni,confirm:true}` |
| POST | `/setup/prepare` | Подготовка существующего Xray с backup/test/restart/rollback |
| POST | `/setup/initialize` | Завершение только пустой установки штатной службы; непустые конфиги не заменяются |
| POST | `/setup/import` | Импорт разрешённых метаданных от агента |
| GET | `/users/{id}/client-config` | Полный секретный клиентский JSON с назначенным routing |
| POST | `/backup` | Snapshot SQLite |
| GET/PUT | `/routing` | Редактор профиля |
| GET | `/routing/export` | Xray routing JSON для клиентского импорта |
| GET | `/routing/test?target=example.ru` | Предварительное совпадение, approximate=true при Geo-зависимости |

```json
{
  "name": "Анна · Android",
  "comment": "Личный телефон",
  "expires_at": null,
  "quota_bytes": 32212254720,
  "policy": "ru-direct"
}
```

Поля ответа пользователя: id, name, email, comment, expires_at, quota_bytes, used_bytes, last_activity, sync, error, policy, created, status. UUID скрыт из списка. Создание — 201. Изменение сохраняет pending_apply, итог смотрите после worker.

Для delete/revoke/rotate: `{"action":"delete","confirm":true}`. Для renewal: `{"action":"renew","days":30,"mode":"expiry","expected_expires":TIMESTAMP_ИЗ_PREVIEW}`. При рассинхронизации preview >120 секунд — 409. Mode now считает от текущей даты, expiry — от max(now, expires).

Локальная подписка: `GET /sub/{token}` без /api возвращает base64 VLESS URI; неактивная/неизвестная подписка — 404. Доступ к ней физически только через loopback/SSH, публикация по HTTP не предусмотрена.
