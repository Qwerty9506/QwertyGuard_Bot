# database.py
import sqlite3

DB_NAME = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица пользователей для удаления прошлых сообщений
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        last_menu_id INTEGER
    )''')
    
    # Таблица групп
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups (
        group_id INTEGER PRIMARY KEY,
        group_name TEXT,
        creator_id INTEGER
    )''')
    
    # Таблица модераторов и их прав
    cursor.execute('''CREATE TABLE IF NOT EXISTS moderators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER,
        user_id INTEGER,
        username TEXT,
        can_mute INTEGER DEFAULT 1,
        can_ban INTEGER DEFAULT 1,
        can_kick INTEGER DEFAULT 1,
        UNIQUE(group_id, user_id)
    )''')
    
    # Кеш юзернеймов для обработки команд вида "Мут @username"
    cursor.execute('''CREATE TABLE IF NOT EXISTS username_cache (
        username TEXT PRIMARY KEY,
        user_id INTEGER
    )''')
    
    conn.commit()
    conn.close()

def set_last_menu(user_id, message_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO users (user_id, last_menu_id) VALUES (?, ?)', (user_id, message_id))
    conn.commit()
    conn.close()

def get_last_menu(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT last_menu_id FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def add_group(group_id, group_name, creator_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO groups (group_id, group_name, creator_id) VALUES (?, ?, ?)', 
                   (group_id, group_name, creator_id))
    conn.commit()
    conn.close()

def get_user_groups(creator_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT group_id, group_name, creator_id FROM groups WHERE creator_id = ?', (creator_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def cache_username(username, user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO username_cache (username, user_id) VALUES (?, ?)', (username.lower(), user_id))
    conn.commit()
    conn.close()

def get_id_by_username(username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM username_cache WHERE username = ?', (username.lower(),))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_moderators(group_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id, group_id, user_id, username, can_mute, can_ban, can_kick FROM moderators WHERE group_id = ?', (group_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_moderator(group_id, user_id, username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO moderators (group_id, user_id, username) VALUES (?, ?, ?)', (group_id, user_id, username))
    conn.commit()
    conn.close()

def toggle_moderator_right(group_id, user_id, right_type):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if right_type == "mute":
        cursor.execute('UPDATE moderators SET can_mute = NOT can_mute WHERE group_id = ? AND user_id = ?', (group_id, user_id))
    elif right_type == "ban":
        cursor.execute('UPDATE moderators SET can_ban = NOT can_ban WHERE group_id = ? AND user_id = ?', (group_id, user_id))
    elif right_type == "kick":
        cursor.execute('UPDATE moderators SET can_kick = NOT can_kick WHERE group_id = ? AND user_id = ?', (group_id, user_id))
    conn.commit()
    conn.close()
