import asyncio
import json
import logging
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

async def init_db():
    async with aiosqlite.connect("database.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            count INTEGER NOT NULL,
            FOREIGN KEY(staff_id) REFERENCES staff(id),
            UNIQUE(staff_id, date)
        )
        """)
        await db.commit()

API_TOKEN = '8018442623:AAGpqIhWdGD67BgLFwMslOHw5P4sIaI26zo'
GROUP_CHAT_ID = -1002893104615  # Ваш ID группы для отчётов
ADMIN_IDS = {6039652860, 1334728666}  # ID админов

DATA_FILE = 'data.json'
LOG_FILE = 'reports_log.json'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# --- FSM для добавления фото ---
class AddPhoto(StatesGroup):
    waiting_photo_count = State()
    waiting_staff_name = State()

# --- FSM для добавления сотрудника ---
class AddStaff(StatesGroup):
    waiting_new_staff_name = State()

# --- FSM для редактирования имени сотрудника ---
class EditStaffName(StatesGroup):
    waiting_old_name = State()
    waiting_new_name = State()

# --- FSM для удаления сотрудника ---
class DeleteStaff(StatesGroup):
    waiting_staff_name = State()

# --- FSM для редактирования отчёта (данных по фото) ---
class EditReport(StatesGroup):
    waiting_staff_name = State()
    waiting_date = State()
    waiting_new_count = State()

# Загрузка/сохранение данных
def load_data():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_log():
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_log(log):
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=4)

reports_log = load_log()

def is_admin(user_id):
    return user_id in ADMIN_IDS

# Главное меню с кнопками и иконками
def main_menu(user_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Отчёт всех сотрудников 📋"))
    if is_admin(user_id):
        kb.add(KeyboardButton("Добавить сотрудника ➕"))
        kb.add(KeyboardButton("Добавить фото 📷"))
        kb.add(KeyboardButton("Изменить имя сотрудника ✏️"))
        kb.add(KeyboardButton("Удалить сотрудника 🗑️"))
        kb.add(KeyboardButton("Отчёт с отправкой 📤"))
    return kb

# Клавиатура сотрудников для inline кнопок
def get_staff_keyboard(prefix=""):
    data = load_data()
    kb = InlineKeyboardMarkup(row_width=1)
    for name in data.keys():
        kb.insert(InlineKeyboardButton(name, callback_data=f"{prefix}{name}"))
    return kb

# Команда /start
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Это бот для учёта фото сотрудников.\n"
        "Используйте кнопки ниже для управления.",
        reply_markup=main_menu(message.from_user.id)
    )

# Обработка кнопок главного меню
@dp.message_handler()
async def main_menu_handler(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id

    if text == "Отчёт всех сотрудников 📋":
        data = load_data()
        today = datetime.now().strftime("%Y-%m-%d")
        if not data:
            await message.answer("Пока нет данных.")
            return
        lines = [f"*Отчёт за {today}:*"]
        for name, records in data.items():
            day_count = records.get(today, 0)
            total_count = sum(records.values())
            lines.append(f"• *{name}* — сегодня: _{day_count}_, всего: _{total_count}_")
        await message.answer("\n".join(lines), parse_mode='Markdown')

    elif text == "Добавить сотрудника ➕":
        if not is_admin(user_id):
            await message.answer("У вас нет прав.")
            return
        await message.answer("Введите имя нового сотрудника:")
        await AddStaff.waiting_new_staff_name.set()

    elif text == "Добавить фото 📷":
        if not is_admin(user_id):
            await message.answer("У вас нет прав.")
            return
        data = load_data()
        if not data:
            await message.answer("Нет сотрудников, добавьте их сначала.")
            return
        await message.answer("Выберите сотрудника:", reply_markup=get_staff_keyboard(prefix="addphoto_"))

    elif text == "Изменить имя сотрудника ✏️":
        if not is_admin(user_id):
            await message.answer("У вас нет прав.")
            return
        data = load_data()
        if not data:
            await message.answer("Нет сотрудников для редактирования.")
            return
        await message.answer("Выберите сотрудника для изменения имени:", reply_markup=get_staff_keyboard(prefix="editname_"))

    elif text == "Удалить сотрудника 🗑️":
        if not is_admin(user_id):
            await message.answer("У вас нет прав.")
            return
        data = load_data()
        if not data:
            await message.answer("Нет сотрудников для удаления.")
            return
        await message.answer("Выберите сотрудника для удаления:", reply_markup=get_staff_keyboard(prefix="delstaff_"))

    elif text == "Отчёт с отправкой 📤":
        if not is_admin(user_id):
            await message.answer("У вас нет прав.")
            return
        report = create_report()
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("Отправить отчёт", callback_data="send_report"),
            InlineKeyboardButton("Изменить", callback_data="edit_from_report")
        )
        keyboard.add(InlineKeyboardButton("Отмена", callback_data="cancel_report"))
        await message.answer(report, parse_mode='Markdown', reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == 'edit_from_report')
async def callback_edit_from_report(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("У вас нет прав.", show_alert=True)
        return
    data = load_data()
    if not data:
        await call.message.answer("Нет данных для редактирования.")
        return
    await call.message.answer("Выберите сотрудника для редактирования отчёта:", reply_markup=get_staff_keyboard(prefix="editreport_"))
    await call.answer()

# Обработка выбора сотрудника из inline клавиатуры
@dp.callback_query_handler(lambda c: c.data.startswith("addphoto_"))
async def callback_addphoto(call: types.CallbackQuery, state: FSMContext):
    name = call.data[len("addphoto_"):]
    await call.message.answer(f"Введите количество фото для сотрудника {name} за сегодня:")
    await AddPhoto.waiting_photo_count.set()
    await state.update_data(staff_name=name)
    await call.answer()

@dp.message_handler(state=AddPhoto.waiting_photo_count)
async def process_photo_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text)
        if count < 0:
            raise ValueError
    except ValueError:
        await message.reply("Введите корректное число.")
        return

    data = load_data()
    state_data = await state.get_data()
    name = state_data['staff_name']
    today = datetime.now().strftime("%Y-%m-%d")

    if name not in data:
        data[name] = {}

    if today not in data[name]:
        data[name][today] = 0

    data[name][today] += count
    save_data(data)

    await message.answer(f"Добавлено {count} фото сотруднику {name} за {today}.")
    await state.finish()

# Добавление сотрудника
@dp.message_handler(state=AddStaff.waiting_new_staff_name)
async def process_new_staff_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    if not new_name:
        await message.reply("Имя не может быть пустым.")
        return

    data = load_data()
    if new_name in data:
        await message.reply("Такой сотрудник уже есть.")
        await state.finish()
        return

    data[new_name] = {}
    save_data(data)

    await message.answer(f"Сотрудник '{new_name}' добавлен.")
    await state.finish()

# Изменение имени сотрудника - выбор сотрудника
@dp.callback_query_handler(lambda c: c.data.startswith("editname_"))
async def callback_editname_start(call: types.CallbackQuery, state: FSMContext):
    name = call.data[len("editname_"):]
    await call.message.answer(f"Введите новое имя для сотрудника {name}:")
    await EditStaffName.waiting_new_name.set()
    await state.update_data(old_name=name)
    await call.answer()

@dp.message_handler(state=EditStaffName.waiting_new_name)
async def process_edit_staff_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    state_data = await state.get_data()
    old_name = state_data.get("old_name")

    if not new_name:
        await message.reply("Имя не может быть пустым.")
        return

    data = load_data()
    if new_name in data:
        await message.reply("Такое имя уже существует.")
        await state.finish()
        return

    # Переименовываем
    data[new_name] = data.pop(old_name)
    save_data(data)

    await message.answer(f"Имя сотрудника '{old_name}' изменено на '{new_name}'.")
    await state.finish()

# Удаление сотрудника - выбор
@dp.callback_query_handler(lambda c: c.data.startswith("delstaff_"))
async def callback_delstaff_start(call: types.CallbackQuery):
    name = call.data[len("delstaff_"):]
    data = load_data()
    if name in data:
        del data[name]
        save_data(data)
        await call.message.answer(f"Сотрудник '{name}' удалён.")
    else:
        await call.message.answer("Сотрудник не найден.")
    await call.answer()

# Редактирование данных отчёта - выбор сотрудника
@dp.callback_query_handler(lambda c: c.data.startswith("editreport_"))
async def callback_edit_report_staff(call: types.CallbackQuery, state: FSMContext):
    name = call.data[len("editreport_"):]
    await call.message.answer(
        f"Введите дату для изменения (формат ГГГГ-ММ-ДД) для сотрудника {name} (например, 2025-08-03):"
    )
    await EditReport.waiting_date.set()
    await state.update_data(staff_name=name)
    await call.answer()

# Ввод даты
@dp.message_handler(state=EditReport.waiting_date)
async def process_edit_report_date(message: types.Message, state: FSMContext):
    date_text = message.text.strip()
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        await message.reply("Некорректный формат даты. Попробуйте снова.")
        return

    await state.update_data(date=date_text)
    await message.answer("Введите новое количество фото для этой даты:")
    await EditReport.waiting_new_count.set()

# Ввод нового количества фото
@dp.message_handler(state=EditReport.waiting_new_count)
async def process_edit_report_count(message: types.Message, state: FSMContext):
    try:
        new_count = int(message.text)
        if new_count < 0:
            raise ValueError
    except ValueError:
        await message.reply("Введите корректное число.")
        return

    state_data = await state.get_data()
    name = state_data['staff_name']
    date = state_data['date']

    data = load_data()
    if name not in data:
        await message.answer("Сотрудник не найден.")
        await state.finish()
        return

    data[name][date] = new_count
    save_data(data)

    await message.answer(f"Данные для сотрудника {name} на дату {date} обновлены: {new_count} фото.")
    await state.finish()

# Создаём отчёт (для отправки в группу)
def create_report():
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")

    lines = [f"*Отчёт за {today}*:\n"]
    for name, records in data.items():
        day_count = records.get(today, 0)
        total_count = sum(records.values())
        lines.append(f"• *{name}* — сегодня: _{day_count}_, всего: _{total_count}_")

    return "\n".join(lines)

# Отправка отчёта с подтверждением
@dp.callback_query_handler(lambda c: c.data in ['send_report', 'cancel_report'])
async def callback_confirm_report(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("У вас нет прав.", show_alert=True)
        return

    if call.data == 'send_report':
        report = create_report()
        await bot.send_message(GROUP_CHAT_ID, report, parse_mode='Markdown')
        reports_log.append({
            "timestamp": datetime.now().isoformat(),
            "report": report
        })
        save_log(reports_log)
        await call.message.edit_reply_markup()
        await call.answer("Отчёт отправлен!")
    else:
        await call.message.edit_reply_markup()
        await call.answer("Отправка отменена.")

# Автоматическая отправка отчёта в 18:00
async def scheduled_report():
    while True:
        now = datetime.now()
        target = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now > target:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        report = create_report()
        await bot.send_message(GROUP_CHAT_ID, report, parse_mode='Markdown')


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    loop.create_task(scheduled_report())
    executor.start_polling(dp, skip_updates=True)
