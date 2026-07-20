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

@router.message(CommandStart(), F.chat.type == "private")
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    groups = await db.get_user_groups(message.from_user.id)
    
    if groups:
        # Без лишнего текста если группы уже есть
        kb = [[InlineKeyboardButton(text=f"👥 {g_title}", callback_data=f"manage_{g_id}")] for g_id, g_title in groups]
        kb.append([InlineKeyboardButton(text="➕ Добавить в новую группу", url=ADD_URL)])
        await message.answer("Ваши группы:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить в группу", url=ADD_URL)]])
        await message.answer("Я бот-модератор. Добавь меня в группу!", reply_markup=kb)

@router.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    groups = await db.get_user_groups(call.from_user.id)
    kb = [[InlineKeyboardButton(text=f"👥 {g_title}", callback_data=f"manage_{g_id}")] for g_id, g_title in groups]
    kb.append([InlineKeyboardButton(text="➕ Добавить в группу", url=ADD_URL)])
    await call.message.edit_text("Ваши группы:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

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

# --- НАСТРОЙКИ ИНВАЙТОВ ---
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

# --- НАСТРОЙКИ АНТИСПАМА ---
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


# --- ПОЛНОЦЕННАЯ ПАНЕЛЬ МОДЕРАЦИИ ---
@router.callback_query(F.data == "settings_moderation")
async def settings_moderation(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    mods = await db.get_moderators(group_id)
    
    kb = []
    text = "Список модераторов:\n"
    if not mods:
        text = "Модераторов пока нет.. (владелец не считается)"
    else:
        for mod in mods:
            user_id, first_name, username, c_b, c_m, c_k = mod
            name = f"{first_name}" + (f" (@{username})" if username else "")
            kb.append([InlineKeyboardButton(text=f"👮‍♂️ {name}", callback_data=f"modpanel_{user_id}")])
            
    kb.append([InlineKeyboardButton(text="➕ Добавить модераторов", callback_data="add_mod_list")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# Выбор пользователей для становления модератором
@router.callback_query(F.data == "add_mod_list")
async def add_mod_list(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    users = await db.get_available_users(group_id)
    
    kb = []
    for u in users:
        uid, fn, un = u
        label = f"{fn}" + (f" (@{un})" if un else "")
        kb.append([InlineKeyboardButton(text=label, callback_data=f"setmod_{uid}")])
        
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings_moderation")])
    
    text = "Выберите пользователя из списка участников (тех, кто писал в группе):"
    if not users:
        text = "В базе пока нет участников. Пусть кто-нибудь напишет сообщение в группе!"
        
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# Сохраняем модератора и открываем его панель
@router.callback_query(F.data.startswith("setmod_"))
async def set_moderator(call: CallbackQuery, state: FSMContext):
    target_id = int(call.data.split("_")[1])
    group_id = (await state.get_data()).get("current_group")
    await db.add_moderator(group_id, target_id)
    await mod_panel_open(call, state, target_id)

@router.callback_query(F.data.startswith("modpanel_"))
async def mod_panel_route(call: CallbackQuery, state: FSMContext):
    target_id = int(call.data.split("_")[1])
    await mod_panel_open(call, state, target_id)

# Отрисовка профиля модератора и его прав
async def mod_panel_open(call: CallbackQuery, state: FSMContext, target_id: int):
    group_id = (await state.get_data()).get("current_group")
    mod = None
    mods = await db.get_moderators(group_id)
    for m in mods:
        if m[0] == target_id:
            mod = m
            break
            
    if not mod:
        return await settings_moderation(call, state)
        
    user_id, first_name, username, c_ban, c_mute, c_kick = mod
    name = f"Модератор {first_name}" + (f" @{username}" if username else "")
    
    def s(val): return "Вкл" if val else "Выкл"
    
    kb = [
        [InlineKeyboardButton(text=f"Бан {s(c_ban)}", callback_data=f"togglemod_can_ban_{target_id}")],
        [InlineKeyboardButton(text=f"Мут {s(c_mute)}", callback_data=f"togglemod_can_mute_{target_id}")],
        [InlineKeyboardButton(text=f"Кик {s(c_kick)}", callback_data=f"togglemod_can_kick_{target_id}")],
        [InlineKeyboardButton(text="❌ Удалить модератора", callback_data=f"delmod_{target_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_moderation")]
    ]
    
    await call.message.edit_text(name, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# Переключение конкретного права
@router.callback_query(F.data.startswith("togglemod_"))
async def toggle_mod(call: CallbackQuery, state: FSMContext):
    # format: togglemod_can_ban_12345
    parts = call.data.split("_")
    right_type = parts[1] + "_" + parts[2]
    target_id = int(parts[3])
    group_id = (await state.get_data()).get("current_group")
    
    await db.toggle_mod_right(group_id, target_id, right_type)
    await mod_panel_open(call, state, target_id)

# Удаление модератора
@router.callback_query(F.data.startswith("delmod_"))
async def del_mod(call: CallbackQuery, state: FSMContext):
    target_id = int(call.data.split("_")[1])
    group_id = (await state.get_data()).get("current_group")
    await db.remove_moderator(group_id, target_id)
    await settings_moderation(call, state)