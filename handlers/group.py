# handlers/group.py
import re
import time
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions
import database as db

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

# Внутренний кеш для антиспама: {(chat_id, user_id): [последнее_время, счетчик]}
SPAM_CACHE = {}

@router.message()
async def group_message_handler(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Кешируем юзернейм для возможности банить по @username
    if message.from_user.username:
        db.cache_username(message.from_user.username.lower(), user_id)

    # --- 1. АНТИСПАМ (АВТО-КИК) ---
    now = time.time()
    if (chat_id, user_id) in SPAM_CACHE:
        last_time, count = SPAM_CACHE[(chat_id, user_id)]
        if now - last_time < 1.3:  # Если интервал меньше 1.3 сек
            count += 1
            SPAM_CACHE[(chat_id, user_id)] = [now, count]
            if count >= 2:
                # Избавляемся от спамера (Кик = Бан + Разбан)
                try:
                    await bot.ban_chat_member(chat_id, user_id)
                    await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
                    user_link = f'<a href="tg://user?id={user_id}">{message.from_user.full_name}</a>'
                    await message.answer(f"Спамер {user_link} был кикнут (Без причины, так как авто!!!)", parse_mode="HTML")
                except Exception:
                    pass
                del SPAM_CACHE[(chat_id, user_id)]
                return
        else:
            SPAM_CACHE[(chat_id, user_id)] = [now, 1]
    else:
        SPAM_CACHE[(chat_id, user_id)] = [now, 1]

    # --- 2. ОБРАБОТКА КОМАНД МОДЕРАЦИИ ---
    text = message.text or message.caption
    if not text:
        return
        
    text_strip = text.strip()
    lower_text = text_strip.lower()
    
    # Проверка триггеров модерации
    if not any(lower_text.startswith(cmd) for cmd in ["мут", "бан", "кик", "размут", "разбан"]):
        return

    # Проверка прав отправителя (Админ ТГ или модератор из базы бота)
    member = await message.chat.get_member(user_id)
    is_tg_admin = member.status in ["creator", "administrator"]
    
    db_mods = db.get_moderators(chat_id)
    mod_rights = next((m for m in db_mods if m[2] == user_id), None)
    
    # Разбор команды
    cmd_match = re.match(r'^(мут|бан|кик|размут|разбан)\s*(.*)$', text_strip, re.IGNORECASE)
    if not cmd_match:
        return
        
    cmd = cmd_match.group(1).lower()
    args = cmd_match.group(2).strip()
    
    # Проверка специфического права
    has_right = is_tg_admin
    if mod_rights:
        if cmd == "мут" and mod_rights[4]: has_right = True
        if cmd == "бан" and mod_rights[5]: has_right = True
        if cmd == "кик" and mod_rights[6]: has_right = True
        if cmd in ["размут", "разбан"] and (mod_rights[4] or mod_rights[5]): has_right = True
        
    if not has_right:
        return  # Нет прав — игнорируем

    # Определение цели (target)
    target_id = None
    target_fullname = "Участник"
    remaining_text = args
    
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        target_fullname = message.reply_to_message.from_user.full_name
    else:
        # Пытаемся найти юзернейм @username в тексте аргументов
        mention_match = re.search(r'@(\w+)', args)
        if mention_match:
            target_username = mention_match.group(1)
            target_id = db.get_id_by_username(target_username)
            target_fullname = f"@{target_username}"
            remaining_text = args.replace(f"@{target_username}", "").strip()
            
    if not target_id:
        await message.reply("❌ Не могу найти этого пользователя. Ему нужно написать хотя бы одно сообщение в чат, чтобы бот его запомнил, либо используйте ответ (reply)!")
        return

    # Парсинг времени и причины
    duration_delta = None
    duration_str = ""
    reason = "-"
    
    if cmd in ["мут", "бан"]:
        time_match = re.search(r'(\d+)\s*(минут|мин|м|час|часа|часов|ч|день|дня|дней|д|сек)', remaining_text, re.IGNORECASE)
        if time_match:
            val = int(time_match.group(1))
            unit = time_match.group(2).lower()
            
            if any(u in unit for u in ['мин', 'м']):
                duration_delta = timedelta(minutes=val)
                duration_str = f"на {val} мин."
            elif any(u in unit for u in ['час', 'ч']):
                duration_delta = timedelta(hours=val)
                duration_str = f"на {val} час."
            elif any(u in unit for u in ['ден', 'дня', 'д']):
                duration_delta = timedelta(days=val)
                duration_str = f"на {val} дн."
            elif 'сек' in unit:
                duration_delta = timedelta(seconds=val)
                duration_str = f"на {val} сек."
                
            reason_text = remaining_text.replace(time_match.group(0), "").strip()
            if reason_text:
                reason = reason_text
        else:
            if remaining_text:
                reason = remaining_text
    else:
        if remaining_text:
            reason = remaining_text

    # Формируем HTML ссылки
    user_link = f'<a href="tg://user?id={target_id}">{target_fullname}</a>'
    admin_link = f'<a href="tg://user?id={user_id}">{message.from_user.full_name}</a>'
    
    until_date = datetime.now() + duration_delta if duration_delta else None

    # Исполнение команд
    try:
        if cmd == "мут":
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            time_label = f" замучен {duration_str}".strip()
            await message.answer(f"{user_link} был {time_label}\nМодератор: {admin_link}\nПричина: {reason}", parse_mode="HTML")
            
        elif cmd == "бан":
            await bot.ban_chat_member(chat_id=chat_id, user_id=target_id, until_date=until_date)
            time_label = f" забанен {duration_str}".strip()
            await message.answer(f"{user_link} был {time_label}\nМодератор: {admin_link}\nПричина: {reason}", parse_mode="HTML")
            
        elif cmd == "кик":
            await bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
            await bot.unban_chat_member(chat_id=chat_id, user_id=target_id, only_if_banned=True)
            await message.answer(f"{user_link} был кикнут\nМодератор: {admin_link}\nПричина: {reason}", parse_mode="HTML")
            
        elif cmd == "размут":
            # Полный ФИКС размута: возвращаем все права на общение
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_id,
                permissions=ChatPermissions(
                    can_send_messages=True, can_send_audios=True, can_send_documents=True,
                    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )
            await message.answer(f"Участник {user_link} был размучен модератором {admin_link}", parse_mode="HTML")
            
        elif cmd == "разбан":
            # Полный ФИКС разбана: параметр only_if_banned=True критически важен!
            await bot.unban_chat_member(chat_id=chat_id, user_id=target_id, only_if_banned=True)
            await message.answer(f"Участник {user_link} был разбанен модератором {admin_link}", parse_mode="HTML")
            
    except Exception as e:
        await message.reply(f"❌ Ошибка выполнения команды: Недостаточно прав у бота или указан неверный статус.")
