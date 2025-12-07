from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
import os
import yt_dlp
from moviepy.video.io.VideoFileClip import VideoFileClip
import uuid

# FFMPEG
os.environ["PATH"] += os.pathsep + r"C:\ffmpeg-master-latest-win64-gpl-shared\bin"

BOT_TOKEN = os.getenv("TOKEN")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Храним временные YouTube-запросы
youtube_tasks = {}

def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📥 YouTube", callback_data="youtube"),
                InlineKeyboardButton(text="📸 Instagram", callback_data="instagram")
            ],
            [
                InlineKeyboardButton(text="🎵 TikTok", callback_data="tiktok")
            ],
            [
                InlineKeyboardButton(text="🎧 Конвертировать", callback_data="convert")
            ]
        ]
    )

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Привет! Выбирай действие:", reply_markup=main_menu())

@dp.callback_query(lambda c: c.data in ["youtube", "instagram", "tiktok", "convert"])
async def process_callback(callback_query: types.CallbackQuery):
    d = callback_query.data

    if d == "youtube":
        await callback_query.message.answer("Отправь ссылку YouTube📥")
    elif d == "instagram":
        await callback_query.message.answer("Отправь ссылку Instagram 📸")
    elif d == "tiktok":
        await callback_query.message.answer("Отправь ссылку TikTok 🎵")
    elif d == "convert":
        await callback_query.message.answer(
            "🎧 Конвертация видео в MP3\n\n"
            "Этот бот позволяет конвертировать видео с YouTube, Instagram и TikTok в MP3.\n"
            "❗ Чтобы конвертация прошла успешно, отправляйте видео в **низком или среднем качестве**.\n"
            "Большие видео (>50 МБ) могут не конвертироваться или не отправляться через Telegram из за его ограничени.\n\n"
            "Отправьте видео, и я подготовлю аудио для скачивания.🎧"
        )


    await callback_query.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    url = message.text.strip()

    # --- YOUTUBE ---
    if "youtube" in url or "youtu.be" in url:
        await message.answer("⏳ Получаем форматы...")

        formats = get_youtube_formats(url)
        if not formats:
            await message.answer("❌ Не удалось получить форматы")
            return

        # Создаём уникальный ключ для хранения URL
        key = str(uuid.uuid4())
        youtube_tasks[key] = url

        buttons = [
            InlineKeyboardButton(text=f"{res}p", callback_data=f"ytq_{key}_{res}")
            for res in formats
        ]

        markup = InlineKeyboardMarkup(
            inline_keyboard=[buttons[i:i+3] for i in range(0, len(buttons), 3)]
        )

        await message.answer("Выбери качество:", reply_markup=markup)
        return

    # --- INSTAGRAM ---
    if "instagram.com" in url:
        await message.answer("⏳ Скачиваю Instagram...")
        video = download_simple(url)
        await send_video(message, video)
        return

    # --- TIKTOK ---
    if "tiktok.com" in url:
        await message.answer("⏳ Скачиваю TikTok...")
        video = download_simple(url)
        await send_video(message, video)
        return

    await message.answer("❌ Я работаю только с YouTube, Instagram и TikTok ссылками.")

@dp.callback_query(lambda c: c.data.startswith("ytq_"))
async def handle_youtube_quality(callback_query: types.CallbackQuery):
    _, key, quality = callback_query.data.split("_")

    url = youtube_tasks.get(key)
    if not url:
        await callback_query.answer("Ошибка данных", show_alert=True)
        return

    await callback_query.message.answer(f"⏳ Скачиваю {quality}p...")

    video = download_youtube(url, quality)
    await send_video(callback_query.message, video)

    await callback_query.answer()
    youtube_tasks.pop(key, None)

@dp.message(F.video)
async def handle_video(message: types.Message):
    downloaded_file = os.path.join(DOWNLOAD_DIR, message.video.file_unique_id + ".mp4")

    file_info = await bot.get_file(message.video.file_id)
    await bot.download_file(file_info.file_path, downloaded_file)

    size_mb = message.video.file_size / (1024*1024)
    if size_mb > 50:
        link = NGROK_URL + "/" + os.path.basename(downloaded_file)
        await message.answer(f"Видео большое ({size_mb:.1f} MB). Ссылка:\n{link}")
        return

    await message.answer("⏳ Конвертирую в MP3...")

    audio = convert_to_mp3(downloaded_file)
    if not audio:
        await message.answer("❌ Ошибка конвертации")
        return

    await message.answer_document(FSInputFile(audio))
    await message.answer("Готово. Выбирай дальше:", reply_markup=main_menu())

# ========== ФУНКЦИИ ==========

def get_youtube_formats(url):
    try:
        ydl_opts = {"quiet": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = []

            for f in info["formats"]:
                h = f.get("height")
                if h and h <= 720:
                    formats.append(h)

            formats = sorted(set(formats), reverse=True)
            return formats

    except Exception:
        return []

def download_youtube(url, quality):
    try:
        ydl_opts = {
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "format": f"bestvideo[height<={quality}]+bestaudio/best",
            "noplaylist": True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception:
        return None

def download_simple(url):
    try:
        ydl_opts = {
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "format": "mp4"
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception:
        return None

# ---------- Конвертация в MP3 ----------
def convert_to_mp3(video_path):
    try:
        clip = VideoFileClip(video_path)

        if clip.audio is None:
            clip.close()
            return None

        audio_path = os.path.splitext(video_path)[0] + ".mp3"
        # Ставим битрейт ниже, чтобы уменьшить размер
        clip.audio.write_audiofile(audio_path, bitrate="128k")
        clip.close()

        # Проверка размера
        if os.path.getsize(audio_path) > 50*1024*1024:
            return "too_big"
        return audio_path
    except Exception as e:
        print("Ошибка конвертации:", e)
        return None

# ---------- Обработка видео ----------
@dp.message(F.video)
async def handle_video(message: types.Message):
    downloaded_file = os.path.join(DOWNLOAD_DIR, os.path.basename(message.video.file_name or "video.mp4"))
    file_info = await bot.get_file(message.video.file_id)
    await bot.download_file(file_info.file_path, downloaded_file)

    await message.answer("⏳ Конвертирую видео в MP3...")
    result = convert_to_mp3(downloaded_file)

    if result == "too_big":
        await message.answer("❌ Файл слишком большой для отправки в Telegram")
    elif result is None:
        await message.answer("❌ Ошибка конвертации")
    else:
        await message.answer_document(FSInputFile(result))

    await message.answer("Готово. Выбирай дальше:", reply_markup=main_menu())



async def send_video(message, path):
    if not path:
        await message.answer("❌ Ошибка скачивания")
        return

    size_mb = os.path.getsize(path) / (1024*1024)
    if size_mb > 50:
        link = NGROK_URL + "/" + os.path.basename(path)
        await message.answer(f"Видео большое ({size_mb:.1f} MB). Ссылка:\n{link}")
    else:
        await message.answer_document(FSInputFile(path))

    await message.answer("Готово. Выбирай дальше:", reply_markup=main_menu())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

