import aiosqlite

async def init_db():
    async with aiosqlite.connect("bot_base.db") as db:
        # Таблица групп
        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id INTEGER PRIMARY KEY,
                title TEXT,
                req_invites INTEGER DEFAULT 0,
                spam_protect BOOLEAN DEFAULT 0
            )
        """)
        # Таблица пользователей в группах (кто сколько пригласил)
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

async def add_group(group_id: int, title: str):
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute("INSERT OR IGNORE INTO groups (group_id, title) VALUES (?, ?)", (group_id, title))
        await db.commit()

async def get_group_settings(group_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        async with db.execute("SELECT req_invites, spam_protect FROM groups WHERE group_id = ?", (group_id,)) as cursor:
            return await cursor.fetchone()

async def update_req_invites(group_id: int, count: int):
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute("UPDATE groups SET req_invites = ? WHERE group_id = ?", (count, group_id))
        await db.commit()
