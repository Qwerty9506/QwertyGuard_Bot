import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import database as db

router = Router()
class BotConfig(StatesGroup): waiting_for_invite_count = State()

BOT_USERNAME = "QwertyGuard_Bot" 
ADD_URL = f"https://t.me/{BOT_USERNAME}?startgroup=true&admin=restrict_members+delete_messages+ban_users+invite_users+pin_messages"

LANGS = {
    'ru': {'sel': 'Выбран Русский язык', 'cont': '✅ Продолжить', 'groups': 'Ваши группы:', 'upd': '🔄 Обновить список', 'add': '➕ Добавить в группу', 'lang_btn': '🌐 Языки', 'back': '🔙 Назад'},
    'uz': {'sel': "O'zbek tili tanlandi", 'cont': '✅ Tasdiqlash', 'groups': 'Sizning guruhlaringiz:', 'upd': '🔄 Ro\'yxatni yangilash', 'add': '➕ Guruhga qo\'shish', 'lang_btn': '🌐 Tillar', 'back': '🔙 Orqaga'},
    'kz': {'sel': 'Қазақ тілі таңдалды', 'cont': '✅ Жалғастыру', 'groups': 'Сіздің топтарыңыз:', 'upd': '🔄 Тізімді жаңарту', 'add': '➕ Топқа қосу', 'lang_btn': '🌐 Тілдер', 'back': '🔙 Артқа'},
    'en': {'sel': 'English selected', 'cont': '✅ Continue', 'groups': 'Your groups:', 'upd': '🔄 Refresh list', 'add': '➕ Add to group', 'lang_btn': '🌐 Languages', 'back': '🔙 Back'},
    'cn': {'sel': '已选择中文', 'cont': '✅ 继续', 'groups': '你的群组:', 'upd': '🔄 刷新列表', 'add': '➕ 添加到群组', 'lang_btn': '🌐 语言', 'back': '🔙 返回'}
}

async def get_main_menu(user_id: int):
    lang = await db.get_user_lang(user_id)
    t = LANGS.get(lang, LANGS['ru'])
    groups = await db.get_user_groups(user_id)
    kb = []
    if groups:
        kb = [[InlineKeyboardButton(text=f"👥 {g_title}", callback_data=f"manage_{g_id}")] for g_id, g_title in groups]
    
    kb.append([InlineKeyboardButton(text=t['upd'], callback_data="refresh_main")])
    kb.append([InlineKeyboardButton(text=t['add'], url=ADD_URL)])
    kb.append([InlineKeyboardButton(text=t['lang_btn'], callback_data="lang_menu_init")])
    
    return t['groups'] if groups else ("Я бот-модератор. Добавь меня в группу!" if lang == 'ru' else "Bot moderator. Add me!"), InlineKeyboardMarkup(inline_keyboard=kb)

@router.message(CommandStart(), F.chat.type == "private")
async def start_cmd(message: Message, state: FSMContext):
    try: await message.delete()
    except: pass
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 🇺🇿 🇰🇿 🇺🇸 🇨🇳 Выбор языка", callback_data="lang_menu_init")]
    ])
    msg = await message.answer("Привет! Welcome! 欢迎!\nВыберите язык / Tilni tanlang / Тілді таңдаңыз:", reply_markup=kb)
    await state.update_data(last_bot_msg=msg.message_id)

@router.callback_query(F.data == "lang_menu_init")
async def lang_menu_init(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский", callback_data="setlang_ru"), InlineKeyboardButton(text="Uzbekcha", callback_data="setlang_uz")],
        [InlineKeyboardButton(text="Қазақша", callback_data="setlang_kz"), InlineKeyboardButton(text="English", callback_data="setlang_en")],
        [InlineKeyboardButton(text="中文", callback_data="setlang_cn")]
    ])
    await call.message.edit_text(" ㅤ", reply_markup=kb)

@router.callback_query(F.data.startswith("setlang_"))
async def setlang(call: CallbackQuery, state: FSMContext):
    lang = call.data.split("_")[1]
    await state.update_data(temp_lang=lang)
    t = LANGS.get(lang, LANGS['ru'])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский", callback_data="setlang_ru"), InlineKeyboardButton(text="Uzbekcha", callback_data="setlang_uz")],
        [InlineKeyboardButton(text="Қазақша", callback_data="setlang_kz"), InlineKeyboardButton(text="English", callback_data="setlang_en")],
        [InlineKeyboardButton(text="中文", callback_data="setlang_cn")],
        [InlineKeyboardButton(text=t['cont'], callback_data="confirm_lang")]
    ])
    await call.message.edit_text(t['sel'], reply_markup=kb)

@router.callback_query(F.data == "confirm_lang")
async def confirm_lang(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("temp_lang", "ru")
    await db.set_user_lang(call.from_user.id, lang)
    
    text, markup = await get_main_menu(call.from_user.id)
    await call.message.edit_text(text, reply_markup=markup)

@router.callback_query(F.data == "refresh_main")
async def refresh_main(call: CallbackQuery):
    text, markup = await get_main_menu(call.fromuser.id)
    try: await call.message.edit_text(text, reply_markup=markup)
    except: await call.answer("Изменений нет", show_alert=False)

@router.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    text, markup = await get_main_menu(call.from_user.id)
    await call.message.edit_text(text, reply_markup=markup)

@router.callback_query(F.data.startswith("manage_"))
async def manage_group(call: CallbackQuery, state: FSMContext):
    group_id = int(call.data.split("_")[1])
    await state.update_data(current_group=group_id)
    clean_id = str(group_id).replace("-100", "") 
    
    groups = await db.get_user_groups(call.from_user.id)
    group_title = next((t for i, t in groups if i == group_id), "Группа")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Колл. обяз. приглашений", callback_data="settings_invites")],
        [InlineKeyboardButton(text="🛡 Защита от спама", callback_data="settings_spam")],
        [InlineKeyboardButton(text="👮‍♂️ Модерация группы", callback_data="settings_moderation")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await call.message.edit_text(f"⚙️ Управление группой\n[{group_title}](https://t.me/c/{clean_id}/1)", reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)

# --- МОДЕРАЦИЯ И СТРАНИЦЫ ---
@router.callback_query(F.data == "settings_moderation")
async def settings_moderation(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    mods = await db.get_moderators(group_id)
    
    kb_buttons = []
    if not mods:
        text = "Модераторов пока нет"
    else:
        text = "👮‍♂️ **Список модераторов:**\nВыберите модератора для управления."
        for user_id, first_name, username, c_b, c_m, c_k in mods:
            name = first_name or "Без имени"
            kb_buttons.append([InlineKeyboardButton(text=f"👤 {name}", callback_data=f"modedit_{user_id}")])
            
    kb_buttons.append([InlineKeyboardButton(text="➕ Задать модератора", callback_data="modlist_0")])
    kb_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="Markdown")

@router.callback_query(F.data.startswith("modlist_"))
async def modlist_pages(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    page = int(call.data.split("_")[1])
    limit = 10
    
    users = await db.get_available_users(group_id)
    total_pages = (len(users) + limit - 1) // limit
    
    kb_buttons = []
    for user_id, first_name, username in users[page*limit : (page+1)*limit]:
        name = first_name or "Без имени"
        kb_buttons.append([InlineKeyboardButton(text=name, callback_data=f"setmod_{user_id}")])
        
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"modlist_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"modlist_{page+1}"))
        
    if nav_buttons:
        kb_buttons.append(nav_buttons)
        
    kb_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings_moderation")])
    await call.message.edit_text("Выберите участника для назначения модератором:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))

@router.callback_query(F.data.startswith("setmod_"))
async def setmod(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    user_id = int(call.data.split("_")[1])
    await db.add_moderator(group_id, user_id)
    await settings_moderation(call, state)

@router.callback_query(F.data.startswith("modedit_"))
async def modedit(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    user_id = int(call.data.split("_")[1])
    
    mods = await db.get_moderators(group_id)
    target_mod = next((m for m in mods if m[0] == user_id), None)
    if not target_mod: return
    
    _, first_name, username, c_ban, c_mute, c_kick = target_mod
    nic = username if username else first_name
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Бан: {'Вкл' if c_ban else 'Выкл'}", callback_data=f"modtog_{user_id}_can_ban")],
        [InlineKeyboardButton(text=f"Мут: {'Вкл' if c_mute else 'Выкл'}", callback_data=f"modtog_{user_id}_can_mute")],
        [InlineKeyboardButton(text=f"Кик: {'Вкл' if c_kick else 'Выкл'}", callback_data=f"modtog_{user_id}_can_kick")],
        [InlineKeyboardButton(text="❌ Разжаловать", callback_data=f"moddel_{user_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_moderation")]
    ])
    
    await call.message.edit_text(f"Управление модератором *{nic}* @{username or ''}", reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.startswith("modtog_"))
async def modtog(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    parts = call.data.split("_")
    user_id = int(parts[1])
    right_type = parts[2] + "_" + parts[3]
    await db.toggle_mod_right(group_id, user_id, right_type)
    
    call.data = f"modedit_{user_id}"
    await modedit(call, state)

@router.callback_query(F.data.startswith("moddel_"))
async def moddel(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    user_id = int(call.data.split("_")[1])
    await db.remove_moderator(group_id, user_id)
    await settings_moderation(call, state)

# --- НАСТРОЙКИ (СПАМ И ИНВАЙТЫ) ---
@router.callback_query(F.data == "settings_invites")
async def settings_invites(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    settings = await db.get_group_settings(group_id)
    req = settings[0] if settings else 0
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выключить" if req > 0 else "Включить", callback_data=f"toggle_invites_{req}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]
    ])
    await call.message.edit_text(f"Обязательные приглашения\nСостояние: **{'Включено' if req > 0 else 'Выключено'}**\nСейчас: {req}", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(BotConfig.waiting_for_invite_count)
    await state.update_data(msg_to_edit=call.message)

@router.callback_query(F.data.startswith("toggle_invites_"))
async def toggle_invites(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    req = int(call.data.split("_")[2])
    await db.update_req_invites(group_id, 0 if req > 0 else 1)
    await settings_invites(call, state)

@router.message(BotConfig.waiting_for_invite_count, F.chat.type == "private")
async def process_invite_count(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    count = int(message.text)
    data = await state.get_data()
    
    try: await message.delete()
    except: pass
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_invites_{count}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{data.get('current_group')}")]
    ])
    await data.get("msg_to_edit").edit_text(f"Обязательные приглашения\nВыбрано: {count} человек\n\nПодтвердите:", reply_markup=kb)
    await state.set_state(None)

@router.callback_query(F.data.startswith("confirm_invites_"))
async def confirm_invites(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    count = int(call.data.split("_")[2])
    await db.update_req_invites(group_id, count)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выключить" if count > 0 else "Включить", callback_data=f"toggle_invites_{count}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]
    ])
    await call.message.edit_text(f"Обязательные приглашения\nСостояние: **{'Включено' if count > 0 else 'Выключено'}**\nСейчас: {count}", reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "settings_spam")
async def settings_spam(call: CallbackQuery, state: FSMContext):
    group_id = (await state.get_data()).get("current_group")
    settings = await db.get_group_settings(group_id)
    spam_status = settings[1] if settings else 0
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выключить" if spam_status else "Включить", callback_data="toggle_spam")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_{group_id}")]
    ])
    await call.message.edit_text(f"🛡 **Защита от спама**\n\nСостояние: **{'Включено' if spam_status else 'Выключено'}**", reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "toggle_spam")
async def toggle_spam(call: CallbackQuery, state: FSMContext):
    await db.toggle_spam((await state.get_data()).get("current_group"))
    await settings_spam(call, state)