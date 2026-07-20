import aiosqlite

async def init_db():
    async with aiosqlite.connect("bot_base.db") as db:
        # Теперь таблица запоминает, кто добавил бота (owner_id)
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
        await db.commit()

async def add_group(group_id: int, title: str, owner_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute("INSERT OR REPLACE INTO groups (group_id, title, owner_id) VALUES (?, ?, ?)", 
                         (group_id, title, owner_id))
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
        # Инвертируем значение: если 0 станет 1, если 1 станет 0
        await db.execute("UPDATE groups SET spam_protect = NOT spam_protect WHERE group_id = ?", (group_id,))
        await db.commit()
