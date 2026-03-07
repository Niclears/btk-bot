import os
import sys
import subprocess
from datetime import datetime, timedelta
import time
import hashlib
import json
from threading import Lock
import psycopg2
import psycopg2.extras

# Сначала устанавливаем библиотеки
print("🔄 Проверка и установка библиотек...")

packages = ['pytelegrambotapi', 'requests', 'beautifulsoup4', 'python-dotenv', 'flask', 'apscheduler', 'psycopg2-binary']
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
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

print("✅ Все библиотеки загружены")

# ---------- Flask сервер для UptimeRobot ----------
app = Flask(__name__)

@app.route('/ping')
def ping():
    return "pong"

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
DATABASE_URL = os.getenv('DATABASE_URL')

if not BOT_TOKEN:
    print("❌ ОШИБКА: Не найден токен в файле .env")
    print("Создай файл .env и добавь строку: BOT_TOKEN=твой_токен")
    sys.exit(1)

if not DATABASE_URL:
    print("❌ ОШИБКА: Не найден DATABASE_URL")
    print("Добавь переменную окружения DATABASE_URL в настройках Render")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# ---------- Твой Telegram ID ----------
YOUR_USER_ID = 1702505914  # ❗ ТВОЙ ID

# ---------- НАСТРОЙКИ ----------
NOTIFICATIONS_ENABLED = True  # True - уведомления для всех подписчиков
subscribed_users = set()  # Множество подписчиков
subscribers_lock = Lock()  # Для безопасной работы с множеством

# ---------- База данных PostgreSQL ----------
def get_db_connection():
    """Создаёт подключение к базе данных"""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Создаёт все необходимые таблицы в базе данных"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Таблица пользователей и их групп
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                     user_id BIGINT PRIMARY KEY, 
                     group_name TEXT,
                     subscribed INTEGER DEFAULT 0,
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Таблица подписчиков
        c.execute('''CREATE TABLE IF NOT EXISTS subscribers (
                     user_id BIGINT PRIMARY KEY,
                     subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Таблица для хранения последнего расписания
        c.execute('''CREATE TABLE IF NOT EXISTS schedule_hash (
                     id INTEGER PRIMARY KEY CHECK (id = 1),
                     hash_value TEXT,
                     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        conn.commit()
        conn.close()
        print("💾 База данных PostgreSQL инициализирована")
        
        # Загружаем сохранённый хеш
        load_previous_hash()
        # Загружаем подписчиков
        load_subscribers()
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации БД: {e}")

def load_previous_hash():
    """Загружает предыдущий хеш из базы данных"""
    global previous_schedule_hash
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT hash_value FROM schedule_hash WHERE id = 1")
        result = c.fetchone()
        if result:
            previous_schedule_hash = result[0]
            print(f"📋 Загружен сохранённый хеш: {previous_schedule_hash[:8]}...")
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка загрузки хеша: {e}")

def save_hash(hash_value):
    """Сохраняет хеш в базу данных"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO schedule_hash (id, hash_value, updated_at) 
                     VALUES (1, %s, CURRENT_TIMESTAMP)
                     ON CONFLICT (id) DO UPDATE SET 
                     hash_value = EXCLUDED.hash_value,
                     updated_at = CURRENT_TIMESTAMP''', (hash_value,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка сохранения хеша: {e}")

def load_subscribers():
    """Загружает подписчиков из базы данных"""
    global subscribed_users
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT user_id FROM subscribers")
        rows = c.fetchall()
        with subscribers_lock:
            subscribed_users = set([row[0] for row in rows])
        conn.close()
        print(f"📋 Загружено {len(subscribed_users)} подписчиков")
    except Exception as e:
        print(f"❌ Ошибка загрузки подписчиков: {e}")

def save_subscriber(user_id):
    """Сохраняет подписчика в базу данных"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO subscribers (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        c.execute("UPDATE users SET subscribed = 1 WHERE user_id = %s", (user_id,))
        conn.commit()
        conn.close()
        # Обновляем множество в памяти
        with subscribers_lock:
            subscribed_users.add(user_id)
    except Exception as e:
        print(f"❌ Ошибка сохранения подписчика: {e}")

def remove_subscriber(user_id):
    """Удаляет подписчика из базы данных"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM subscribers WHERE user_id = %s", (user_id,))
        c.execute("UPDATE users SET subscribed = 0 WHERE user_id = %s", (user_id,))
        conn.commit()
        conn.close()
        # Обновляем множество в памяти
        with subscribers_lock:
            if user_id in subscribed_users:
                subscribed_users.remove(user_id)
    except Exception as e:
        print(f"❌ Ошибка удаления подписчика: {e}")

def save_user_group(user_id, group_name):
    """Сохраняет группу пользователя"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO users (user_id, group_name) 
                     VALUES (%s, %s) 
                     ON CONFLICT (user_id) DO UPDATE SET 
                     group_name = EXCLUDED.group_name''', 
                     (user_id, group_name))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения группы: {e}")
        return False

def get_user_group(user_id):
    """Получает группу пользователя"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT group_name FROM users WHERE user_id = %s", (user_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Ошибка получения группы: {e}")
        return None

# Инициализируем базу данных
init_db()

# ---------- ПЛАНИРОВЩИК ДЛЯ ПРОВЕРКИ РАСПИСАНИЯ ----------
previous_schedule_hash = None

def get_all_groups_schedule():
    """Получает расписание для нескольких групп, чтобы проверить изменения"""
    all_schedule = []
    # Проверяем популярные группы
    sample_groups = ['213', '301', '483', '105', '212', '295']
    
    for group in sample_groups:
        try:
            schedule = get_schedule_from_site(group)
            all_schedule.extend(schedule)
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ Ошибка при проверке группы {group}: {e}")
    
    return all_schedule

def get_schedule_hash():
    """Получает хеш текущего расписания для сравнения"""
    try:
        all_schedule = get_all_groups_schedule()
        schedule_str = json.dumps(all_schedule, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(schedule_str.encode('utf-8')).hexdigest()
    except Exception as e:
        print(f"❌ Ошибка при создании хеша: {e}")
        return None

def notify_all_users():
    """Рассылает уведомления всем подписчикам"""
    with subscribers_lock:
        if not subscribed_users:
            print("📭 Нет подписчиков для уведомления")
            return
        users_to_notify = list(subscribed_users)
    
    message = (
        "🔔 <b>ОБНОВЛЕНИЕ РАСПИСАНИЯ!</b>\n\n"
        "На сайте колледжа появились изменения.\n"
        "Нажми 📚 Неделя, чтобы посмотреть обновлённое расписание.\n\n"
        f"📅 <i>{datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"
    )
    
    success = 0
    failed = 0
    
    print(f"📨 Отправка уведомлений {len(users_to_notify)} подписчикам...")
    
    for user_id in users_to_notify:
        try:
            bot.send_message(user_id, message, parse_mode='HTML')
            success += 1
            time.sleep(0.05)
        except Exception as e:
            print(f"❌ Ошибка отправки пользователю {user_id}: {e}")
            if "Forbidden: bot was blocked by the user" in str(e):
                remove_subscriber(user_id)
                print(f"🗑️ Пользователь {user_id} удалён из подписчиков")
            failed += 1
    
    print(f"📨 Уведомления: {success} отправлено, {failed} ошибок")

def check_schedule_updates():
    """Проверяет обновления расписания"""
    global previous_schedule_hash
    
    print(f"\n{'='*50}")
    print(f"🔄 Проверка обновлений расписания ({datetime.now().strftime('%H:%M')})")
    
    try:
        current_hash = get_schedule_hash()
        
        if not current_hash:
            print("❌ Не удалось получить хеш")
            return
        
        if previous_schedule_hash and current_hash != previous_schedule_hash:
            print("✅ ИЗМЕНЕНИЯ ОБНАРУЖЕНЫ!")
            save_hash(current_hash)
            
            if NOTIFICATIONS_ENABLED:
                notify_all_users()
        else:
            print("ℹ️ Изменений нет")
        
        previous_schedule_hash = current_hash
        print(f"✅ Текущий хеш: {current_hash[:8]}...")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    print('='*50)

def start_scheduler():
    """Запускает планировщик проверки расписания"""
    scheduler = BackgroundScheduler()
    
    scheduler.add_job(
        check_schedule_updates,
        trigger=CronTrigger(minute='*/20', hour='9-20'),
        id='schedule_checker',
        replace_existing=True
    )
    
    scheduler.add_job(
        check_schedule_updates,
        trigger='date',
        id='initial_check'
    )
    
    scheduler.start()
    print("⏰ Планировщик проверки расписания запущен")
    print("⏰ Режим работы: каждые 20 минут с 9:00 до 20:00")
    print(f"👥 Уведомления будут приходить всем подписчикам")
    
    return scheduler

# ---------- РАСПИСАНИЕ ЗВОНКОВ ----------
def get_bell_schedule(day_of_week):
    """Возвращает расписание звонков для указанного дня недели"""
    days = {
        0: "ПОНЕДЕЛЬНИК", 1: "ВТОРНИК", 2: "СРЕДА", 3: "ЧЕТВЕРГ",
        4: "ПЯТНИЦА", 5: "СУББОТА", 6: "ВОСКРЕСЕНЬЕ"
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
    
    if day_of_week in [0, 2, 4]:
        schedule = mon_wed_fri
        special = ""
    elif day_of_week == 1:
        schedule = tuesday
        special = "\n⏰ <b>Классный час:</b> 14.10 – 14.55\n"
    elif day_of_week == 3:
        schedule = thursday
        special = "\n⏰ <b>Часы информации:</b> 14.10 – 14.35\n"
    elif day_of_week == 5:
        schedule = saturday
        special = ""
    else:
        return "🎉 Воскресенье - выходной день!"
    
    text = f"🔔 <b>РАСПИСАНИЕ ЗВОНКОВ</b>\n📅 <b>{day_name}</b>\n══════════════════════\n\n"
    
    for lesson, first, second in schedule:
        text += f"<b>{lesson}:</b>\n  ⏱️ <b>{first}</b> (1 подгруппа)\n  ⏱️ <b>{second}</b> (2 подгруппа)\n\n"
    
    text += special + "══════════════════════"
    return text

# ---------- Парсинг расписания занятий (ВСЕ СТРАНИЦЫ) ----------
def get_schedule_from_site(group_name):
    """
    Получает расписание через парсинг HTML-страницы колледжа.
    """
    url = "https://www.bartc.by/index.php/ru/obuchayushchemusya/dnevnoe-otdelenie/tekushchee-raspisanie"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }

    all_schedule_items = []
    page = 0
    limit = 20  # На сайте по 20 записей на страницу

    try:
        print(f"\n{'='*50}")
        print(f"🔍 НАЧАЛО ПАРСИНГА для группы: {group_name}")
        print(f"{'='*50}")

        while True:
            # Формируем URL с параметром limitstart для пагинации
            url_with_page = f"{url}?limitstart={page * limit}"
            print(f"\n📡 Запрос страницы {page + 1}: {url_with_page}")

            response = requests.get(url_with_page, headers=headers, timeout=15)
            print(f"📊 Статус ответа: {response.status_code}")

            if response.status_code != 200:
                print(f"❌ Ошибка HTTP: {response.status_code}")
                break

            response.encoding = 'utf-8'
            print(f"📏 Размер страницы: {len(response.text)} символов")

            soup = BeautifulSoup(response.text, 'html.parser')

            # Ищем таблицу по её ID или структуре
            table = soup.find('table', id='at_107')  # У таблицы есть ID!
            if not table:
                # Если не нашли по ID, ищем любую таблицу с классом ari-tbl-row
                table = soup.find('table', class_='display')
                if not table:
                    print("❌ Таблица с расписанием не найдена!")
                    break

            print("✅ Таблица найдена")

            # Находим все строки таблицы
            rows = table.find_all('tr')
            print(f"📊 Всего строк в таблице: {len(rows)}")

            if len(rows) <= 1:  # Только заголовок или пусто
                print("✅ Строк с данными нет")
                break

            page_items = 0
            for row in rows[1:]:  # Пропускаем строку заголовка
                cells = row.find_all('td')
                if len(cells) >= 7:
                    date = cells[0].text.strip()
                    group = cells[1].text.strip()
                    lesson_num = cells[2].text.strip()
                    subject = cells[3].text.strip()
                    teacher = cells[4].text.strip()
                    room = cells[5].text.strip()
                    # sub_group = cells[6].text.strip() # Пока не используем

                    if group == group_name:
                        all_schedule_items.append({
                            'date': date,
                            'lesson_num': lesson_num,
                            'subject': subject,
                            'teacher': teacher,
                            'room': room
                        })
                        page_items += 1

            print(f"✅ На странице {page + 1} найдено {page_items} занятий для группы {group_name}")

            # Проверяем, есть ли следующая страница (ищем кнопку "Вперед")
            pagination = soup.find('div', class_='dataTables_paginate')
            if pagination:
                next_link = pagination.find('a', class_='next')
                if not next_link or 'disabled' in next_link.get('class', []):
                    print("✅ Это последняя страница")
                    break
            else:
                # Если пагинации нет, значит страница одна
                break

            page += 1
            time.sleep(1)  # Небольшая задержка, чтобы не нагружать сайт

        print(f"\n🎯 ВСЕГО найдено {len(all_schedule_items)} занятий для группы {group_name}")
        print(f"{'='*50}\n")
        return all_schedule_items

    except requests.exceptions.ConnectionError as e:
        print(f"❌ Ошибка подключения: {e}")
        return []
    except requests.exceptions.Timeout as e:
        print(f"❌ Таймаут: {e}")
        return []
    except Exception as e:
        print(f"❌ Неизвестная ошибка: {e}")
        import traceback
        traceback.print_exc()
        return []
def get_lesson_time(lesson_num, day_of_week):
    """Возвращает время начала и конца пары"""
    mon_wed_fri = {1: "8.00 – 9.40", 2: "9.50 – 11.45", 3: "12.20 – 14.00",
                   4: "14.10 – 15.50", 5: "16.00 – 17.40", 6: "17.50 – 19.30"}
    tuesday = {1: "8.00 – 9.40", 2: "9.50 – 11.45", 3: "12.20 – 14.00",
               4: "15.05 – 16.45", 5: "16.55 – 18.35", 6: "18.45 – 20.25"}
    thursday = {1: "8.00 – 9.40", 2: "9.50 – 11.45", 3: "12.20 – 14.00",
                4: "14.45 – 16.25", 5: "16.35 – 18.15", 6: "18.25 – 20.05"}
    saturday = {1: "8.00 – 9.40", 2: "9.50 – 11.30", 3: "11.50 – 13.25",
                4: "13.35 – 15.15", 5: "15.25 – 17.05"}
    
    if day_of_week in [0, 2, 4]:
        return mon_wed_fri.get(lesson_num)
    elif day_of_week == 1:
        return tuesday.get(lesson_num)
    elif day_of_week == 3:
        return thursday.get(lesson_num)
    elif day_of_week == 5:
        return saturday.get(lesson_num)
    return None

def format_schedule_with_day(schedule, group_name, target_day, period_name):
    """Форматирует расписание"""
    if not schedule:
        return f"😕 Нет расписания для группы {group_name}"
    
    days_ru = {0: "ПОНЕДЕЛЬНИК", 1: "ВТОРНИК", 2: "СРЕДА", 3: "ЧЕТВЕРГ",
               4: "ПЯТНИЦА", 5: "СУББОТА", 6: "ВОСКРЕСЕНЬЕ"}
    
    text = f"📚 <b>РАСПИСАНИЕ {period_name}</b>\n👥 <b>Группа {group_name}</b>\n"
    if period_name in ["СЕГОДНЯ", "ЗАВТРА"]:
        text += f"📅 <b>{days_ru[target_day]}</b>\n"
    text += "══════════════════════\n"
    
    dates = {}
    for item in schedule:
        if item['date'] not in dates:
            dates[item['date']] = []
        dates[item['date']].append(item)
    
    total_count = 0
    for date in sorted(dates.keys()):
        text += f"\n📅 <b>{date}</b>\n──────────────────\n"
        sorted_items = sorted(dates[date], key=lambda x: int(x['lesson_num']) if x['lesson_num'].isdigit() else 0)
        
        for item in sorted_items:
            total_count += 1
            text += f"<b>{item['lesson_num']} пара:</b>\n📖 <b>{item['subject']}</b>\n👨‍🏫 {item['teacher']}\n🚪 Кабинет: {item['room']}\n"
            if item['lesson_num'].isdigit():
                lesson_time = get_lesson_time(int(item['lesson_num']), target_day)
                if lesson_time:
                    text += f"⏱️ {lesson_time}\n"
            text += "\n"
    
    text += f"══════════════════════\n📊 <b>Всего пар:</b> {total_count}"
    return text

# ---------- Команды бота ----------
def show_subscription_menu(message):
    """Показывает меню подписки"""
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    btn1 = telebot.types.InlineKeyboardButton("✅ Подписаться", callback_data='subscribe')
    btn2 = telebot.types.InlineKeyboardButton("❌ Отписаться", callback_data='unsubscribe')
    btn3 = telebot.types.InlineKeyboardButton("📊 Статус", callback_data='status')
    markup.add(btn1, btn2, btn3)
    
    with subscribers_lock:
        status = "✅ Подписан" if message.chat.id in subscribed_users else "❌ Не подписан"
    
    bot.send_message(
        message.chat.id,
        f"📢 <b>Управление подпиской</b>\n\nТекущий статус: {status}\n\n🔔 При изменении расписания ты будешь получать уведомление.",
        parse_mode='HTML',
        reply_markup=markup
    )

@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('📅 Сегодня', '📆 Завтра', '📚 Неделя')
    markup.add('🔔 Звонки', 'ℹ️ Помощь', '📢 Подписка')
    
    welcome_text = (
        "👋 <b>Привет! Я бот расписания БТК</b>\n\n"
        "📌 <b>Что я умею:</b>\n• Показывать расписание занятий\n• Показывать расписание звонков\n• Сохранять твою группу\n• Уведомлять об изменениях в расписании (кнопка 📢 Подписка)\n\n"
        "📝 <b>Как пользоваться:</b>\n1. Отправь номер группы (например, 301)\n2. Нажимай кнопки для просмотра\n\n"
        "🎯 <b>Кнопки:</b>\n📅 Сегодня - расписание на сегодня\n📆 Завтра - расписание на завтра\n📚 Неделя - всё расписание\n🔔 Звонки - расписание звонков\n📢 Подписка - уведомления об изменениях"
    )
    
    bot.send_message(message.chat.id, welcome_text, parse_mode='HTML', reply_markup=markup)

@bot.message_handler(commands=['subscribe'])
def subscribe(message):
    user_id = message.chat.id
    with subscribers_lock:
        if user_id in subscribed_users:
            bot.send_message(user_id, "ℹ️ Ты уже подписан на уведомления!", parse_mode='HTML')
            return
    save_subscriber(user_id)
    bot.send_message(user_id, "✅ <b>Ты подписан на уведомления!</b>\n\nЯ буду присылать сообщение, когда расписание обновится.\n", parse_mode='HTML')

@bot.message_handler(commands=['unsubscribe'])
def unsubscribe(message):
    user_id = message.chat.id
    with subscribers_lock:
        if user_id not in subscribed_users:
            bot.send_message(user_id, "ℹ️ Ты не подписан на уведомления.", parse_mode='HTML')
            return
    remove_subscriber(user_id)
    bot.send_message(user_id, "❌ <b>Ты отписан от уведомлений.</b>\n\nЕсли захочешь снова подписаться, нажми /subscribe", parse_mode='HTML')

@bot.message_handler(commands=['stats'])
def stats(message):
    if message.chat.id != YOUR_USER_ID:
        bot.send_message(message.chat.id, "❌ Эта команда только для администратора")
        return
    with subscribers_lock:
        count = len(subscribed_users)
    bot.send_message(message.chat.id, f"📊 <b>Статистика</b>\n\n👥 Подписчиков: {count}\n🔔 Уведомления: {'ВКЛЮЧЕНЫ' if NOTIFICATIONS_ENABLED else 'ВЫКЛЮЧЕНЫ'}", parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.message.chat.id
    
    if call.data == 'subscribe':
        with subscribers_lock:
            if user_id in subscribed_users:
                bot.answer_callback_query(call.id, "✅ Ты уже подписан!")
                return
        save_subscriber(user_id)
        bot.answer_callback_query(call.id, "✅ Ты подписан!")
        
    elif call.data == 'unsubscribe':
        with subscribers_lock:
            if user_id not in subscribed_users:
                bot.answer_callback_query(call.id, "❌ Ты не подписан")
                return
        remove_subscriber(user_id)
        bot.answer_callback_query(call.id, "❌ Ты отписался")
        
    elif call.data == 'status':
        with subscribers_lock:
            status = "✅ Подписан" if user_id in subscribed_users else "❌ Не подписан"
        bot.answer_callback_query(call.id, status)
    
    with subscribers_lock:
        status = "✅ Подписан" if user_id in subscribed_users else "❌ Не подписан"
    
    try:
        bot.edit_message_text(
            f"📢 <b>Управление подпиской</b>\n\nТекущий статус: {status}\n\n🔔 При изменении расписания ты будешь получать уведомление.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=call.message.reply_markup
        )
    except:
        pass

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text
    user_id = message.chat.id
    
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
    elif text == '📢 Подписка':
        show_subscription_menu(message)
    else:
        if save_user_group(user_id, text):
            bot.send_message(user_id, f"✅ <b>Группа {text} сохранена!</b>\n\nТеперь нажимай кнопки для просмотра расписания", parse_mode='HTML')
        else:
            bot.send_message(user_id, "❌ Ошибка при сохранении группы")

def show_bell_schedule(message):
    today = datetime.now().weekday()
    bell_text = get_bell_schedule(today)
    tomorrow = (today + 1) % 7
    tomorrow_name = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"][tomorrow]
    full_text = f"{bell_text}\n\n📌 <b>Завтра ({tomorrow_name}):</b>\nИспользуй кнопку 📆 Завтра для расписания занятий"
    bot.send_message(message.chat.id, full_text, parse_mode='HTML')

def show_help(message):
    help_text = (
        "ℹ️ <b>ПОМОЩЬ ПО БОТУ</b>\n\n"
        "📌 <b>Основные команды:</b>\n• <b>Отправь номер группы</b> - сохранить группу\n• <b>📅 Сегодня</b> - расписание на сегодня\n• <b>📆 Завтра</b> - расписание на завтра\n• <b>📚 Неделя</b> - всё расписание\n• <b>🔔 Звонки</b> - расписание звонков\n• <b>📢 Подписка</b> - уведомления об изменениях\n• <b>/subscribe</b> - подписаться\n• <b>/unsubscribe</b> - отписаться\n\n"
        "❓ <b>Если бот не отвечает:</b>\n• Проверь, сохранена ли группа\n• Попробуй нажать /start\n• Напиши позже, если сайт колледжа недоступен\n\n🛠️ <b>Разработчик:</b> Михась"
    )
    bot.send_message(message.chat.id, help_text, parse_mode='HTML')

def show_schedule(message, period):
    user_id = message.chat.id
    group = get_user_group(user_id)
    
    if not group:
        bot.send_message(user_id, "❌ Сначала отправь номер группы")
        return
    
    msg = bot.send_message(user_id, f"🔍 <b>Ищу расписание для группы {group}...</b>", parse_mode='HTML')
    schedule = get_schedule_from_site(group)
    
    if not schedule:
        bot.edit_message_text("😕 <b>Не удалось найти расписание.</b>\n\nПроверь номер группы или попробуй позже.", user_id, msg.message_id, parse_mode='HTML')
        return
    
    all_dates = sorted(set([item['date'] for item in schedule]))
    now = datetime.now()
    
    months_ru = {1: 'янв', 2: 'фев', 3: 'март', 4: 'апр', 5: 'мая', 6: 'июн', 7: 'июл', 8: 'авг', 9: 'сен', 10: 'окт', 11: 'ноя', 12: 'дек'}
    
    today_str = f"{now.day:02d}-{months_ru[now.month]}"
    tomorrow_str = f"{(now + timedelta(days=1)).day:02d}-{months_ru[(now + timedelta(days=1)).month]}"
    
    today_weekday = now.weekday()
    
    if period == 'today':
        target_day, period_name, target_date = today_weekday, "СЕГОДНЯ", today_str
        filtered_schedule = [item for item in schedule if item['date'].lower() == target_date.lower()]
        
        if not filtered_schedule:
            bot.edit_message_text(f"😕 <b>Нет расписания на сегодня</b>\n\nДля группы {group} не найдено занятий на {target_date}.\n\n📅 <b>Доступные даты:</b>\n" + "\n".join(all_dates[:10]) + "\n\nПопробуй посмотреть всё расписание (📚 Неделя)", user_id, msg.message_id, parse_mode='HTML')
            return
        
        text = format_schedule_with_day(filtered_schedule, group, target_day, period_name)
    
    elif period == 'tomorrow':
        target_day, period_name, target_date = (today_weekday + 1) % 7, "ЗАВТРА", tomorrow_str
        filtered_schedule = [item for item in schedule if item['date'].lower() == target_date.lower()]
        
        if not filtered_schedule:
            bot.edit_message_text(f"😕 <b>Нет расписания на завтра</b>\n\nДля группы {group} не найдено занятий на {target_date}.\n\nПопробуй посмотреть всё расписание (📚 Неделя)", user_id, msg.message_id, parse_mode='HTML')
            return
        
        text = format_schedule_with_day(filtered_schedule, group, target_day, period_name)
    
    else:
        text = format_schedule_with_day(schedule, group, today_weekday, "НА БЛИЖАЙШИЕ ДНИ")
    
    try:
        bot.edit_message_text(text, user_id, msg.message_id, parse_mode='HTML')
    except Exception as e:
        print(f"Ошибка при редактировании: {e}")
        if len(text) > 4096:
            for i in range(0, len(text), 4096):
                bot.send_message(user_id, text[i:i+4096], parse_mode='HTML')
        else:
            bot.send_message(user_id, text, parse_mode='HTML')

# ---------- Запуск ----------
if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 ЗАПУСК БОТА РАСПИСАНИЯ БТК")
    print("="*50)
    
    keep_alive()
    scheduler = start_scheduler()
    
    print("✅ Бот готов к работе!")
    print("📱 Найди своего бота в Telegram и отправь /start")
    print("="*50 + "\n")
    
    try:
        bot.polling(non_stop=True, interval=0)
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
    finally:
        if 'scheduler' in locals():
            scheduler.shutdown()
