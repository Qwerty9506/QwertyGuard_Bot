import asyncio
import re
import time
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import database as db

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
spam_cache = {}

# Вспомогательная функция для слов (1 друга, 5 друзей)
def plural_friends(n: int) -> str:
    if 1 <= n % 10 <= 4 and not (11 <= n % 100 <= 14): return "друга"
    return "друзей"

# Вспомогательная проверка админа
async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except: return False

# Парсер времени
def parse_time(text: str):
    text = text.lower()
    if "навсегда" in text: return 0
    match = re.search(r'(\d+)\s*(час|ч|мин|м|день|дн|сек|с)?', text)
    if not match: return 0
    val = int(match.group(1))
    unit = match.group(2) or "м"
    if "ч" in unit: return val * 3600
    if "д" in unit: return val * 86400
    if "с" in unit: return val
    return val * 60

# --- 1. ЛОГИКА ВХОДА (Тихая) ---
@router.message(F.new_chat_members)
async def on_user_join(message: Message, bot: Bot):
    for new_member in message.new_chat_members:
        if new_member.id == bot.id:
            await db.add_group(message.chat.id, message.chat.title, message.from_user.id)
            await message.answer("Всем привет)")
            return
    
    # Бот игнорит входы визуально, но если кто-то добавил человека — считаем в базу!
    adder_id = message.from_user.id
    for member in message.new_chat_members:
        if member.id != adder_id:
            await db.add_user_invites(adder_id, message.chat.id, 1)

# --- 2. ЛОГИКА СООБЩЕНИЙ (Антиспам, Модерация, Проверка Инвайтов) ---
@router.message(F.text)
async def handle_group_msgs(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text
    
    settings = await db.get_group_settings(chat_id)
    if not settings: return
    req_invites, spam_protect = settings

    user_is_admin = await is_admin(bot, chat_id, user_id)

    # --- МОДЕРАЦИЯ (Работает только для админов) ---
    if user_is_admin and message.reply_to_message:
        cmd_match = re.match(r"(?i)^(бан|мут|кик|разбан|размут)", text)
        if cmd_match:
            cmd = cmd_match.group(1).lower()
            target = message.reply_to_message.from_user
            target_link = f"[{target.first_name}](tg://user?id={target.id})"
            mod_link = f"[{message.from_user.first_name}](tg://user?id={user_id})"
            
            time_sec = parse_time(text)
            until = int(time.time()) + time_sec if time_sec > 0 else 0
            
            if cmd == "бан":
                await bot.ban_chat_member(chat_id, target.id, until_date=until)
                await message.answer(f"Участник {target_link} был забанен\nМодератор: {mod_link}\nПричина: -", parse_mode="Markdown")
                if time_sec > 0:
                    asyncio.create_task(notify_expiration(bot, chat_id, target, time_sec, "бана", "учите правила"))
            elif cmd == "мут":
                await bot.restrict_chat_member(chat_id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
                await message.answer(f"Участник {target_link} был замучен\nМодератор: {mod_link}\nПричина: -", parse_mode="Markdown")
                if time_sec > 0:
                    asyncio.create_task(notify_expiration(bot, chat_id, target, time_sec, "мута", "следите за языком"))
            elif cmd == "кик":
                await bot.ban_chat_member(chat_id, target.id)
                await bot.unban_chat_member(chat_id, target.id)
                await message.answer(f"Участник {target_link} был кикнут\nМодератор: {mod_link}", parse_mode="Markdown")
            elif cmd == "разбан" or cmd == "размут":
                await bot.restrict_chat_member(chat_id, target.id, permissions=ChatPermissions(can_send_messages=True, can_send_other_messages=True))
                action_text = "разбанен" if cmd == "разбан" else "размучен"
                await message.answer(f"Участник {target_link} был {action_text}\nМодератор: {mod_link}", parse_mode="Markdown")
            return

    # Если админ пишет обычное сообщение — пропускаем проверки
    if user_is_admin: return

    # --- ПРОВЕРКА ИНВАЙТОВ (Удаление сообщения, если не добавил друзей) ---
    if req_invites > 0:
        invites_data = await db.get_user_invites(user_id, chat_id)
        current_invites, is_allowed = invites_data
        
        if not is_allowed and current_invites < req_invites:
            await message.delete()
            word = plural_friends(req_invites)
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Я добавил", callback_data=f"check_{user_id}")],
                [InlineKeyboardButton(text="🔓 Отпустить", callback_data=f"release_{user_id}")]
            ])
            
            msg = await message.answer(
                f"[{message.from_user.first_name}](tg://user?id={user_id}), вам нельзя писать в группе!\n\n"
                f"Для получения доступа нужно добавить {req_invites} {word}.",
                reply_markup=kb, parse_mode="Markdown"
            )
            # Удаляем предупреждение через время (чтобы не засорять чат)
            await asyncio.sleep(20)
            try: await msg.delete()
            except: pass
            return

    # --- АНТИСПАМ ---
    if spam_protect:
        if chat_id not in spam_cache: spam_cache[chat_id] = {}
        user_cache = spam_cache[chat_id].get(user_id)
        
        if user_cache and user_cache["text"] == text.lower():
            user_cache["count"] += 1
            if user_cache["count"] == 2:
                await message.delete()
                return
            elif user_cache["count"] >= 3:
                await message.delete()
                await bot.ban_chat_member(chat_id, user_id)
                await bot.unban_chat_member(chat_id, user_id)
                spam_cache[chat_id].pop(user_id, None)
                await message.answer(f"Спамер [{message.from_user.first_name}](tg://user?id={user_id}) был кикнут\nПричина: Спам", parse_mode="Markdown")
                return
        else:
            spam_cache[chat_id][user_id] = {"text": text.lower(), "count": 1}

# --- ОБРАБОТЧИКИ КНОПОК ---

@router.callback_query(F.data.startswith("check_"))
async def check_invites(call: CallbackQuery):
    target_id = int(call.data.split("_")[1])
    if call.from_user.id != target_id:
        return await call.answer("Это не ваша кнопка!", show_alert=True)
        
    settings = await db.get_group_settings(call.message.chat.id)
    req = settings[0] if settings else 0
    invites_data = await db.get_user_invites(target_id, call.message.chat.id)
    current = invites_data[0]
    
    if current >= req:
        await db.allow_user(target_id, call.message.chat.id)
        await call.message.delete()
        await call.answer("Доступ разрешен! Можете писать.", show_alert=True)
    else:
        await call.answer(f"Вы добавили только {current} из {req}!", show_alert=True)

@router.callback_query(F.data.startswith("release_"))
async def release_user(call: CallbackQuery, bot: Bot):
    # ПРОВЕРКА: Только модераторы/владельцы могут отпускать
    if not await is_admin(bot, call.message.chat.id, call.from_user.id):
        return await call.answer("Эта кнопка доступна только Владельцу и Модераторам!", show_alert=True)
        
    target_id = int(call.data.split("_")[1])
    await db.allow_user(target_id, call.message.chat.id)
    await call.message.delete()
    await call.answer("Пользователь отпущен! Теперь он может писать.", show_alert=True)

# Фоновая задача для уведомления об окончании бана/мута
async def notify_expiration(bot: Bot, chat_id: int, user, delay: int, action: str, tip: str):
    await asyncio.sleep(delay)
    try:
        await bot.send_message(
            chat_id, 
            f"[{user.first_name}](tg://user?id={user.id}) Время {action} окончено, {tip}.", 
            parse_mode="Markdown"
        )
    except: pass
