import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import database as db

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

@router.message(F.new_chat_members)
async def on_user_join(message: Message, bot: Bot):
    # Если добавили бота
    for new_member in message.new_chat_members:
        if new_member.id == bot.id:
            # Сохраняем группу и человека, который добавил бота, как владельца
            await db.add_group(message.chat.id, message.chat.title, message.from_user.id)
            await message.answer("Всем привет)")
            return # Выходим, чтобы не писать приветствие как для обычного юзера
            
    # Если зашел обычный пользователь
    settings = await db.get_group_settings(message.chat.id)
    req_invites = settings[0] if settings else 0
    
    for new_member in message.new_chat_members:
        if req_invites > 0:
            await bot.restrict_chat_member(
                message.chat.id, new_member.id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            
            # Внимание: замени ТВОЙ_БОТ на юзернейм
            bot_username = (await bot.get_me()).username
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Я добавил", callback_data=f"check_{new_member.id}")],
                [InlineKeyboardButton(text="🔓 Отпустить", callback_data=f"release_{new_member.id}")]
            ])
            
            msg = await message.answer(
                f"{new_member.first_name}, вам нельзя писать в группе!\n\n"
                f"Для получения доступа нужно добавить {req_invites} друзей.\n"
                f"Ваша реф ссылка приглашения [тык](https://t.me/{bot_username}?start=ref_{message.chat.id})",
                reply_markup=kb,
                disable_web_page_preview=True,
                parse_mode="Markdown"
            )
            
            await asyncio.sleep(299.4) # 4.99 минут
            try:
                await msg.delete()
            except:
                pass

@router.callback_query(F.data.startswith("release_"))
async def release_user(call: CallbackQuery, bot: Bot):
    user_id = int(call.data.split("_")[1])
    await bot.restrict_chat_member(
        call.message.chat.id, user_id,
        permissions=ChatPermissions(
            can_send_messages=True, can_send_media_messages=True, 
            can_send_other_messages=True, can_add_web_page_previews=True
        )
    )
    await call.message.delete()
