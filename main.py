import os
import sys
import subprocess
from datetime import datetime, timedelta
import time
import sqlite3

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

# ---------- Парсинг расписания занятий (ВСЕ СТРАНИЦЫ) ----------
def get_schedule_from_site(group_name):
    base_url = "https://www.bartc.by/index.php/ru/obuchayushchemusya/dnevnoe-otdelenie/tekushchee-raspisanie"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
        'Connection': 'keep-alive',
    }
    
    all_schedule_items = []
    page = 0
    limit = 20  # Сколько записей на странице
    
    try:
        while True:
            # Формируем URL с параметрами пагинации
            # На сайте используется limitstart
            url = f"{base_url}?limitstart={page * limit}"
            
            print(f"🔄 Загружаю страницу {page + 1}...")
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем таблицу
            table = soup.find('table')
            if not table:
                print(f"❌ На странице {page + 1} нет таблицы")
                break
            
            # Парсим строки таблицы
            rows = table.find_all('tr')[1:]  # пропускаем заголовок
            print(f"📊 Страница {page + 1}: найдено {len(rows)} строк")
            
            if not rows:
                print(f"✅ Достигнут конец данных")
                break
            
            # Ищем информацию о пагинации
            pagination = soup.find('div', class_='pagination')
            if pagination:
                # Пробуем найти общее количество записей
                counter = pagination.find('div', class_='counter')
                if counter:
                    print(f"📄 Информация о пагинации: {counter.text}")
            
            page_items = 0
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
                        all_schedule_items.append({
                            'date': date,
                            'lesson_num': lesson_num,
                            'subject': subject,
                            'teacher': teacher,
                            'room': room
                        })
                        page_items += 1
            
            print(f"✅ Страница {page + 1}: найдено {page_items} занятий для группы {group_name}")
            
            # Проверяем, есть ли следующая страница
            # Ищем ссылку "next" или "далее"
            next_link = soup.find('a', title='Вперед')
            if not next_link:
                next_link = soup.find('a', class_='next')
            if not next_link:
                next_link = soup.find('a', text=lambda t: t and ('далее' in t.lower() or 'next' in t.lower() or '>' in t))
            
            if not next_link:
                print("✅ Это последняя страница")
                break
            
            page += 1
            
            # Небольшая задержка, чтобы не нагружать сайт
            time.sleep(1)
            
        print(f"🎯 ВСЕГО найдено {len(all_schedule_items)} занятий для группы {group_name}")
        return all_schedule_items
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        return []
    except Exception as e:
        print(f"❌ Неизвестная ошибка: {e}")
        import traceback
        traceback.print_exc()
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
    
    # Группируем по датам
    dates = {}
    for item in schedule:
        if item['date'] not in dates:
            dates[item['date']] = []
        dates[item['date']].append(item)
    
    # Сортируем даты
    total_count = 0
    
    for date in sorted(dates.keys()):
        text += f"\n📅 <b>{date}</b>\n"
        text += "──────────────────\n"
        
        # Сортируем по номеру пары
        sorted_items = sorted(dates[date], key=lambda x: int(x['lesson_num']) if x['lesson_num'].isdigit() else 0)
        
        for item in sorted_items:
            total_count += 1
            text += f"<b>{item['lesson_num']} пара:</b>\n"
            text += f"📖 <b>{item['subject']}</b>\n"
            text += f"👨‍🏫 {item['teacher']}\n"
            text += f"🚪 Кабинет: {item['room']}\n"
            
            if item['lesson_num'].isdigit():
                lesson_time = get_lesson_time(int(item['lesson_num']), target_day)
                if lesson_time:
                    text += f"⏱️ {lesson_time}\n"
            
            text += "\n"
    
    text += "══════════════════════\n"
    text += f"📊 <b>Всего пар:</b> {total_count}"
    
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
        "🛠️ <b>Разработчик:</b> @твой_username"
    )
    bot.send_message(message.chat.id, help_text, parse_mode='HTML')

def show_schedule(message, period):
    # Устанавливаем часовой пояс для корректной даты
    os.environ['TZ'] = 'Europe/Minsk'
    try:
        time.tzset()
    except:
        pass
    
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
        print(f"\n{'='*50}")
        print(f"📊 ВСЕГО НАЙДЕНО: {len(schedule)} занятий для группы {group}")
        
        # Показываем все уникальные даты в расписании
        all_dates = sorted(set([item['date'] for item in schedule]))
        print(f"📅 Даты в расписании: {all_dates}")
        
        # Определяем сегодняшнюю дату
        now = datetime.now()
        
        # Словарь русских месяцев
        months_ru = {
            1: 'янв', 2: 'фев', 3: 'мар', 4: 'апр', 5: 'май', 6: 'июн',
            7: 'июл', 8: 'авг', 9: 'сен', 10: 'окт', 11: 'ноя', 12: 'дек'
        }
        
        today_str = f"{now.day}-{months_ru[now.month]}"
        tomorrow_str = f"{(now + timedelta(days=1)).day}-{months_ru[(now + timedelta(days=1)).month]}"
        
        print(f"📅 Сегодня (вычислено): {today_str}")
        print(f"📅 Завтра (вычислено): {tomorrow_str}")
        
        # Определяем день недели
        today = now.weekday()
        
        if period == 'today':
            target_day = today
            period_name = "СЕГОДНЯ"
            target_date = today_str
            
            print(f"🔍 Ищем дату: {target_date}")
            
            # Фильтруем только сегодняшние занятия
            filtered_schedule = []
            for item in schedule:
                print(f"  Сравниваем с: {item['date']} -> {item['date'].lower() == target_date.lower()}")
                if item['date'].lower() == target_date.lower():
                    filtered_schedule.append(item)
            
            print(f"✅ Найдено сегодня: {len(filtered_schedule)}")
            
            if not filtered_schedule:
                # Показываем доступные даты
                dates_list = "\n".join(all_dates[:10])
                bot.edit_message_text(
                    f"😕 <b>Нет расписания на сегодня</b>\n\n"
                    f"Для группы {group} не найдено занятий на {target_date}.\n\n"
                    f"📅 <b>Доступные даты:</b>\n{dates_list}\n\n"
                    f"Попробуй посмотреть всё расписание (📚 Неделя)",
                    message.chat.id,
                    msg.message_id,
                    parse_mode='HTML'
                )
                return
            
            text = format_schedule_with_day(filtered_schedule, group, target_day, period_name)
            
        elif period == 'tomorrow':
            target_day = (today + 1) % 7
            period_name = "ЗАВТРА"
            target_date = tomorrow_str
            
            print(f"🔍 Ищем дату: {target_date}")
            
            # Фильтруем только завтрашние занятия
            filtered_schedule = []
            for item in schedule:
                print(f"  Сравниваем с: {item['date']} -> {item['date'].lower() == target_date.lower()}")
                if item['date'].lower() == target_date.lower():
                    filtered_schedule.append(item)
            
            print(f"✅ Найдено завтра: {len(filtered_schedule)}")
            
            if not filtered_schedule:
                bot.edit_message_text(
                    f"😕 <b>Нет расписания на завтра</b>\n\n"
                    f"Для группы {group} не найдено занятий на {target_date}.\n\n"
                    f"Попробуй посмотреть всё расписание (📚 Неделя)",
                    message.chat.id,
                    msg.message_id,
                    parse_mode='HTML'
                )
                return
            
            text = format_schedule_with_day(filtered_schedule, group, target_day, period_name)
            
        else:  # week
            # Для недели показываем всё расписание
            text = format_schedule_with_day(schedule, group, today, "НА БЛИЖАЙШИЕ ДНИ")
        
        try:
            bot.edit_message_text(text, message.chat.id, msg.message_id, parse_mode='HTML')
        except Exception as e:
            print(f"Ошибка при редактировании: {e}")
            if len(text) > 4096:
                for i in range(0, len(text), 4096):
                    bot.send_message(message.chat.id, text[i:i+4096], parse_mode='HTML')
            else:
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
