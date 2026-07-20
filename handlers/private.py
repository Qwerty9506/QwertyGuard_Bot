# handlers/private.py
import html
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from config import BOT_USERNAME
import database as db

router = Router()
router.message.filter(F.chat.type == "private")

class ModStates(StatesGroup):
    waiting_for_moder_id = State()

def get_main_keyboard(user_id):
    groups = db.get_user_groups(user_id)
    buttons = []
    for g_id, g_name, _ in groups:
        buttons.append([InlineKeyboardButton(text=f"👥 {g_name}", callback_data=f"manage_group:{g_id}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить в группу", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("start"))
async def start_cmd(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    last_id = db.get_last_menu(message.from_user.id)
    if last_id:
        try:
            await bot.delete_message(chat_id=message.from_user.id, message_id=last_id)
        except Exception:
            pass
            
    msg = await message.answer("<b>Ваши группы:</b>", reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")
    db.set_last_menu(message.from_user.id, msg.message_id)

@router.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated, bot: Bot):
    if event.new_chat_member.status in ["administrator", "member"]:
        group_id = event.chat.id
        group_name = event.chat.title
        creator_id = event.from_user.id
        
        db.add_group(group_id, group_name, creator_id)
        
        last_id = db.get_last_menu(creator_id)
        if last_id:
            try:
                await bot.edit_message_text(
                    text="<b>Ваши группы:</b>\n\n<i>(Список обновлен! Добавлена новая группа)</i>",
                    chat_id=creator_id,
                    message_id=last_id,
                    reply_markup=get_main_keyboard(creator_id),
                    parse_mode="HTML"
                )
            except Exception:
                pass

@router.callback_query(F.data.startswith("manage_group:"))
async def manage_group(callback: CallbackQuery):
    group_id = int(callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👮 Модераторы", callback_data=f"group_mods:{group_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text("⚙️ Управление модерацией группы:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text("<b>Ваши группы:</b>", reply_markup=get_main_keyboard(callback.from_user.id), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("group_mods:"))
async def group_mods(callback: CallbackQuery):
    group_id = int(callback.data.split(":")[1])
    moders = db.get_moderators(group_id)
    
    buttons = []
    for m in moders:
        buttons.append([InlineKeyboardButton(text=f"👤 {m[3]} (ID: {m[2]})", callback_data=f"edit_mod:{group_id}:{m[2]}")])
        
    buttons.append([InlineKeyboardButton(text="➕ Добавить модератора", callback_data=f"add_mod_prompt:{group_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"manage_group:{group_id}")])
    
    await callback.message.edit_text("Список модераторов группы и их права:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@router.callback_query(F.data.startswith("add_mod_prompt:"))
async def add_mod_prompt(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split(":")[1])
    await state.update_data(group_id=group_id)
    await state.set_state(ModStates.waiting_for_moder_id)
    await callback.message.edit_text("Отправьте Telegram ID пользователя и через пробел его Ник (например: 12345678 Qwerty):")
    await callback.answer()

@router.message(ModStates.waiting_for_moder_id)
async def process_add_moder(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    group_id = data['group_id']
    await state.clear()
    
    try:
        user_id_str, username = message.text.split(maxsplit=1)
        user_id = int(user_id_str)
        db.add_moderator(group_id, user_id, username)
        msg_text = f"✅ Модератор {html.escape(username)} добавлен!"
    except Exception:
        msg_text = "❌ Ошибка. Вводите строго по шаблону: ID Ник"
        
    last_id = db.get_last_menu(message.from_user.id)
    if last_id:
        try: await bot.delete_message(message.from_user.id, last_id)
        except Exception: pass
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ К списку модераторов", callback_data=f"group_mods:{group_id}")]])
    msg = await message.answer(msg_text, reply_markup=kb)
    db.set_last_menu(message.from_user.id, msg.message_id)

@router.callback_query(F.data.startswith("edit_mod:"))
async def edit_mod(callback: CallbackQuery):
    _, group_id, user_id = callback.data.split(":")
    group_id, user_id = int(group_id), int(user_id)
    
    moders = db.get_moderators(group_id)
    m = next((x for x in moders if x[2] == user_id), None)
    
    if not m:
        await callback.answer("Модератор не найден.")
        return
        
    m_mute = "✅ Мут" if m[4] else "❌ Мут"
    m_ban = "✅ Бан" if m[5] else "❌ Бан"
    m_kick = "✅ Кик" if m[6] else "❌ Кик"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=m_mute, callback_data=f"toggle:mute:{group_id}:{user_id}")],
        [InlineKeyboardButton(text=m_ban, callback_data=f"toggle:ban:{group_id}:{user_id}")],
        [InlineKeyboardButton(text=m_kick, callback_data=f"toggle:kick:{group_id}:{user_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"group_mods:{group_id}")]
    ])
    
    await callback.message.edit_text(f"Настройка прав для модератора <b>{html.escape(m[3])}</b>:", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("toggle:"))
async def toggle_right(callback: CallbackQuery):
    _, right, group_id, user_id = callback.data.split(":")
    group_id, user_id = int(group_id), int(user_id)
    
    db.toggle_moderator_right(group_id, user_id, right)
    
    moders = db.get_moderators(group_id)
    m = next((x for x in moders if x[2] == user_id), None)
    
    m_mute = "✅ Мут" if m[4] else "❌ Мут"
    m_ban = "✅ Бан" if m[5] else "❌ Бан"
    m_kick = "✅ Кик" if m[6] else "❌ Кик"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=m_mute, callback_data=f"toggle:mute:{group_id}:{user_id}")],
        [InlineKeyboardButton(text=m_ban, callback_data=f"toggle:ban:{group_id}:{user_id}")],
        [InlineKeyboardButton(text=m_kick, callback_data=f"toggle:kick:{group_id}:{user_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"group_mods:{group_id}")]
    ])
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer()
