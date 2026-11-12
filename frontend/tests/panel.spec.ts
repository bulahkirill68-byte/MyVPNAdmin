import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'

test('real API: login, user wizard, QR, pause, renewal, routing, backup, mobile', async ({ page }) => {
  const browserErrors: string[] = []
  page.on('pageerror', (error) => browserErrors.push(error.message))
  await page.setViewportSize({ width: 1440, height: 1050 })
  await page.goto('/')
  await page.getByLabel('Имя администратора').fill('e2e-owner')
  await page.getByLabel('Пароль', { exact: true }).fill('e2e-only-long-password')
  await page.getByRole('button', { name: 'Войти в панель' }).click()
  await expect(page.getByRole('heading', { name: 'Обзор сервера.' })).toBeVisible()
  await expect(page.locator('.hero-status')).toContainText('8.8.8.8')
  await page.screenshot({
    path: '../artifacts/dashboard-desktop.png',
    fullPage: true,
    animations: 'disabled',
  })
  await page.getByRole('button', { name: 'Добавить пользователя', exact: true }).click()
  await page.getByLabel('Имя / устройство').fill('Тест · Android')
  await page.getByRole('button', { name: 'Продолжить' }).click()
  await page.getByLabel('Квота трафика, ГиБ').fill('10')
  await page.getByRole('dialog').getByRole('button', { name: 'Создать доступ', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Карточка доступа' })).toBeVisible()
  await page.getByRole('button', { name: 'Показать QR и ссылку' }).click()
  await expect(page.getByRole('img', { name: 'QR-код подключения VLESS' })).toBeVisible()
  await expect(page.getByLabel('VLESS-ссылка', { exact: true })).toHaveValue(/^vless:\/\//)
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Клиентский JSON с маршрутизацией' }).click()
  const configDownload = await downloadEvent
  const config = JSON.parse(await readFile((await configDownload.path())!, 'utf8'))
  expect(config.routing.domainStrategy).toBe('IPOnDemand')
  expect(config.outbounds.map((o: { tag: string }) => o.tag)).toEqual(['proxy', 'direct', 'block'])
  await page.getByRole('button', { name: 'Готово', exact: true }).click()
  await page
    .getByRole('navigation')
    .getByRole('button', { name: /^Пользователи/ })
    .click()
  await page.getByRole('button', { name: 'Тест · Android', exact: false }).first().click()
  await page.getByRole('button', { name: 'Приостановить', exact: true }).click()
  await page.getByRole('button', { name: 'Подтвердить', exact: true }).click()
  await expect(page.locator('tbody tr').filter({ hasText: 'Тест · Android' })).toContainText('Приостановлен')
  await page.getByRole('button', { name: 'Тест · Android', exact: false }).first().click()
  await page.getByRole('button', { name: 'Продлить', exact: true }).click()
  await page.getByRole('button', { name: 'Рассчитать итоговую дату' }).click()
  await expect(page.getByText('Новый срок UTC')).toBeVisible()
  await page.getByRole('button', { name: 'Подтвердить продление' }).click()
  await page.getByRole('button', { name: 'Маршрутизация', exact: true }).click()
  await page.getByRole('button', { name: 'Правило', exact: true }).click()
  await page.getByLabel('Значения через запятую').fill('domain:example.ru')
  await page.getByRole('button', { name: 'Сохранить профиль' }).click()
  await page.getByLabel('Домен или IP для проверки').fill('example.ru')
  await page.getByRole('button', { name: 'Проверить', exact: true }).click()
  await expect(page.getByText('proxy · правило 1.', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'Настройки', exact: true }).click()
  await page.getByRole('button', { name: 'Создать копию сейчас' }).click()
  await expect(page.locator('.backup-list li')).toHaveCount(1)
  await page.getByRole('button', { name: 'Обзор', exact: true }).click()
  await page.getByRole('button', { name: 'Светлая тема' }).click()
  await page.screenshot({ path: '../artifacts/dashboard-light.png', fullPage: true, animations: 'disabled' })
  await page.getByRole('button', { name: 'Тёмная тема' }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: '../artifacts/dashboard-mobile.png', fullPage: true, animations: 'disabled' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.getByRole('button', { name: 'Меню', exact: true }).click()
  await page
    .getByRole('navigation')
    .getByRole('button', { name: /^Пользователи/ })
    .click()
  await expect(page.getByRole('heading', { name: 'Пользователи.' })).toBeVisible()
  expect(browserErrors).toEqual([])
})

test('setup wizard: fresh install job and import UI with isolated host-agent responses', async ({ page }) => {
  let installed = false, imported = false
  await page.route('**/api/settings', route => route.fulfill({ json: { server: null, backups: [] } }))
  await page.route('**/api/setup', route => route.fulfill({ json: {
    available: true, imported, installed, config_exists: installed, public_ip: '8.8.8.8',
    job: { state: installed ? 'succeeded' : 'idle', message: installed ? 'Xray готов к импорту в панель' : '' }
  } }))
  await page.route('**/api/setup/install', async route => {
    expect(route.request().postDataJSON()).toMatchObject({ ip: '8.8.8.8', sni: 'www.wikipedia.org', confirm: true })
    installed = true
    await route.fulfill({ status: 202, json: { state: 'running', id: 'isolated-ui-job' } })
  })
  await page.route('**/api/setup/import', async route => {
    imported = true
    await route.fulfill({ status: 202, json: { state: 'succeeded', message: 'Сервер импортирован' } })
  })
  await page.goto('/')
  await page.getByLabel('Имя администратора').fill('e2e-owner')
  await page.getByLabel('Пароль', { exact: true }).fill('e2e-only-long-password')
  await page.getByRole('button', { name: 'Войти в панель' }).click()
  await page.getByRole('button', { name: 'Настройки', exact: true }).click()
  await expect(page.getByLabel('Публичный IPv4 VPS')).toHaveValue('8.8.8.8')
  await page.getByRole('checkbox', { name: /Разрешаю установить Xray/ }).check()
  await page.getByRole('button', { name: 'Установить Xray + REALITY', exact: true }).click()
  await expect(page.getByText('Xray готов к импорту в панель', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Импортировать в панель', exact: true }).click()
  await expect(page.getByText('Сервер подключён к панели.', { exact: false })).toBeVisible()
})
