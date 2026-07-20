import asyncio
import re
import time
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from aiogram.filters import CommandStart, ChatMemberUpdatedFilter, IS_NOT_MEMBER, MEMBER
from aiogram.enums import ChatMemberStatus
import database as db

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
spam_cache = {}
invite_warnings = {} # Кэш для предотвращения дублей сообщений о приглашении

UNMUTE_PERMS = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True, can_invite_users=True
)

def plural_friends(n: int) -> str:
    if 1 <= n % 10 <= 4 and not (11 <= n % 100 <= 14): return "друга"
    return "друзей"

def format_time_text(seconds: int) -> str:
    if seconds <= 0: return "Навсегда"
    if seconds < 60: return f"{seconds} сек"
    if seconds < 3600: return f"{seconds//60} мин"
    if seconds < 86400: return f"{seconds//3600} ч"
    return f"{seconds//86400} дн"

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

def parse_mod_command(text: str):
    lines = text.split('\n', 1)
    first_line = lines[0].strip()
    reason = lines[1].strip() if len(lines) > 1 else "Не указана"
    
    match = re.match(r"(?i)^(бан|мут|кик|разбан|размут)\b", first_line)
    if not match: return None
    
    cmd = match.group(1).lower()
    rest = first_line[match.end():].strip()
    
    target_username = None
    target_id = None
    time_str = rest
    
    user_match = re.match(r"(?:@([a-zA-Z0-9_]+)|(\d+))\b", rest)
    if user_match:
        target_username = user_match.group(1)
        target_id = int(user_match.group(2)) if user_match.group(2) else None
        time_str = rest[user_match.end():].strip()
        
    time_sec = parse_time(time_str) if time_str else 0
    return cmd, target_username, target_id, time_sec, reason

# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ УДАЛЕНИЯ СООБЩЕНИЙ БОТА ---
async def delete_msg_after(bot: Bot, chat_id: int, msg_id: int, delay: int = 15):
    await asyncio.sleep(delay)
    try: await bot.delete_message(chat_id, msg_id)
    except: pass

async def check_mod_rights(bot: Bot, chat_id: int, user_id: int, action: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in [ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR]:
            return True
    except: pass
    
    rights = await db.get_moderator_rights(chat_id, user_id)
    if rights:
        c_ban, c_mute, c_kick = rights
        if action in ['бан', 'разбан']: return bool(c_ban)
        if action in ['мут', 'размут']: return bool(c_mute)
        if action == 'кик': return bool(c_kick)
        
    return False

async def unban_unmute_task(bot: Bot, chat_id: int, user_id: int, first_name: str, delay: int, action: str):
    await asyncio.sleep(delay)
    try:
        if action == "бана":
            await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
            text_msg = f"[{first_name}](tg://user?id={user_id}) Время бана окончено, доступ открыт."
        elif action == "мута":
            await bot.restrict_chat_member(chat_id, user_id, permissions=UNMUTE_PERMS)
            text_msg = f"[{first_name}](tg://user?id={user_id}) Время мута окончено, вы можете писать."
        
        msg = await bot.send_message(chat_id, text_msg, parse_mode="Markdown")
        asyncio.create_task(delete_msg_after(bot, chat_id, msg.message_id, 15))
    except Exception as e:
        print(f"Ошибка снятия наказания: {e}")

async def captcha_timer(bot: Bot, chat_id: int, user_id: int, msg_id: int):
    await asyncio.sleep(12)
    u_cache = spam_cache.get(chat_id, {}).get(user_id)
    if u_cache and u_cache.get("pending"):
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.delete_message(chat_id, msg_id)
        except: pass
        spam_cache[chat_id].pop(user_id, None)

@router.message(CommandStart())
async def group_start_cmd(message: Message):
    try: await message.delete()
    except Exception: pass

# --- УДАЛЕНИЕ СИСТЕМНЫХ СООБЩЕНИЙ ---
@router.message(F.new_chat_members | F.left_chat_member | F.new_chat_title | F.new_chat_photo | F.delete_chat_photo | F.pinned_message)
async def handle_system_messages(message: Message, bot: Bot):
    try: await message.delete()
    except: pass

    # Оставляем здесь только приветствие при добавлении самого бота
    if message.new_chat_members:
        for new_member in message.new_chat_members:
            if new_member.id == bot.id:
                await db.add_group(message.chat.id, message.chat.title, message.from_user.id)
                msg = await message.answer("Всем привет)")
                asyncio.create_task(delete_msg_after(bot, message.chat.id, msg.message_id, 15))
                return

# --- НАДЕЖНЫЙ ПОДСЧЕТ ИНВАЙТОВ ЧЕРЕЗ CHAT MEMBER UPDATED ---
@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> MEMBER))
async def track_invites(event: ChatMemberUpdated, bot: Bot):
    adder_id = event.from_user.id
    new_user = event.new_chat_member.user
    chat_id = event.chat.id

    # Игнорируем бота
    if new_user.id == bot.id:
        return

    await db.track_user(chat_id, new_user.id, new_user.first_name, new_user.username)
    
    # Если инициатор добавления (adder_id) не совпадает с самим пользователем, значит его добавили вручную
    if new_user.id != adder_id:
        await db.add_user_invites(adder_id, chat_id, 1)


@router.message(F.text | F.caption)
async def handle_group_msgs(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or message.caption or ""
    
    await db.track_user(chat_id, user_id, message.from_user.first_name, message.from_user.username)
    
    settings = await db.get_group_settings(chat_id)
    if not settings: return
    req_invites, spam_protect = settings

    cmd_info = parse_mod_command(text)
    if cmd_info:
        cmd, target_username, target_id_parsed, time_sec, reason = cmd_info
        target_id, target_name = None, None
        
        if message.reply_to_message:
            target_id = message.reply_to_message.from_user.id
            target_name = message.reply_to_message.from_user.first_name
        elif target_id_parsed:
            target_id = target_id_parsed
            target_name = f"ID {target_id}"
        elif target_username:
            user_data = await db.get_user_by_username(chat_id, target_username)
            if user_data:
                target_id, target_name = user_data
            else:
                try: await message.delete()
                except: pass
                msg = await message.answer(f"Пользователь @{target_username} не найден. Он должен написать хотя бы одно сообщение.")
                asyncio.create_task(delete_msg_after(bot, chat_id, msg.message_id, 15))
                return
                
        if target_id:
            has_rights = await check_mod_rights(bot, chat_id, user_id, cmd)
            if not has_rights: return
            
            try: await message.delete() 
            except: pass
                
            until = int(time.time()) + time_sec if time_sec > 0 else 0
            mod_link = f"[{message.from_user.first_name}](tg://user?id={user_id})"
            target_link = f"[{target_name}](tg://user?id={target_id})"
            time_text = format_time_text(time_sec)
            
            msg = None
           # ... (остальной код до модераторских команд) ...

            if cmd == "бан":
                # Добавлен параметр revoke_messages=True для удаления сообщений пользователя
                await bot.ban_chat_member(chat_id, target_id, until_date=until, revoke_messages=True)
                msg = await message.answer(f"🔨 Участник {target_link} забанен\nМодератор: {mod_link}\nВремя: {time_text}\nПричина: {reason}", parse_mode="Markdown")
                if time_sec > 0: asyncio.create_task(unban_unmute_task(bot, chat_id, target_id, target_name, time_sec, "бана"))
                
            elif cmd == "мут":
                await bot.restrict_chat_member(chat_id, target_id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
                msg = await message.answer(f"🤐 Участник {target_link} замучен\nМодератор: {mod_link}\nВремя: {time_text}\nПричина: {reason}", parse_mode="Markdown")
                if time_sec > 0: asyncio.create_task(unban_unmute_task(bot, chat_id, target_id, target_name, time_sec, "мута"))
                
            elif cmd == "кик":
                await bot.ban_chat_member(chat_id, target_id)
                await asyncio.sleep(1)
                await bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
                
                # Если кик был через reply, удаляем сообщение, на которое ответили
                if message.reply_to_message:
                    try:
                        await message.reply_to_message.delete()
                    except Exception:
                        pass
                        
                msg = await message.answer(f"👢 Участник {target_link} кикнут\nМодератор: {mod_link}\nПричина: {reason}", parse_mode="Markdown")
                
            elif cmd in ["разбан", "размут"]:
                await bot.restrict_chat_member(chat_id, target_id, permissions=UNMUTE_PERMS)
                action_text = "разбанен" if cmd == "разбан" else "размучен"
                msg = await message.answer(f"✅ Участник {target_link} был {action_text}\nМодератор: {mod_link}", parse_mode="Markdown")
            
            if msg: asyncio.create_task(delete_msg_after(bot, chat_id, msg.message_id, 15))
            return

# ... (продолжение функции) ...
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in [ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR]: return
    except: pass

    # --- ЗАЩИТА: ПРОВЕРКА ИНВАЙТОВ И СИСТЕМА ПРЕДУПРЕЖДЕНИЙ ---
    if req_invites > 0:
        current_invites, is_allowed = await db.get_user_invites(user_id, chat_id)
        if not is_allowed and current_invites < req_invites:
            try: await message.delete()
            except: pass
            
            # Выдаем мут на 60 секунд сразу после первого сообщения
            until_date = int(time.time()) + 60
            try:
                await bot.restrict_chat_member(
                    chat_id, user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date
                )
            except: pass

            # Инициализация кэша предупреждений
            if chat_id not in invite_warnings:
                invite_warnings[chat_id] = {}
            
            # Если уже висит предупреждение, удаляем его (защита от багов и дублей)
            old_msg_id = invite_warnings[chat_id].get(user_id)
            if old_msg_id:
                try: await bot.delete_message(chat_id, old_msg_id)
                except: pass

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Я добавил", callback_data=f"check_{user_id}")],
                [InlineKeyboardButton(text="🔓 Отпустить", callback_data=f"release_{user_id}")]
            ])
            
            msg = await message.answer(
                f"[{message.from_user.first_name}](tg://user?id={user_id}), вам нельзя писать в группе!\n\n"
                f"Для получения доступа нужно добавить {req_invites} {plural_friends(req_invites)}.\n"
                f"🤐 _Вы временно заглушены на 1 минуту, чтобы не спамить._",
                reply_markup=kb, parse_mode="Markdown"
            )
            
            invite_warnings[chat_id][user_id] = msg.message_id

            # Персональный таск для удаления сообщения ровно через 60 секунд
            async def del_invite_warning(b, c, m, u):
                await asyncio.sleep(60)
                try: await b.delete_message(c, m)
                except: pass
                # Очищаем кэш, если сообщение еще актуально
                if invite_warnings.get(c, {}).get(u) == m:
                    invite_warnings[c].pop(u, None)

            asyncio.create_task(del_invite_warning(bot, chat_id, msg.message_id, user_id))
            return

    # --- УЛУЧШЕННЫЙ АНТИСПАМ ---
    if spam_protect:
        if chat_id not in spam_cache: spam_cache[chat_id] = {}
        now = time.time()
        
        if user_id not in spam_cache[chat_id]:
            spam_cache[chat_id][user_id] = {"text": "", "dupes": 0, "history": [], "all_msgs": [], "verified": False, "pending": False, "banned": False}
            
        u_cache = spam_cache[chat_id][user_id]

        if u_cache.get("banned") or u_cache.get("pending"):
            try: await message.delete()
            except: pass
            return

        u_cache["all_msgs"].append((message.message_id, now))
        u_cache["all_msgs"] = [(mid, t) for mid, t in u_cache["all_msgs"] if now - t <= 300]

        u_cache["history"] = [t for t in u_cache["history"] if now - t <= 6]
        u_cache["history"].append(now)

        if text.lower() == u_cache["text"] and text.strip() != "":
            u_cache["dupes"] += 1
        else:
            u_cache["text"] = text.lower()
            u_cache["dupes"] = 1

        if u_cache["dupes"] >= 3 or len(u_cache["history"]) >= 10:
            try: await message.delete()
            except: pass
            
            for mid, _ in u_cache["all_msgs"]:
                try: await bot.delete_message(chat_id, mid)
                except: pass
            u_cache["all_msgs"] = [] 
            
            if u_cache["verified"]:
                if not u_cache.get("banned"):
                    u_cache["banned"] = True
                    await bot.ban_chat_member(chat_id, user_id)
                    spam_cache[chat_id].pop(user_id, None)
                    msg = await message.answer(f"⛔️ Пользователь [{message.from_user.first_name}](tg://user?id={user_id}) заблокирован за продолжение спама.", parse_mode="Markdown")
                    asyncio.create_task(delete_msg_after(bot, chat_id, msg.message_id, 15))
            else:
                if not u_cache["pending"]:
                    u_cache["pending"] = True
                    await bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
                    
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🤖 Я не бот", callback_data=f"captcha_{user_id}")]
                    ])
                    msg = await message.answer(
                        f"⚠️ [{message.from_user.first_name}](tg://user?id={user_id}), сработала защита от спама.\n\n"
                        f"Подтвердите, что вы живой человек. У вас есть 12 секунд до **БАНА**.",
                        reply_markup=kb, parse_mode="Markdown"
                    )
                    asyncio.create_task(captcha_timer(bot, chat_id, user_id, msg.message_id))
            return

@router.callback_query(F.data.startswith("captcha_"))
async def captcha_verify(call: CallbackQuery, bot: Bot):
    target_id = int(call.data.split("_")[1])
    if call.from_user.id != target_id:
        return await call.answer("Эта кнопка не для вас!", show_alert=True)
    
    chat_id = call.message.chat.id
    u_cache = spam_cache.get(chat_id, {}).get(target_id)
    
    if u_cache and u_cache.get("pending"):
        u_cache["verified"] = True
        u_cache["pending"] = False
        u_cache["dupes"] = 0
        u_cache["history"] = []
        
        await bot.restrict_chat_member(chat_id, target_id, permissions=UNMUTE_PERMS)
        try: await call.message.delete()
        except: pass
        await call.answer("Проверка пройдена. Можете писать!", show_alert=True)

@router.callback_query(F.data.startswith("check_"))
async def check_invites(call: CallbackQuery, bot: Bot):
    target_id = int(call.data.split("_")[1])
    if call.from_user.id != target_id:
        return await call.answer("Это не ваша кнопка!", show_alert=True)
        
    settings = await db.get_group_settings(call.message.chat.id)
    req = settings[0] if settings else 0
    current, is_allowed = await db.get_user_invites(target_id, call.message.chat.id)
    
    if current >= req:
        await db.allow_user(target_id, call.message.chat.id)
        # Снимаем мут после успешной проверки
        try: await bot.restrict_chat_member(call.message.chat.id, target_id, permissions=UNMUTE_PERMS)
        except: pass
        try: await call.message.delete()
        except: pass
        await call.answer("Доступ разрешен! Можете писать.", show_alert=True)
    else:
        await call.answer(f"Вы добавили только {current} из {req}!", show_alert=True)

@router.callback_query(F.data.startswith("release_"))
async def release_user(call: CallbackQuery, bot: Bot):
    try:
        member = await bot.get_chat_member(call.message.chat.id, call.from_user.id)
        if member.status not in [ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR]:
            return await call.answer("Эта кнопка доступна только Владельцу и Админам!", show_alert=True)
    except: return
        
    target_id = int(call.data.split("_")[1])
    await db.allow_user(target_id, call.message.chat.id)
    # Снимаем мут после "Отпустить"
    try: await bot.restrict_chat_member(call.message.chat.id, target_id, permissions=UNMUTE_PERMS)
    except: pass
    try: await call.message.delete()
    except: pass
    await call.answer("Пользователь отпущен! Теперь он может писать.", show_alert=True)
