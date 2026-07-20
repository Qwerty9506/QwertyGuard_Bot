import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import database as db

router = Router()

class BotConfig(StatesGroup):
    waiting_for_invite_count = State()

# Клавиатура стартового меню
def start_kb(has_groups=False):
    kb = []
    if not has_groups:
        kb.append([InlineKeyboardButton(text="➕ Добавить в группу", url="https://t.me/ТВОЙ_БОТ?startgroup=true")])
    else:
        kb.append([InlineKeyboardButton(text="📁 Мои группы", callback_data="my_groups")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.message(CommandStart(), F.chat.type == "private")
async def start_cmd(message: Message):
    # В реальном проекте тут проверка по БД, есть ли у юзера группы
    has_groups = True # Заглушка
    text = "👋 Привет! Я бот-модератор.\n\n🛡 Защищаю от спама, слежу за инвайтами и наказываю нарушителей. Добавь меня в группу и выдай права администратора!"
    await message.answer(text, reply_markup=start_kb(has_groups))

@router.callback_query(F.data == "my_groups")
async def show_groups(call: CallbackQuery):
    # Заглушка. Тут нужно достать группы из БД, где юзер админ
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Супер Группа", callback_data="manage_-100123456789")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await call.message.edit_text("Ваши группы:", reply_markup=kb)

@router.callback_query(F.data.startswith("manage_"))
async def manage_group(call: CallbackQuery, state: FSMContext):
    group_id = int(call.data.split("_")[1])
    await state.update_data(current_group=group_id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Колл. обяз. приглашений", callback_data="settings_invites")],
        [InlineKeyboardButton(text="🛡 Защита от спама", callback_data="settings_spam")],
        [InlineKeyboardButton(text="👮‍♂️ Модерация группы", callback_data="settings_moderation")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="my_groups")]
    ])
    await call.message.edit_text(f"⚙️ Управление группой [Группа](https://t.me/c/{str(group_id)[4:]}/1)", reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "settings_invites")
async def settings_invites(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("current_group")
    settings = await db.get_group_settings(group_id)
    req_invites = settings[0] if settings else 0
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]])
    await call.message.edit_text(
        f"🔢 Количество обязательных приглашений\nСейчас: {req_invites} человек\n\nНапишите в чат цифру, сколько человек нужно добавить:",
        reply_markup=kb
    )
    await state.set_state(BotConfig.waiting_for_invite_count)
    await state.update_data(msg_to_edit=call.message)

@router.message(BotConfig.waiting_for_invite_count, F.chat.type == "private")
async def process_invite_count(message: Message, state: FSMContext):
    if not message.text.isdigit():
        msg = await message.answer("❌ Пожалуйста, отправьте только число!")
        await asyncio.sleep(2)
        await msg.delete()
        await message.delete()
        return

    count = int(message.text)
    data = await state.get_data()
    group_id = data.get("current_group")
    msg_to_edit: Message = data.get("msg_to_edit")

    # Удаляем сообщение пользователя через 1.5 секунды
    await asyncio.sleep(1.5)
    await message.delete()

    # Обновляем сообщение меню
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_invites_{count}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]
    ])
    await msg_to_edit.edit_text(
        f"🔢 Количество обязательных приглашений\nВыбрано: {count} человек\n\nНажмите подтвердить для сохранения.",
        reply_markup=kb
    )
    await state.set_state(None)

@router.callback_query(F.data.startswith("confirm_invites_"))
async def confirm_invites(call: CallbackQuery, state: FSMContext):
    count = int(call.data.split("_")[2])
    data = await state.get_data()
    group_id = data.get("current_group")
    
    await db.update_req_invites(group_id, count)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]])
    await call.message.edit_text(f"✅ Успешно!\nСейчас: {count} человек", reply_markup=kb)
