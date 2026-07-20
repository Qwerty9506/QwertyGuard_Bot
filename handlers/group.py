import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import database as db

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

# Временная память для антиспама: {group_id: {user_id: {"text": "сообщение", "count": 1}}}
spam_cache = {}

@router.message(F.new_chat_members)
async def on_user_join(message: Message, bot: Bot):
    settings = await db.get_group_settings(message.chat.id)
    if not settings:
        await db.add_group(message.chat.id, message.chat.title)
        settings = (0, 0)
    
    req_invites = settings[0]
    
    for new_member in message.new_chat_members:
        if new_member.id == bot.id:
            await message.answer("👋 Всем привет! Я бот-модератор. Админы, настройте меня в ЛС.")
            continue
            
        if req_invites > 0:
            # Забираем права писать
            await bot.restrict_chat_member(
                message.chat.id, new_member.id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Получить ссылку", url="https://t.me/ТВОЙ_БОТ?start=get_link")],
                [InlineKeyboardButton(text="✅ Я добавил", callback_data=f"check_invites_{new_member.id}")],
                [InlineKeyboardButton(text="🔓 Отпустить (Админ)", callback_data=f"release_{new_member.id}")]
            ])
            
            msg = await message.answer(
                f"👤 {new_member.first_name}, вам нельзя писать в группе!\n\n"
                f"Для получения доступа нужно добавить {req_invites} друзей.\n"
                f"👉 [ТЫК - получить ссылку](https://t.me/ТВОЙ_БОТ?start=get_link)",
                reply_markup=kb,
                disable_web_page_preview=True
            )
            
            # Удаление через 4.99 минут (299 сек)
            await asyncio.sleep(299)
            try:
                await msg.delete()
            except:
                pass

@router.callback_query(F.data.startswith("release_"))
async def release_user(call: CallbackQuery, bot: Bot):
    # Тут нужна проверка на админа
    user_id = int(call.data.split("_")[1])
    await bot.restrict_chat_member(
        call.message.chat.id, user_id,
        permissions=ChatPermissions(
            can_send_messages=True, can_send_media_messages=True, 
            can_send_other_messages=True, can_add_web_page_previews=True
        )
    )
    await call.message.delete()
    await call.answer("✅ Пользователь отпущен!", show_alert=True)

@router.message(F.text)
async def anti_spam_and_commands(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.lower()
    
    # 1. АНТИСПАМ (работает, если включен в БД, тут для простоты показываю саму логику)
    if chat_id not in spam_cache:
        spam_cache[chat_id] = {}
        
    user_cache = spam_cache[chat_id].get(user_id)
    
    if user_cache and user_cache["text"] == text:
        user_cache["count"] += 1
        
        if user_cache["count"] == 2:
            await message.delete() # Удаляем второе такое же
        elif user_cache["count"] >= 3:
            await message.delete()
            await bot.ban_chat_member(chat_id, user_id) # Кик (бан + сразу анбан)
            await bot.unban_chat_member(chat_id, user_id)
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔓 Отпустить (Ошибочно)", callback_data=f"release_{user_id}")]
            ])
            await message.answer(f"🛑 Спамер @{message.from_user.username} был кикнут.\nПричина: Спам 3+ сообщений подряд", reply_markup=kb)
            spam_cache[chat_id].pop(user_id) # Очищаем после кика
            return
    else:
        spam_cache[chat_id][user_id] = {"text": text, "count": 1}

    # 2. ПРОСТАЯ МОДЕРАЦИЯ (Мут, Бан, Кик)
    # Пример команды: "Бан 2 часа" или "Кик" (ответом на сообщение)
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        
        if text.startswith("бан"):
            await bot.ban_chat_member(chat_id, target.id)
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔓 Отпустить", callback_data=f"release_{target.id}")]])
            await message.answer(f"🔨 {target.first_name} был забанен.\nПричина: Модерация", reply_markup=kb)
            
        elif text.startswith("кик"):
            await bot.ban_chat_member(chat_id, target.id)
            await bot.unban_chat_member(chat_id, target.id)
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔓 Отпустить", callback_data=f"release_{target.id}")]])
            await message.answer(f"👢 {target.first_name} был кикнут.\nПричина: Модерация", reply_markup=kb)
