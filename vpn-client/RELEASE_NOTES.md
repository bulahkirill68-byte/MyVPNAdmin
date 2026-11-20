# Reality VPN 1.0.3

Windows-клиент, Android-клиент и отдельная сборка для Android 8.0.0.

## Скачать

- **Windows x64:** `RealityVPN-1.0.3-portable.exe` либо `RealityVPN-1.0.3-setup.exe`.
- **Android 8.0+:** `RealityVPN-1.0.3.apk` (ARM32, ARM64, x86_64).
- **Отдельный порт Android 8.0.0 / API 26:** `RealityVPN-Android8-1.0.3.apk` — универсальный APK для ARM32, ARM64, x86 и x86_64. Для каждой архитектуры приложен APK меньшего размера.
- `SHA256SUMS.txt` содержит контрольные суммы всех восьми сборок.

## Windows

- VLESS TCP/RAW + REALITY + XTLS Vision, fingerprint по умолчанию `firefox`.
- Режимы системного прокси и VPN/TUN.
- Быстрый portable: однократная распаковка и кэширование файлов для последующих запусков.
- Проверка доступа через VPN отдельно от состояния локального ядра, индикатор задержки статистики, скорости и анимации.
- Исправлены вставка и копирование ссылок; профили зашифрованы Windows DPAPI.
- Опциональный запуск при входе в Windows, по умолчанию выключен.

## Android

- Анимации, счётчики и скорости в приложении и foreground-уведомлении.
- Плитка Reality VPN в быстрых настройках и кнопка остановки в уведомлении.
- Выбор включённых/исключённых приложений с иконками; служебные пакеты без launcher-значка скрыты.
- AES-GCM/Android Keystore для профилей.
- Исправлено разделение DNS и direct-маршрутизации Яндекса/российских доменов.
- Отдельный Gradle-проект Android 8 с `minSdk` / `targetSdk` 26 и проверками на API 26.

APK подписаны тем же локальным ключом и сохраняют `applicationId`: установите поверх существующей версии, чтобы сохранить профили. Android 8 порт имеет versionCode 5, основной Android APK — 4. Для неизвестной архитектуры Android 8 выбирайте универсальный APK. Перед обновлением отключите VPN и закройте старую версию приложения.

На Android 14+ система позволяет скрывать ongoing-уведомления свайпом; приложение восстанавливает уведомление активного VPN. Установка пользователем запрета уведомлений не обходится. Windows EXE без Authenticode-подписи.

## Проверки

Прошли Windows production build, 15 тестов и packaged UI/core smoke; Android — 13 тестов, сборка и lint; Android 8 — 10 тестов, включая API 26, сборка и lint. Проверены подписи/выравнивание APK. Отдельный localhost-тест с настоящим Xray подтверждает direct DNS/TLS-маршруты для `ya.ru` и `yandex.ru` при недоступном тестовом VPN endpoint.

Реальные TUN/UAC-маршруты на Windows и VPN/per-app работа на физическом Android-устройстве требуют проверки в целевой сети. Запуск ядра и успешная проверка отдельных HTTPS-адресов не гарантируют доступность любого сайта.

Инструкции и исходники: [`vpn-client/README.md`](https://github.com/bulahkirill68-byte/MyVPNAdmin/blob/main/vpn-client/README.md) и [`vpn-client/android-8/README.md`](https://github.com/bulahkirill68-byte/MyVPNAdmin/blob/main/vpn-client/android-8/README.md).
