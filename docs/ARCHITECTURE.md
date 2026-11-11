# Архитектура

```text
Браузер → localhost:8000 → SSH tunnel → VPS 127.0.0.1:8000
                                              │
                                    FastAPI + Vue static
                                              │
                                       /data/panel.db (WAL)
                                              │
                                       один Python worker
                                              │
                                 127.0.0.1:10085 gRPC Xray
                                              │
                                    systemd Xray → TCP 443
```

Web и worker — один собранный образ, отдельные процессы. SQLite хранится в bind mount `./data`; единственный migrator не имеет сети. Server выделен в отдельную сущность для будущего расширения, но MVP работает с id=1. Несколько серверов в интерфейсе не предлагаются.

## Компромисс host network

На Linux контейнер с host network видит хостовый loopback Xray без открывания API в интернет. Web жёстко слушает 127.0.0.1:8000. Worker слушателей не создаёт. Это уменьшает сетевую изоляцию: процесс может соединяться с другими локальными сервисами. Компенсация — non-root UID 10001, отсутствие capabilities, read-only rootfs, no-new-privileges, никаких Docker socket/config.json/root mount. В 0.2 для установки и первоначальной подготовки добавлен отдельный root systemd host-agent с peer-checked Unix-сокетом; обычный CRUD/трафик по-прежнему используют прямой локальный gRPC.

## gRPC контракт

Изучены официальные файлы XTLS/Xray-core, commit `c43ee98ec7c5a9d34b32cedf891b4c8707e9c8b0`:

- `common/serial/typed_message.proto`: type=1, value=2;
- `common/protocol/user.proto`: level=1, email=2, account=3;
- `proxy/vless/account.proto`: id=1, flow=2, encryption=3;
- `app/proxyman/command/command.proto`: AddUserOperation, RemoveUserOperation, AlterInbound, GetInboundUsers;
- `app/stats/command/command.proto`: QueryStats(reset=false), GetSysStats(Uptime field 10).

`backend/app/xray.proto` — намеренно небольшой **wire-compatible subset**, а не копия всех внутренних конфигов Xray. Имена RPC и TypedMessage.type в адаптере — официальные полные имена. Локальный package protobuf не используется в TypedMessage. Сгенерированный `xray_pb2.py` включён в репозиторий. Генерация:

```bash
python -m grpc_tools.protoc -Ibackend --python_out=backend backend/app/xray.proto
```

Проверяется настоящий gRPC transport в тесте с generic server. На VPS `app.cli smoke` проверяет StatsService; reconciliation проверяет HandlerService. При существующем email UUID читается через GetInboundUsers. Неподдерживаемый RPC → видимая ошибка, неизвестная идентичность не удаляется. Автообновления Xray нет.

## Желаемое состояние

У пользователя есть intent (`active`, `paused`, `revoked`), nullable expires_at/quota_bytes и вычисляемый эффективный статус. Приоритет: deleted/revoked → paused → expired → quota_exceeded → active. Пауза не останавливает календарный срок. Возобновление снимает паузу/аннулирование, но не продлевает срок и не обнуляет трафик. Для expired нужно продление, для quota_exceeded — увеличение/снятие квоты. 0 не является безлимитом.

CRUD фиксирует `pending_apply`, worker применяет HandlerService и выставляет `applied` либо `error`. API CRUD подтверждает запись желания в SQLite, не успешный доступ. Reconciliation выполняется на каждой итерации, включая старт и восстановление после API outage. Tombstone не удаляется физически: это нужно, чтобы блокировка пережила возвращение статического клиента после перезапуска Xray.

При ротации прежние UUID остаются только в закрытой истории SQLite. Если после рестарта Xray вернул **известный** UUID того же email, worker удалит старую идентичность и применит новую. Неизвестный UUID вызывает конфликт вместо захвата пользователя.

Один активный worker защищён `filelock` на общем /data. Процесс держит DB-транзакцию на итерацию; накопление трафика, baseline счётчиков, уведомления и samples фиксируются атомарно. При сбое после runtime-действия и до commit операция повторится идемпотентно. Все RPC имеют timeout 4 секунды. Модель предназначена для небольшого одного VPS; длинная итерация при массовой недоступности API может задерживать записи UI.

## Трафик

Для каждой пары user/direction хранится последнее значение. Delta = current − previous; при уменьшении current считаем current. Перезапуск определяется по изменению оценённого времени запуска Xray `UTC now − Uptime` более чем на 3 секунды. При рестарте baseline обнуляется, даже если новые счётчики уже превысили старые. Пропавший счётчик без рестарта не обнуляет baseline. reset=false не разрушает счётчики других потребителей.

Пороговые события 80/95/100% попадают в аудит, без отправки email/Telegram. Отсутствие StatsService отображается отдельно; сроки и ручные блокировки всё равно применяются через HandlerService. Графики: почасовая сумма samples, детализация хранится 90 дней; накопленный used_bytes не очищается. День/месяц — UTC. После перевода часов на VPS возможно ложное определение рестарта, поэтому нужен работающий NTP.

## Резервирование

SQLite backup API делает согласованный snapshot без копирования живого WAL вручную. Integrity check, минимум 100 МиБ свободного места, последние 14 копий. Суточный запуск из worker, ручной из CLI/UI. Restore только из data/backups с остановленными web/worker, проверкой integrity и обязательных таблиц; worker lock защищает от запущенного планировщика. Перед восстановлением создаётся аварийная копия, затем сбрасываются сессии, выполняются миграции. Копии версионированы и не входят в Git.
