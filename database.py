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
        await db.commit()

async def add_group(group_id: int, title: str, owner_id: int):
    async with aiosqlite.connect("bot_base.db") as db:
        await db.execute("INSERT OR REPLACE INTO groups (group_id, title, owner_id) VALUES (?, ?, ?)", (group_id, title, owner_id))
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
        await db.execute("UPDATE groups SET spam_protect = NOT spam_protect WHERE group_id = ?", (group_id,))
        await db.commit()

# --- НОВЫЕ ФУНКЦИИ ДЛЯ ИНВАЙТОВ ---
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
