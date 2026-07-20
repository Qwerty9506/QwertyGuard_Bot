import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import database as db

router = Router()
class BotConfig(StatesGroup): waiting_for_invite_count = State()

BOT_USERNAME = "QwertyGuard_Bot" # <--- ВПИШИ ЮЗЕРНЕЙМ БОТА БЕЗ @
ADD_URL = f"https://t.me/{BOT_USERNAME}?startgroup=true&admin=restrict_members+delete_messages+ban_users+invite_users+pin_messages"

async def get_main_menu(user_id: int):
    groups = await db.get_user_groups(user_id)
    kb = []
    if groups:
        kb = [[InlineKeyboardButton(text=f"👥 {g_title}", callback_data=f"manage_{g_id}")] for g_id, g_title in groups]
        kb.append([InlineKeyboardButton(text="🔄 Обновить список", callback_data="refresh_main")])
        kb.append([InlineKeyboardButton(text="➕ Добавить в группу", url=ADD_URL)])
        return "Ваши группы:", InlineKeyboardMarkup(inline_keyboard=kb)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить список", callback_data="refresh_main")],
            [InlineKeyboardButton(text="➕ Добавить в группу", url=ADD_URL)]
        ])
        return "Я бот-модератор. Добавь меня в группу!", kb

@router.message(CommandStart(), F.chat.type == "private")
async def start_cmd(message: Message, state: FSMContext):
    data = await state.get_data()
    
    try: await message.delete()
    except: pass

    last_bot_msg = data.get("last_bot_msg")
    if last_bot_msg:
        try: await message.chat.delete_message(last_bot_msg)
        except: pass

    await state.clear()
    text, markup = await get_main_menu(message.from_user.id)
    msg = await message.answer(text, reply_markup=markup)
        
    await state.update_data(last_bot_msg=msg.message_id)

@router.callback_query(F.data == "refresh_main")
async def refresh_main(call: CallbackQuery):
    text, markup = await get_main_menu(call.from_user.id)
    try:
        await call.message.edit_text(text, reply_markup=markup)
        await call.answer("Список групп успешно обновлен!")
    except Exception:
        await call.answer("Изменений в списке групп нет.", show_alert=False)

@router.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_bot_msg = data.get("last_bot_msg")
    
    await state.clear()
    if last_bot_msg:
        await state.update_data(last_bot_msg=last_bot_msg)
        
    text, markup = await get_main_menu(call.from_user.id)
    await call.message.edit_text(text, reply_markup=markup)

@router.callback_query(F.data.startswith("manage_"))
async def manage_group(call: CallbackQuery, state: FSMContext):
    group_id = int(call.data.split("_")[1])
    await state.update_data(current_group=group_id)
    clean_id = str(group_id).replace("-100", "") 
    
    groups = await db.get_user_groups(call.from_user.id)
    group_title = "Группа"
    for g_id, g_title in groups:
        if g_id == group_id:
            group_title = g_title
            break

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Колл. обяз. приглашений", callback_data="settings_invites")],
        [InlineKeyboardButton(text="🛡 Защита от спама", callback_data="settings_spam")],
        [InlineKeyboardButton(text="👮‍♂️ Модерация группы", callback_data="settings_moderation")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await call.message.edit_text(f"⚙️ Управление группой\n[{group_title}](https://t.me/c/{clean_id}/1)", reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "settings_moderation")
async def settings_moderation(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]
    ])
    await call.message.edit_text("👮‍♂️ **Модерация группы**\n\nРаздел в разработке. Здесь скоро будут настройки прав модераторов!", reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "settings_invites")
async def settings_invites(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("current_group")
    settings = await db.get_group_settings(group_id)
    req_invites = settings[0] if settings else 0
    
    status_text = "Включено" if req_invites > 0 else "Выключено"
    btn_text = "Выключить" if req_invites > 0 else "Включить"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, callback_data=f"toggle_invites_{req_invites}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]
    ])
    
    await call.message.edit_text(
        f"Количество обязательных приглашений\n"
        f"Состояние: **{status_text}**\n"
        f"Сейчас: {req_invites} человек\n\n"
        f"Напишите сколько человек надо добавить (или переключите статус):", 
        reply_markup=kb, parse_mode="Markdown"
    )
    await state.set_state(BotConfig.waiting_for_invite_count)
    await state.update_data(msg_to_edit=call.message)

@router.callback_query(F.data.startswith("toggle_invites_"))
async def toggle_invites(call: CallbackQuery, state: FSMContext):
    current_val = int(call.data.split("_")[2])
    group_id = (await state.get_data()).get("current_group")
    
    if current_val > 0:
        await db.update_req_invites(group_id, 0)
    else:
        await db.update_req_invites(group_id, 1) 
        
    await settings_invites(call, state)

@router.message(BotConfig.waiting_for_invite_count, F.chat.type == "private")
async def process_invite_count(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    count = int(message.text)
    data = await state.get_data()
    group_id, msg_to_edit = data.get("current_group"), data.get("msg_to_edit")
    await asyncio.sleep(1.5)
    
    try: await message.delete()
    except: pass
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_invites_{count}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]
    ])
    await msg_to_edit.edit_text(f"Количество обязательных приглашений\nВыбрано: {count} человек\n\nПодтвердите сохранение:", reply_markup=kb)
    await state.set_state(None)

@router.callback_query(F.data.startswith("confirm_invites_"))
async def confirm_invites(call: CallbackQuery, state: FSMContext):
    count = int(call.data.split("_")[2])
    group_id = (await state.get_data()).get("current_group")
    await db.update_req_invites(group_id, count)
    
    status_text = "Включено" if count > 0 else "Выключено"
    btn_text = "Выключить" if count > 0 else "Включить"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, callback_data=f"toggle_invites_{count}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]
    ])
    await call.message.edit_text(
        f"Количество обязательных приглашений\n"
        f"Состояние: **{status_text}**\n"
        f"Сейчас: {count} человек", 
        reply_markup=kb, parse_mode="Markdown"
    )

@router.callback_query(F.data == "settings_spam")
async def settings_spam(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    settings = await db.get_group_settings(group_id)
    spam_status = settings[1] if settings else 0
    status_text = "Включено" if spam_status else "Выключено"
    btn_text = "Выключить" if spam_status else "Включить"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, callback_data="toggle_spam")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]
    ])
    text = (
        "🛡 **Защита от спама** поможет удалять повторяющиеся сообщения.\n\n"
        "**Как это работает:**\n"
        "• **10 сообщений за 6 секунд** ➔ Проверка (Капча).\n"
        "• **3 одинаковых сообщения подряд** ➔ Проверка (Капча).\n"
        "• **Не прошел проверку (12 сек)** ➔ Бан и удаление спама за последние 5 минут.\n"
        "• **Прошел, но снова спамит** ➔ Бан и удаление спама за последние 5 минут.\n\n"
        f"Состояние: **{status_text}**"
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "toggle_spam")
async def toggle_spam(call: CallbackQuery, state: FSMContext):
    await db.toggle_spam((await state.get_data()).get("current_group"))
    await settings_spam(call, state)