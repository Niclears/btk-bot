import os
import sys
import subprocess
from datetime import datetime, timedelta

# Сначала устанавливаем библиотеки
print("🔄 Проверка и установка библиотек...")

packages = ['pytelegrambotapi', 'requests', 'beautifulsoup4', 'python-dotenv', 'flask']
for package in packages:
    try:
        __import__(package.replace('-', '_'))
        print(f"✅ {package} уже установлен")
    except ImportError:
        print(f"📦 Устанавливаю {package}...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

# Теперь импортируем все библиотеки
import telebot
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
import sqlite3

print("✅ Все библиотеки загружены")

# ---------- Flask сервер для UptimeRobot ----------
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот расписания БТК работает!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
    print("🌐 Flask-сервер запущен на порту 8080")

# ---------- Загружаем токен ----------
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    print("❌ ОШИБКА: Не найден токен в файле .env")
    print("Создай файл .env и добавь строку: BOT_TOKEN=твой_токен")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# ---------- База данных ----------
def init_db():
    conn = sqlite3.connect('schedule.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, group_name TEXT)''')
    conn.commit()
    conn.close()
    print("💾 База данных инициализирована")

init_db()

# ---------- РАСПИСАНИЕ ЗВОНКОВ ----------
def get_bell_schedule(day_of_week):
    """
    Возвращает расписание звонков для указанного дня недели
    day_of_week: 0-6 (понедельник-воскресенье)
    """
    days = {
        0: "ПОНЕДЕЛЬНИК",
        1: "ВТОРНИК",
        2: "СРЕДА",
        3: "ЧЕТВЕРГ",
        4: "ПЯТНИЦА",
        5: "СУББОТА",
        6: "ВОСКРЕСЕНЬЕ"
    }

    day_name = days.get(day_of_week, "")

    # Расписание для понедельника, среды, пятницы
    mon_wed_fri = [
        ("1 пара", "8.00 – 8.45", "8.55 – 9.40"),
        ("2 пара", "9.50 – 10.35", "11.00 – 11.45"),
        ("3 пара", "12.20 – 13.05", "13.15 – 14.00"),
        ("4 пара", "14.10 – 14.55", "15.05 – 15.50"),
        ("5 пара", "16.00 – 16.45", "16.55 – 17.40"),
        ("6 пара", "17.50 – 18.35", "18.45 – 19.30")
    ]

    # Расписание для вторника
    tuesday = [
        ("1 пара", "8.00 – 8.45", "8.55 – 9.40"),
        ("2 пара", "9.50 – 10.35", "11.00 – 11.45"),
        ("3 пара", "12.20 – 13.05", "13.15 – 14.00"),
        ("4 пара", "15.05 – 15.50", "16.00 – 16.45"),
        ("5 пара", "16.55 – 17.40", "17.50 – 18.35"),
        ("6 пара", "18.45 – 19.30", "19.40 – 20.25")
    ]

    # Расписание для четверга
    thursday = [
        ("1 пара", "8.00 – 8.45", "8.55 – 9.40"),
        ("2 пара", "9.50 – 10.35", "11.00 – 11.45"),
        ("3 пара", "12.20 – 13.05", "13.15 – 14.00"),
        ("4 пара", "14.45 – 15.30", "15.40 – 16.25"),
        ("5 пара", "16.35 – 17.20", "17.30 – 18.15"),
        ("6 пара", "18.25 – 19.10", "19.20 – 20.05")
    ]

    # Расписание для субботы
    saturday = [
        ("1 пара", "8.00 – 8.45", "8.55 – 9.40"),
        ("2 пара", "9.50 – 10.35", "10.45 – 11.30"),
        ("3 пара", "11.50 – 12.35", "12.40 – 13.25"),
        ("4 пара", "13.35 – 14.20", "14.30 – 15.15"),
        ("5 пара", "15.25 – 16.10", "16.20 – 17.05")
    ]

    if day_of_week in [0, 2, 4]:  # ПН, СР, ПТ
        schedule = mon_wed_fri
        special = ""
    elif day_of_week == 1:  # ВТ
        schedule = tuesday
        special = "\n⏰ <b>Классный час:</b> 14.10 – 14.55\n"
    elif day_of_week == 3:  # ЧТ
        schedule = thursday
        special = "\n⏰ <b>Часы информации:</b> 14.10 – 14.35\n"
    elif day_of_week == 5:  # СБ
        schedule = saturday
        special = ""
    else:  # ВС - нет занятий
        return "🎉 Воскресенье - выходной день!"

    # Форматируем расписание
    text = f"🔔 <b>РАСПИСАНИЕ ЗВОНКОВ</b>\n📅 <b>{day_name}</b>\n"
    text += "══════════════════════\n\n"

    for lesson, first, second in schedule:
        text += f"<b>{lesson}:</b>\n"
        text += f"  ⏱️ <b>{first}</b> (1 подгруппа)\n"
        text += f"  ⏱️ <b>{second}</b> (2 подгруппа)\n\n"

    text += special
    text += "══════════════════════"

    return text

# ---------- Парсинг расписания занятий ----------
def get_schedule_from_site(group_name):
    url = "https://www.bartc.by/index.php/ru/obuchayushchemusya/dnevnoe-otdelenie/tekushchee-raspisanie"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')

        table = soup.find('table')
        if not table:
            print("❌ Таблица не найдена")
            return []

        schedule_items = []
        rows = table.find_all('tr')[1:]  # пропускаем заголовок

        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 7:
                date = cells[0].text.strip()
                group = cells[1].text.strip()
                lesson_num = cells[2].text.strip()
                subject = cells[3].text.strip()
                teacher = cells[4].text.strip()
                room = cells[5].text.strip()

                if group == group_name:
                    schedule_items.append({
                        'date': date,
                        'lesson_num': lesson_num,
                        'subject': subject,
                        'teacher': teacher,
                        'room': room
                    })

        print(f"✅ Найдено {len(schedule_items)} занятий для группы {group_name}")
        return schedule_items

    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        return []
    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}")
        return []

def get_lesson_time(lesson_num, day_of_week):
    """
    Возвращает время начала и конца пары по номеру и дню недели
    """
    # ПН, СР, ПТ
    mon_wed_fri = {
        1: "8.00 – 9.40",
        2: "9.50 – 11.45",
        3: "12.20 – 14.00",
        4: "14.10 – 15.50",
        5: "16.00 – 17.40",
        6: "17.50 – 19.30"
    }

    # ВТ
    tuesday = {
        1: "8.00 – 9.40",
        2: "9.50 – 11.45",
        3: "12.20 – 14.00",
        4: "15.05 – 16.45",
        5: "16.55 – 18.35",
        6: "18.45 – 20.25"
    }

    # ЧТ
    thursday = {
        1: "8.00 – 9.40",
        2: "9.50 – 11.45",
        3: "12.20 – 14.00",
        4: "14.45 – 16.25",
        5: "16.35 – 18.15",
        6: "18.25 – 20.05"
    }

    # СБ
    saturday = {
        1: "8.00 – 9.40",
        2: "9.50 – 11.30",
        3: "11.50 – 13.25",
        4: "13.35 – 15.15",
        5: "15.25 – 17.05"
    }

    if day_of_week in [0, 2, 4]:  # ПН, СР, ПТ
        return mon_wed_fri.get(lesson_num)
    elif day_of_week == 1:  # ВТ
        return tuesday.get(lesson_num)
    elif day_of_week == 3:  # ЧТ
        return thursday.get(lesson_num)
    elif day_of_week == 5:  # СБ
        return saturday.get(lesson_num)
    else:
        return None

def format_schedule_with_day(schedule, group_name, target_day, period_name):
    """Форматирует расписание с учетом конкретного дня недели для времени пар"""
    if not schedule:
        return f"😕 Нет расписания для группы {group_name}"

    # Словарь для перевода дня недели
    days_ru = {
        0: "ПОНЕДЕЛЬНИК",
        1: "ВТОРНИК", 
        2: "СРЕДА",
        3: "ЧЕТВЕРГ",
        4: "ПЯТНИЦА",
        5: "СУББОТА",
        6: "ВОСКРЕСЕНЬЕ"
    }

    text = f"📚 <b>РАСПИСАНИЕ {period_name}</b>\n"
    text += f"👥 <b>Группа {group_name}</b>\n"
    if period_name in ["СЕГОДНЯ", "ЗАВТРА"]:
        text += f"📅 <b>{days_ru[target_day]}</b>\n"
    text += "══════════════════════\n"

    current_date = ""
    count = 0

    for item in schedule:
        count += 1
        if item['date'] != current_date:
            current_date = item['date']
            text += f"\n📅 <b>{current_date}</b>\n"
            text += "──────────────────\n"

        text += f"<b>{item['lesson_num']} пара:</b>\n"
        text += f"📖 <b>{item['subject']}</b>\n"
        text += f"👨‍🏫 {item['teacher']}\n"
        text += f"🚪 Кабинет: {item['room']}\n"

        # Добавляем время пары с учетом дня недели
        if item['lesson_num'].isdigit():
            lesson_time = get_lesson_time(int(item['lesson_num']), target_day)
            if lesson_time:
                text += f"⏱️ {lesson_time}\n"

        text += "\n"

    text += "══════════════════════\n"
    text += f"📊 <b>Всего пар:</b> {count}"

    return text

# ---------- Команды бота ----------
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('📅 Сегодня', '📆 Завтра', '📚 Неделя')
    markup.add('🔔 Звонки', 'ℹ️ Помощь')

    welcome_text = (
        "👋 <b>Привет! Я бот расписания БТК</b>\n\n"
        "📌 <b>Что я умею:</b>\n"
        "• Показывать расписание занятий\n"
        "• Показывать расписание звонков\n"
        "• Сохранять твою группу\n\n"
        "📝 <b>Как пользоваться:</b>\n"
        "1. Отправь номер группы (например, 213)\n"
        "2. Нажимай кнопки для просмотра\n\n"
        "🎯 <b>Кнопки:</b>\n"
        "📅 Сегодня - расписание на сегодня\n"
        "📆 Завтра - расписание на завтра\n"
        "📚 Неделя - всё расписание\n"
        "🔔 Звонки - расписание звонков"
    )

    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode='HTML',
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text

    if text == '📅 Сегодня':
        show_schedule(message, 'today')
    elif text == '📆 Завтра':
        show_schedule(message, 'tomorrow')
    elif text == '📚 Неделя':
        show_schedule(message, 'week')
    elif text == '🔔 Звонки':
        show_bell_schedule(message)
    elif text == 'ℹ️ Помощь':
        show_help(message)
    else:
        # Сохраняем группу
        try:
            conn = sqlite3.connect('schedule.db')
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO users (user_id, group_name) VALUES (?, ?)",
                      (message.chat.id, text))
            conn.commit()
            conn.close()

            bot.send_message(
                message.chat.id,
                f"✅ <b>Группа {text} сохранена!</b>\n\nТеперь нажимай кнопки для просмотра расписания",
                parse_mode='HTML'
            )
        except Exception as e:
            bot.send_message(message.chat.id, "❌ Ошибка при сохранении группы")
            print(f"Ошибка БД: {e}")

def show_bell_schedule(message):
    """Показывает расписание звонков"""
    today = datetime.now().weekday()

    # Получаем расписание на сегодня
    bell_text = get_bell_schedule(today)

    # Добавляем информацию о завтрашнем дне
    tomorrow = (today + 1) % 7
    tomorrow_name = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"][tomorrow]

    full_text = (
        f"{bell_text}\n\n"
        f"📌 <b>Завтра ({tomorrow_name}):</b>\n"
        f"Используй кнопку 📆 Завтра для расписания занятий"
    )

    bot.send_message(message.chat.id, full_text, parse_mode='HTML')

def show_help(message):
    help_text = (
        "ℹ️ <b>ПОМОЩЬ ПО БОТУ</b>\n\n"
        "📌 <b>Основные команды:</b>\n"
        "• <b>Отправь номер группы</b> - сохранить группу\n"
        "• <b>📅 Сегодня</b> - расписание на сегодня\n"
        "• <b>📆 Завтра</b> - расписание на завтра\n"
        "• <b>📚 Неделя</b> - всё расписание\n"
        "• <b>🔔 Звонки</b> - расписание звонков\n\n"
        "❓ <b>Если бот не отвечает:</b>\n"
        "• Проверь, сохранена ли группа\n"
        "• Попробуй нажать /start\n"
        "• Напиши позже, если сайт колледжа недоступен\n\n"
        "🛠️ <b>Разработчик:</b> @Михась"
    )
    bot.send_message(message.chat.id, help_text, parse_mode='HTML')

def show_schedule(message, period):
    # Получаем группу пользователя
    try:
        conn = sqlite3.connect('schedule.db')
        c = conn.cursor()
        c.execute("SELECT group_name FROM users WHERE user_id = ?", (message.chat.id,))
        result = c.fetchone()
        conn.close()
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка при получении данных")
        print(f"Ошибка БД: {e}")
        return

    if not result:
        bot.send_message(message.chat.id, "❌ Сначала отправь номер группы")
        return

    group = result[0]

    msg = bot.send_message(message.chat.id, f"🔍 <b>Ищу расписание для группы {group}...</b>", parse_mode='HTML')

    schedule = get_schedule_from_site(group)

    if schedule:
        # Определяем день недели для показа времени пар
        today = datetime.now().weekday()

        if period == 'today':
            target_day = today
            period_name = "СЕГОДНЯ"
            # Получаем сегодняшнюю дату в разных форматах
            today_date = datetime.now()
            date_formats = [
                today_date.strftime("%d-%b").lower(),           # 23-фев
                today_date.strftime("%-d-%b").lower(),          # 23-фев (без нуля)
                today_date.strftime("%d.%m"),                   # 23.02
                today_date.strftime("%d/%m"),                   # 23/02
                f"{today_date.day} {today_date.strftime('%b')}".lower()  # 23 фев
            ]
        elif period == 'tomorrow':
            target_day = (today + 1) % 7
            period_name = "ЗАВТРА"
            # Получаем завтрашнюю дату в разных форматах
            tomorrow_date = datetime.now() + timedelta(days=1)
            date_formats = [
                tomorrow_date.strftime("%d-%b").lower(),        # 24-фев
                tomorrow_date.strftime("%-d-%b").lower(),       # 24-фев (без нуля)
                tomorrow_date.strftime("%d.%m"),                # 24.02
                tomorrow_date.strftime("%d/%m"),                # 24/02
                f"{tomorrow_date.day} {tomorrow_date.strftime('%b')}".lower()  # 24 фев
            ]
        else:  # week
            target_day = today
            period_name = "НА БЛИЖАЙШИЕ ДНИ"
            # Для недели показываем всё расписание
            text = format_schedule_with_day(schedule, group, target_day, period_name)
            try:
                bot.edit_message_text(text, message.chat.id, msg.message_id, parse_mode='HTML')
            except Exception as e:
                print(f"Ошибка при редактировании: {e}")
                bot.send_message(message.chat.id, text, parse_mode='HTML')
            return

        # Фильтруем расписание по дате (пробуем все форматы)
        filtered_schedule = []

        # Сначала выводим все доступные даты для отладки
        available_dates = set()
        for item in schedule:
            available_dates.add(item['date'])
        print(f"📅 Доступные даты на сайте: {sorted(available_dates)}")
        print(f"🔍 Ищем дату: {date_formats[0]}")

        # Ищем совпадение по любому из форматов
        for item in schedule:
            item_date = item['date'].lower().strip()
            for date_format in date_formats:
                if date_format in item_date or item_date in date_format:
                    filtered_schedule.append(item)
                    break

        # Если не нашли, пробуем просто по дню месяца
        if not filtered_schedule and period in ['today', 'tomorrow']:
            target_day_num = datetime.now().day if period == 'today' else (datetime.now() + timedelta(days=1)).day
            for item in schedule:
                # Проверяем, есть ли номер дня в строке даты
                if str(target_day_num) in item['date']:
                    filtered_schedule.append(item)

        if not filtered_schedule and period in ['today', 'tomorrow']:
            # Показываем пользователю доступные даты
            dates_list = "\n".join(sorted(list(available_dates))[:5])
            bot.edit_message_text(
                f"😕 <b>Нет расписания на {period_name.lower()}</b>\n\n"
                f"Для группы {group} не найдено занятий на {date_formats[0]}.\n\n"
                f"📅 <b>Доступные даты:</b>\n{dates_list}\n\n"
                f"Попробуй выбрать другую группу или посмотреть всё расписание (📚 Неделя)",
                message.chat.id,
                msg.message_id,
                parse_mode='HTML'
            )
            return

        # Форматируем с правильным днем недели для времени пар
        text = format_schedule_with_day(filtered_schedule, group, target_day, period_name)

        try:
            bot.edit_message_text(text, message.chat.id, msg.message_id, parse_mode='HTML')
        except Exception as e:
            print(f"Ошибка при редактировании: {e}")
            bot.send_message(message.chat.id, text, parse_mode='HTML')
    else:
        bot.edit_message_text(
            "😕 <b>Не удалось найти расписание.</b>\n\n"
            "Проверь номер группы или попробуй позже.\n"
            "Возможно, сайт колледжа временно недоступен.",
            message.chat.id,
            msg.message_id,
            parse_mode='HTML'
        )
# ---------- Запуск ----------
if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 ЗАПУСК БОТА РАСПИСАНИЯ БТК")
    print("="*50)

    # Запускаем Flask в отдельном потоке
    keep_alive()

    print("✅ Бот готов к работе!")
    print("📱 Найди своего бота в Telegram и отправь /start")
    print("="*50 + "\n")

    # Запускаем бота
    try:
        bot.polling(non_stop=True, interval=0)
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")