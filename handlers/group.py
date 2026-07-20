import asyncio
import re
import time
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import database as db

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
spam_cache = {}

# Права при размуте (всё разрешено)
UNMUTE_PERMS = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True, can_invite_users=True
)

def plural_friends(n: int) -> str:
    if 1 <= n % 10 <= 4 and not (11 <= n % 100 <= 14): return "друга"
    return "друзей"

# Форматирование времени для красивого вывода
def format_time_text(seconds: int) -> str:
    if seconds <= 0: return "Навсегда"
    if seconds < 60: return f"{seconds} сек"
    if seconds < 3600: return f"{seconds//60} мин"
    if seconds < 86400: return f"{seconds//3600} ч"
    return f"{seconds//86400} дн"

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

# Парсер команды (разбор Бан @username 2 часа \n Причина)
def parse_mod_command(text: str):
    lines = text.split('\n', 1)
    first_line = lines[0].strip()
    reason = lines[1].strip() if len(lines) > 1 else "Не указана"
    
    match = re.search(r"(?i)^(бан|мут|кик|разбан|размут)\s*(?:@([a-zA-Z0-9_]+))?\s*(.*)$", first_line)
    if not match: return None
    
    cmd = match.group(1).lower()
    username = match.group(2)
    time_str = match.group(3).strip()
    
    time_sec = parse_time(time_str) if time_str else 0
    return cmd, username, time_sec, reason

# Проверка прав: Админ Telegram ИЛИ наш кастомный Модератор из БД
async def check_mod_rights(bot: Bot, chat_id: int, user_id: int, action: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ['creator', 'administrator']:
            return True
    except: pass
    
    rights = await db.get_moderator_rights(chat_id, user_id)
    if rights:
        c_ban, c_mute, c_kick = rights
        if action in ['бан', 'разбан']: return bool(c_ban)
        if action in ['мут', 'размут']: return bool(c_mute)
        if action == 'кик': return bool(c_kick)
        
    return False

# Снятие наказания через заданное время (ТЕПЕРЬ РЕАЛЬНО РАЗБАНИВАЕТ/РАЗМУЧИВАЕТ БЕЗ БАГОВ)
async def unban_unmute_task(bot: Bot, chat_id: int, user_id: int, first_name: str, delay: int, action: str):
    await asyncio.sleep(delay)
    try:
        if action == "бана":
            await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
            text_msg = f"[{first_name}](tg://user?id={user_id}) Время бана окончено, доступ открыт."
        elif action == "мута":
            await bot.restrict_chat_member(chat_id, user_id, permissions=UNMUTE_PERMS)
            text_msg = f"[{first_name}](tg://user?id={user_id}) Время мута окончено, вы можете писать."
        
        await bot.send_message(chat_id, text_msg, parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка снятия наказания: {e}")

# --- 1. ЛОГИКА ВХОДА ---
@router.message(F.new_chat_members)
async def on_user_join(message: Message, bot: Bot):
    for new_member in message.new_chat_members:
        if new_member.id == bot.id:
            await db.add_group(message.chat.id, message.chat.title, message.from_user.id)
            await message.answer("Всем привет)")
            return
            
    adder_id = message.from_user.id
    for member in message.new_chat_members:
        await db.track_user(message.chat.id, member.id, member.first_name, member.username)
        if member.id != adder_id:
            await db.add_user_invites(adder_id, message.chat.id, 1)

# --- 2. ЛОГИКА СООБЩЕНИЙ ---
@router.message(F.text | F.caption)
async def handle_group_msgs(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or message.caption or ""
    
    # Сохраняем пользователя в базу для работы поиска по @username
    await db.track_user(chat_id, user_id, message.from_user.first_name, message.from_user.username)
    
    settings = await db.get_group_settings(chat_id)
    if not settings: return
    req_invites, spam_protect = settings

    # --- МОДЕРАЦИЯ ---
    cmd_info = parse_mod_command(text)
    if cmd_info:
        cmd, target_username, time_sec, reason = cmd_info
        target_id, target_name = None, None
        
        if message.reply_to_message:
            target_id = message.reply_to_message.from_user.id
            target_name = message.reply_to_message.from_user.first_name
        elif target_username:
            user_data = await db.get_user_by_username(chat_id, target_username)
            if user_data:
                target_id, target_name = user_data
            else:
                await message.answer(f"Пользователь @{target_username} не найден. Он должен написать хотя бы одно сообщение в группе, чтобы попасть в базу.")
                return
                
        if target_id:
            has_rights = await check_mod_rights(bot, chat_id, user_id, cmd)
            if not has_rights:
                return # Нет прав — просто игнорим команду или сообщение
                
            until = int(time.time()) + time_sec if time_sec > 0 else 0
            mod_link = f"[{message.from_user.first_name}](tg://user?id={user_id})"
            target_link = f"[{target_name}](tg://user?id={target_id})"
            time_text = format_time_text(time_sec)
            
            if cmd == "бан":
                await bot.ban_chat_member(chat_id, target_id, until_date=until)
                await message.answer(f"🔨 Участник {target_link} забанен\nМодератор: {mod_link}\nВремя: {time_text}\nПричина: {reason}", parse_mode="Markdown")
                if time_sec > 0: asyncio.create_task(unban_unmute_task(bot, chat_id, target_id, target_name, time_sec, "бана"))
            
            elif cmd == "мут":
                await bot.restrict_chat_member(chat_id, target_id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
                await message.answer(f"🤐 Участник {target_link} замучен\nМодератор: {mod_link}\nВремя: {time_text}\nПричина: {reason}", parse_mode="Markdown")
                if time_sec > 0: asyncio.create_task(unban_unmute_task(bot, chat_id, target_id, target_name, time_sec, "мута"))
            
            elif cmd == "кик":
                await bot.ban_chat_member(chat_id, target_id)
                await asyncio.sleep(1)
                await bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
                await message.answer(f"👢 Участник {target_link} кикнут\nМодератор: {mod_link}\nПричина: {reason}", parse_mode="Markdown")
            
            elif cmd == "разбан" or cmd == "размут":
                await bot.restrict_chat_member(chat_id, target_id, permissions=UNMUTE_PERMS)
                action_text = "разбанен" if cmd == "разбан" else "размучен"
                await message.answer(f"✅ Участник {target_link} был {action_text}\nМодератор: {mod_link}", parse_mode="Markdown")
            return # Останавливаем обработку, чтобы сообщение модератора не ушло в спам-фильтр

    # Если пишет админ (Telegram) или владелец — пропускаем проверки
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ['creator', 'administrator']: return
    except: pass

    # --- ПРОВЕРКА ИНВАЙТОВ ---
    if req_invites > 0:
        current_invites, is_allowed = await db.get_user_invites(user_id, chat_id)
        if not is_allowed and current_invites < req_invites:
            await message.delete()
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Я добавил", callback_data=f"check_{user_id}")],
                [InlineKeyboardButton(text="🔓 Отпустить", callback_data=f"release_{user_id}")]
            ])
            msg = await message.answer(
                f"[{message.from_user.first_name}](tg://user?id={user_id}), вам нельзя писать в группе!\n\n"
                f"Для получения доступа нужно добавить {req_invites} {plural_friends(req_invites)}.",
                reply_markup=kb, parse_mode="Markdown"
            )
            await asyncio.sleep(20)
            try: await msg.delete()
            except: pass
            return

    # --- УЛУЧШЕННЫЙ АНТИСПАМ ---
    if spam_protect:
        if chat_id not in spam_cache: spam_cache[chat_id] = {}
        now = time.time()
        user_cache = spam_cache[chat_id].get(user_id)
        
        # Если последнее сообщение было больше 15 секунд назад — сбрасываем счетчик (решает баг универсально)
        if user_cache and (now - user_cache["time"] > 15):
            user_cache = None
            
        if user_cache and user_cache["text"] == text.lower():
            user_cache["count"] += 1
            user_cache["time"] = now # обновляем время
            
            if user_cache["count"] == 2:
                await message.delete()
                return
            elif user_cache["count"] >= 3:
                await message.delete()
                await bot.ban_chat_member(chat_id, user_id)
                await asyncio.sleep(1)
                await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
                spam_cache[chat_id].pop(user_id, None)
                await message.answer(f"👢 Спамер [{message.from_user.first_name}](tg://user?id={user_id}) был кикнут\nПричина: Спам (дублирование)", parse_mode="Markdown")
                return
        else:
            spam_cache[chat_id][user_id] = {"text": text.lower(), "count": 1, "time": now}

# --- ОБРАБОТЧИКИ КНОПОК ИНВАЙТА ---
@router.callback_query(F.data.startswith("check_"))
async def check_invites(call: CallbackQuery):
    target_id = int(call.data.split("_")[1])
    if call.from_user.id != target_id:
        return await call.answer("Это не ваша кнопка!", show_alert=True)
        
    settings = await db.get_group_settings(call.message.chat.id)
    req = settings[0] if settings else 0
    current, is_allowed = await db.get_user_invites(target_id, call.message.chat.id)
    
    if current >= req:
        await db.allow_user(target_id, call.message.chat.id)
        await call.message.delete()
        await call.answer("Доступ разрешен! Можете писать.", show_alert=True)
    else:
        await call.answer(f"Вы добавили только {current} из {req}!", show_alert=True)

@router.callback_query(F.data.startswith("release_"))
async def release_user(call: CallbackQuery, bot: Bot):
    try:
        member = await bot.get_chat_member(call.message.chat.id, call.from_user.id)
        if member.status not in ['creator', 'administrator']:
            return await call.answer("Эта кнопка доступна только Владельцу и Админам!", show_alert=True)
    except: return
        
    target_id = int(call.data.split("_")[1])
    await db.allow_user(target_id, call.message.chat.id)
    await call.message.delete()
    await call.answer("Пользователь отпущен! Теперь он может писать.", show_alert=True)