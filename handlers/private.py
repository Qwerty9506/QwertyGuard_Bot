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
# Ссылка с запросом прав админа
ADD_URL = f"https://t.me/{BOT_USERNAME}?startgroup=true&admin=restrict_members+delete_messages+ban_users+invite_users+pin_messages"

@router.message(CommandStart(), F.chat.type == "private")
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    groups = await db.get_user_groups(message.from_user.id)
    
    if groups:
        # Если группы есть — никаких приветствий, сразу меню!
        kb = [[InlineKeyboardButton(text=f"👥 {g_title}", callback_data=f"manage_{g_id}")] for g_id, g_title in groups]
        kb.append([InlineKeyboardButton(text="➕ Добавить в группу", url=ADD_URL)])
        await message.answer("Ваши группы:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        # Если групп нет
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить в группу", url=ADD_URL)]])
        await message.answer("Я бот-модератор. Добавь меня в группу!", reply_markup=kb)

@router.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    groups = await db.get_user_groups(call.from_user.id)
    kb = [[InlineKeyboardButton(text=f"👥 {g_title}", callback_data=f"manage_{g_id}")] for g_id, g_title in groups]
    kb.append([InlineKeyboardButton(text="➕ Добавить в группу", url=ADD_URL)])
    await call.message.edit_text("Ваши группы:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# (Остальной код private.py из прошлого моего ответа для кнопок управления остается таким же, он работал отлично)
# Ниже приведу кусок для возврата в меню группы, чтобы не было путаницы.
@router.callback_query(F.data.startswith("manage_"))
async def manage_group(call: CallbackQuery, state: FSMContext):
    group_id = int(call.data.split("_")[1])
    await state.update_data(current_group=group_id)
    clean_id = str(group_id).replace("-100", "") 
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Колл. обяз. приглашений", callback_data="settings_invites")],
        [InlineKeyboardButton(text="🛡 Защита от спама", callback_data="settings_spam")],
        [InlineKeyboardButton(text="👮‍♂️ Модерация группы", callback_data="settings_moderation")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await call.message.edit_text(f"⚙️ Управление группой [Перейти в чат](https://t.me/c/{clean_id}/1)", reply_markup=kb, parse_mode="Markdown")

# Настройки инвайтов
@router.callback_query(F.data == "settings_invites")
async def settings_invites(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("current_group")
    settings = await db.get_group_settings(group_id)
    req_invites = settings[0] if settings else 0
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]])
    await call.message.edit_text(f"Количество обязательных приглашений\nСейчас: {req_invites} человек\n\nНапишите сколько человек надо добавить:", reply_markup=kb)
    await state.set_state(BotConfig.waiting_for_invite_count)
    await state.update_data(msg_to_edit=call.message)

@router.message(BotConfig.waiting_for_invite_count, F.chat.type == "private")
async def process_invite_count(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    count = int(message.text)
    data = await state.get_data()
    group_id, msg_to_edit = data.get("current_group"), data.get("msg_to_edit")
    await asyncio.sleep(1.5)
    await message.delete()
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
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]])
    await call.message.edit_text(f"Количество обязательных приглашений\nСейчас: {count} человек", reply_markup=kb)

# Антиспам
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
    await call.message.edit_text(f"Режим защита от спама поможет удалять повторяющиеся подряд сообщения 2+\n\nСостояние: {status_text}", reply_markup=kb)

@router.callback_query(F.data == "toggle_spam")
async def toggle_spam(call: CallbackQuery, state: FSMContext):
    await db.toggle_spam((await state.get_data()).get("current_group"))
    await settings_spam(call, state)

# Заглушка модерации для меню (основная работа модерации теперь в group.py)
@router.callback_query(F.data == "settings_moderation")
async def settings_moderation(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]])
    await call.message.edit_text("Модерация работает прямо в группе! Напишите 'Бан 2 часа' в ответ на сообщение.", reply_markup=kb)
