# Telegram Video Bot

Универсальный Telegram-бот для скачивания видео/аудио с 13+ платформ.

**Поддерживаемые сервисы:** YouTube, TikTok, VK, Instagram, Pinterest, YouTube Music, PornHub, XVideos, Rutube, OK.ru, Deezer, Spotify, SoundCloud, Яндекс.Музыка.

---

## 1. Подготовка: что нужно получить

### 1.1. `API_ID` и `API_HASH` — данные приложения Telegram

1. Зайдите на **https://my.telegram.org/apps**
2. Войдите в аккаунт Telegram (тот же номер, что в приложении)
3. Если нет приложения — нажмите **Create Application**
4. Скопируйте `App api_id` и `App api_hash`
5. **Важно:** это не токен бота, это данные **вашего аккаунта Telegram**, под которым бот будет работать через MTProto.

### 1.2. `BOT_TOKEN` — токен бота (от BotFather)

1. Откройте в Telegram: **https://t.me/BotFather**
2. `/newbot` → название → username (например `MyVideoBot_bot`)
3. BotFather вернёт токен: `123456:ABCdef...` — скопируйте его
4. Дополнительно: `/mybots` → выберите бота → **Settings** → **Group Privacy** → **Disable** (чтобы бот видел ссылки в группах)

---

## 2. Локальный запуск (Windows)

### 2.1. Скачать код

```bash
git clone https://github.com/ВАШ_АККАУНТ/telegram_video_bot.git
cd telegram_video_bot
```

### 2.2. Установить FFmpeg

**Скачать:** https://github.com/BtbN/FFmpeg-Builds/releases

Выберите `ffmpeg-master-latest-win64-gpl.zip`:
- Распакуйте в `C:\ffmpeg`
- `Win+R` → `sysdm.cpl` → **Дополнительно** → **Переменные среды**
- В `Path` добавьте `C:\ffmpeg\bin`
- Проверка: `ffmpeg -version`

**Или через winget:**
```cmd
winget install ffmpeg
```

### 2.3. Установить Python 3.11

**Скачать:** https://www.python.org/downloads/release/python-3119/
- `Windows installer (64-bit)`
- При установке обязательно отметьте **Add Python to PATH**

Проверка:
```cmd
python --version
```

### 2.4. Создать виртуальное окружение и установить зависимости

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Если ошибка сборки `curl-cffi` — установите Rust:
- https://rustup.rs/ → запустите `rustup-init.exe`
- Переоткройте терминал
- `pip install -r requirements.txt`

### 2.5. Настроить `config.py`

Откройте `config.py` и замените значения на свои:

```python
API_ID = int(os.getenv('API_ID', 'ВАШ_API_ID'))
API_HASH = os.getenv('API_HASH', 'ВАШ_API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN', 'ВАШ_BOT_TOKEN')
```

Если планируете VK-музыку — укажите логин/пароль:
```python
VK_LOGIN = os.getenv('VK_LOGIN', '+79123456789')
VK_PASSWORD = os.getenv('VK_PASSWORD', 'ваш_пароль')
```

### 2.6. Запустить бота

```cmd
python bot.py
```

**Ожидаемый вывод:**
```
[VideoBot] Bot started! MTProto (2 GB limit)
```

Отправьте боту любую ссылку (YouTube, TikTok, OK.ru и т.д.) — он должен ответить выбором качества.

---

## 3. Деплой на Render.com

**Сайт:** https://render.com

### 3.1. Залить код на GitHub

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/ВАШ_АККАУНТ/telegram_video_bot.git
git push -u origin main
```

### 3.2. Удалить секреты из `config.py` перед пушем

**Важно:** в `config.py` лежат ваши токены. Чтобы не светить их в репозитории:

**Вариант А — очистить значения по умолчанию (рекомендуется):**
```python
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
```
Все значения будут браться только из переменных окружения.

**Вариант Б — добавить config.py в .gitignore:**
```bash
echo "config.py" >> .gitignore
```
Но тогда на Render нужно будет как-то доставить файл — неудобно.

### 3.3. Создать сервис на Render

1. Зайдите на https://dashboard.render.com
2. **New** → **Blueprint**
3. Подключите GitHub → выберите репозиторий
4. Render увидит `render.yaml` и предложит настройки

**Или вручную:**

1. **New** → **Worker**
2. На вкладке **Public Git repository** вставьте: `https://github.com/ВАШ_АККАУНТ/telegram_video_bot.git`
3. Runtime: выберите **Docker**
4. Branch: `main`

### 3.4. Добавить переменные окружения

В разделе **Environment Variables** добавьте (каждая отдельно):

| Key | Value |
|-----|-------|
| `API_ID` | ваш api_id |
| `API_HASH` | ваш api_hash |
| `BOT_TOKEN` | ваш bot_token |
| `VK_LOGIN` | (если нужно) |
| `VK_PASSWORD` | (если нужно) |
| `DEEZER_ARL` | (если нужно) |
| `TEMP_DIR` | `/data/downloads` |

**Как получить Deezer ARL:**
1. Зайдите на https://deezer.com в Chrome
2. F12 → **Application** → **Cookies** → `deezer.com` → `arl`
3. Скопируйте значение

### 3.5. Добавить диск (Disk)

Внизу страницы **Disks** → **Add Disk**:
- Name: `data`
- Mount Path: `/data`
- Size: 1 GB

Это сохранит сессию Pyrogram (`video_bot.session`) между перезапусками.

### 3.6. Deploy

Нажмите **Apply** → **Create Worker**.

Render соберёт образ, запустит бота. Логи можно смотреть в **Logs** вкладке.

---

## 4. Переменные окружения (полный список)

| Переменная | Описание | Обязательно |
|------------|----------|-------------|
| `API_ID` | ID приложения Telegram | Да |
| `API_HASH` | Хэш приложения Telegram | Да |
| `BOT_TOKEN` | Токен от BotFather | Да |
| `VK_LOGIN` | Логин VK (для музыки) | Для VK музыки |
| `VK_PASSWORD` | Пароль VK | Для VK музыки |
| `DEEZER_ARL` | ARL-кука Deezer | Для Deezer |
| `TEMP_DIR` | Папка для временных файлов | По умолч. `downloads` |

---

## 5. Команды бота

- `/start` — приветствие
- `/help` — список платформ
- `/login vk_token <токен>` — авторизация VK по OAuth токену
- `/logout` — сброс VK токена

Просто отправьте ссылку — бот предложит выбрать качество, скачает и пришлёт файл.

---

## 6. Ограничения

- Telegram: файлы до 2 ГБ (через MTProto)
- Render: бесплатный тир 512 MB RAM, спит при неактивности 15 мин (бот встаёт по входящему сообщению)
- Для продакшна: $7/мес (Starter) — без сна

---

## 7. Ссылки

| Что | Ссылка |
|-----|--------|
| Создать Telegram приложение | https://my.telegram.org/apps |
| BotFather | https://t.me/BotFather |
| Python 3.11 | https://www.python.org/downloads/release/python-3119/ |
| FFmpeg Windows | https://github.com/BtbN/FFmpeg-Builds/releases |
| Rust (для curl-cffi) | https://rustup.rs/ |
| Render.com | https://render.com |
