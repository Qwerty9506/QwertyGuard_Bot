import aiosqlite

async def init_db():
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id INTEGER PRIMARY KEY,
                title TEXT,
                owner_id INTEGER,
                req_invites INTEGER DEFAULT 0,
                spam_protect BOOLEAN DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER,
                group_id INTEGER,
                invites_count INTEGER DEFAULT 0,
                is_allowed BOOLEAN DEFAULT 0,
                PRIMARY KEY (user_id, group_id)
            )
        """)
        # Таблица для отслеживания всех участников чата
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_users (
                group_id INTEGER,
                user_id INTEGER,
                first_name TEXT,
                username TEXT,
                PRIMARY KEY (group_id, user_id)
            )
        """)
        # Таблица для кастомных модераторов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS moderators (
                group_id INTEGER,
                user_id INTEGER,
                can_ban BOOLEAN DEFAULT 1,
                can_mute BOOLEAN DEFAULT 1,
                can_kick BOOLEAN DEFAULT 1,
                PRIMARY KEY (group_id, user_id)
            )
        """)
        await db.commit()

# --- БАЗОВЫЕ ФУНКЦИИ ГРУППЫ ---
async def add_group(group_id: int, title: str, owner_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        # ИСПРАВЛЕНО: ON CONFLICT вместо REPLACE, чтобы настройки не сбрасывались
        await db.execute("""
            INSERT INTO groups (group_id, title, owner_id) 
            VALUES (?, ?, ?) 
            ON CONFLICT(group_id) DO UPDATE SET title = excluded.title
        """, (group_id, title, owner_id))
        await db.commit()

async def get_user_groups(user_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        async with db.execute("SELECT group_id, title FROM groups WHERE owner_id = ?", (user_id,)) as cursor:
            return await cursor.fetchall()

async def get_group_settings(group_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        async with db.execute("SELECT req_invites, spam_protect FROM groups WHERE group_id = ?", (group_id,)) as cursor:
            return await cursor.fetchone()

async def update_req_invites(group_id: int, count: int):
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute("UPDATE groups SET req_invites = ? WHERE group_id = ?", (count, group_id))
        await db.commit()

async def toggle_spam(group_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        # ИСПРАВЛЕНО: Математическое переключение 1 - spam_protect для надежности в SQLite
        await db.execute("UPDATE groups SET spam_protect = 1 - spam_protect WHERE group_id = ?", (group_id,))
        await db.commit()

# --- ФУНКЦИИ ДЛЯ ИНВАЙТОВ ---
async def get_user_invites(user_id: int, group_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        async with db.execute("SELECT invites_count, is_allowed FROM users WHERE user_id = ? AND group_id = ?", (user_id, group_id)) as cur:
            res = await cur.fetchone()
            return res if res else (0, 0)

async def add_user_invites(user_id: int, group_id: int, count: int = 1):
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute("""
            INSERT INTO users (user_id, group_id, invites_count) 
            VALUES (?, ?, ?) 
            ON CONFLICT(user_id, group_id) 
            DO UPDATE SET invites_count = invites_count + ?
        """, (user_id, group_id, count, count))
        await db.commit()

async def allow_user(user_id: int, group_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute("""
            INSERT INTO users (user_id, group_id, is_allowed) 
            VALUES (?, ?, 1) 
            ON CONFLICT(user_id, group_id) 
            DO UPDATE SET is_allowed = 1
        """, (user_id, group_id))
        await db.commit()

# --- ОТСЛЕЖИВАНИЕ УЧАСТНИКОВ И ЮЗЕРНЕЙМОВ ---
async def track_user(group_id: int, user_id: int, first_name: str, username: str):
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute("INSERT OR REPLACE INTO group_users VALUES (?, ?, ?, ?)", (group_id, user_id, first_name, username))
        await db.commit()

async def get_user_by_username(group_id: int, username: str):
    username = username.replace("@", "")
    async with aiosqlite.connect("bot_base.db") as db:
        async with db.execute("SELECT user_id, first_name FROM group_users WHERE group_id = ? AND LOWER(username) = ?", (group_id, username.lower())) as cur:
            return await cur.fetchone()

async def get_available_users(group_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        async with db.execute("""
            SELECT user_id, first_name, username FROM group_users 
            WHERE group_id = ? AND user_id NOT IN (SELECT user_id FROM moderators WHERE group_id = ?)
            ORDER BY user_id DESC LIMIT 30
        """, (group_id, group_id)) as cur:
            return await cur.fetchall()

# --- СИСТЕМА МОДЕРАТОРОВ ---
async def get_moderators(group_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        async with db.execute("""
            SELECT m.user_id, u.first_name, u.username, m.can_ban, m.can_mute, m.can_kick 
            FROM moderators m
            LEFT JOIN group_users u ON m.user_id = u.user_id AND m.group_id = u.group_id
            WHERE m.group_id = ?
        """, (group_id,)) as cur:
            return await cur.fetchall()

async def get_moderator_rights(group_id: int, user_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        async with db.execute("SELECT can_ban, can_mute, can_kick FROM moderators WHERE group_id = ? AND user_id = ?", (group_id, user_id)) as cur:
            return await cur.fetchone()

async def add_moderator(group_id: int, user_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute("INSERT OR IGNORE INTO moderators (group_id, user_id) VALUES (?, ?)", (group_id, user_id))
        await db.commit()

async def remove_moderator(group_id: int, user_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute("DELETE FROM moderators WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        await db.commit()

async def toggle_mod_right(group_id: int, user_id: int, right_type: str):
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute(f"UPDATE moderators SET {right_type} = NOT {right_type} WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        await db.commit()
