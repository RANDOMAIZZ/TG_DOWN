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

### 2.5. Настроить `.env`

Скопируйте `.env.example` в `.env` и заполните свои данные:

```bash
copy .env.example .env
```

Отредактируйте `.env`:
```
API_ID=ВАШ_API_ID
API_HASH=ВАШ_API_HASH
BOT_TOKEN=ВАШ_BOT_TOKEN
```

**Важно:** `config.py` больше не содержит секретов — все данные читаются из `.env` или переменных окружения. Это безопасно для публичного репозитория.

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

## 3. Деплой на сервер (Hetzner / VPS)

Бот запускается через Docker. Подготовьте сервер с Docker Engine.

### 3.1. Клонировать репозиторий

```bash
git clone https://github.com/ВАШ_АККАУНТ/telegram_video_bot.git
cd telegram_video_bot
```

### 3.2. Создать `.env` с секретами

Скопируйте `.env.example` в `.env` и вставьте свои токены (API_ID, API_HASH, BOT_TOKEN и опциональные данные).

**`.env` добавлен в `.gitignore` — он никогда не попадёт в репозиторий.**

### 3.3. Собрать и запустить

```bash
docker build -t video-bot .
docker run -d \
  --name video-bot \
  --restart unless-stopped \
  --env-file .env \
  -v video-bot-data:/data \
  video-bot
```

Или через `start.sh` без Docker (нужен Python 3.11 + ffmpeg + deno + tor):
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./start.sh
```

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
