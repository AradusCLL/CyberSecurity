import os
import io 
import re 
import requests 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
)
from telegram.error import BadRequest
from google import genai
from google.genai import types

# --- 1. КОНФИГУРАЦИЯ И КЛЮЧИ ---

BOT_TOKEN = "8259649452:AAGBclEBC9U04h2n6ymElPeOEjklirvkLsw"
GEMINI_KEY = "AIzaSyBaOhR_e9U3VzBmgKwFaopwMOLYOavFnko" 

# Инициализация Gemini
try:
    client = genai.Client(api_key=GEMINI_KEY)
    print("✅ Gemini API готов.")
except Exception as e:
    print(f"❌ Ошибка Gemini: {e}")
    client = None

# Словарь для хранения объекта чата (истории) для каждого пользователя
user_chats = {} 

# Системный промпт 
EXPERT_PROMPT = (
    "Ты — русскоязычный, проактивный **Цифровой Телохранитель** (Cybersecurity Guardian) на базе ИИ. "
    "Твой стиль общения: уверенный, прямой, с легким оттенком боевой готовности. "
    "Твоя ГЛАВНАЯ МИССИЯ: Оценить угрозу, дать четкий вердикт и предоставить инструкцию для немедленной защиты. "
    
    "**1. Анализ Угроз и Вердикт:** "
    "— Ты способен молниеносно анализировать ТЕКСТ, ИЗОБРАЖЕНИЯ и ССЫЛКИ. "
    "— НИКОГДА не переходи по ссылкам. Оценивай только их структуру. "
    "— Твой ответ ДОЛЖЕН начинаться с яркого, однозначного вердикта, выделенного эмодзи: **🟢 БЕЗОПАСНО**, **⚠️ РИСКОВАННО** или **🔴 ОПАСНО**. "

    "**2. Стиль и UX:** "
    "— Используй КРАТКИЕ и СЖАТЫЕ фразы, идеальные для Telegram. Избегай длинных вступлений. "
    "— АКТИВНО используй Markdown (**жирный**, *курсив*, списки) и яркие эмодзи для наглядности. "
    "— Персонализируй обращение, используя контекст и имя пользователя (если известно). "
    "— Помни, что тебе нужно обработать команды **/reset** и **КРАТКОЕ РЕЗЮМЕ**. "
)

# Конфигурация для передачи системной инструкции (используется при создании чата)
GEMINI_CONFIG = types.GenerateContentConfig(
    system_instruction=EXPERT_PROMPT
)

# --- 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

# Функция для получения или создания объекта чата для пользователя
def get_or_create_chat(user_id):
    """Получает существующий чат или создает новый, используя EXPERT_PROMPT."""
    if user_id not in user_chats:
        user_chats[user_id] = client.chats.create(
            model='gemini-2.5-flash',
            config=GEMINI_CONFIG 
        )
    return user_chats[user_id]

# Функция для создания разметки кнопки "Краткое резюме"
def build_summary_markup(message_id):
    """Создает InlineKeyboardMarkup с кнопкой резюме."""
    keyboard = [[
        InlineKeyboardButton("📝 Краткое резюме", callback_data=f"summary_{message_id}")
    ]]
    return InlineKeyboardMarkup(keyboard)

# Разметка для навигационных кнопок 
def build_navigation_markup():
    """Создает InlineKeyboardMarkup с навигационными кнопками."""
    keyboard = [
        [
            InlineKeyboardButton("🔍 Проверить ссылку", callback_data="nav_link"),
            InlineKeyboardButton("📸 Анализ фото", callback_data="nav_photo"),
        ],
        [
            InlineKeyboardButton("ℹ️ О боте", callback_data="nav_about"), 
            InlineKeyboardButton("❓ Помощь / Команды", callback_data="nav_help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# --- 3. ОБРАБОТЧИКИ КОМАНД И СООБЩЕНИЙ ---

# Приветствие
async def start(update, context):
    await update.message.reply_text(
        "👋 Привет! Я ваш помощник по кибербезопасности (на базе Gemini). "
        "Теперь я помню, о чем мы говорили! "
        "Спросите, отправьте фото или **подозрительную ссылку** для анализа.🛡️",
        reply_markup=build_navigation_markup()
    )

# Команда для сброса контекста чата
async def reset_chat(update: Update, context):
    user_id = update.message.from_user.id
    if user_id in user_chats:
        del user_chats[user_id] 
        await update.message.reply_text(
            "🗑️ Контекст разговора сброшен! Теперь мы начинаем новый диалог. "
            "Это поможет снизить расходы на токены."
        )
    else:
        await update.message.reply_text("Контекст и так пуст.")


# Обработчик нажатия кнопок
async def handle_callback_query(update: Update, context):
    query = update.callback_query
    await query.answer() 
    
    data = query.data
    chat_id = query.message.chat_id

    # --- ЛОГИКА РЕЗЮМЕ ---
    if data.startswith("summary_"):
        target_message_id = int(data.split("_")[1])
        original_message = await context.bot.forward_message(
            chat_id=chat_id,
            from_chat_id=chat_id,
            message_id=target_message_id
        )
        text_to_summarize = original_message.text
        
        # ИЗМЕНЕННЫЙ ПРОМПТ ДЛЯ РЕЗЮМЕ: Убираем сложное форматирование, чтобы избежать ошибки
        summary_prompt = "Сделай ЭКСТРА-КРАТКОЕ резюме этого текста в 1-2 предложениях. Используй ТОЛЬКО жирный текст (**) для выделения, избегай других сложных символов и форматирования. Сохрани ключевой вывод по кибербезопасности."

        await query.edit_message_text("⏳ Генерирую краткое резюме...", reply_markup=None)

        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[summary_prompt, text_to_summarize]
            )
            
            await query.edit_message_text(
                f"**📝 Краткое резюме:**\n\n{response.text}", 
                parse_mode='Markdown',
                reply_markup=build_navigation_markup()
            )
        except BadRequest as e:
            # Отдельный обработчик для ошибки парсинга Markdown
            await query.edit_message_text(
                f"❌ Ошибка форматирования текста (Markdown). Вероятно, Gemini сгенерировал сложный символ. Попробуйте сбросить чат. Подробнее: {e}",
                reply_markup=build_navigation_markup()
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка при создании резюме: {e}", reply_markup=build_navigation_markup())
        finally:
            await context.bot.delete_message(chat_id, original_message.message_id)

    # --- ЛОГИКА НАВИГАЦИИ ---
    elif data == "nav_link":
        await query.edit_message_text(
            "🔗 **Анализ ссылки**\n\nОтправьте мне подозрительный URL-адрес (начиная с `http://` или `https://`), и я его проверю, не переходя по нему.",
            parse_mode='Markdown',
            reply_markup=build_navigation_markup() 
        )
    
    elif data == "nav_photo":
        await query.edit_message_text(
            "📸 **Анализ фото**\n\nПросто отправьте мне изображение, например скриншот подозрительного SMS или QR-кода.",
            parse_mode='Markdown',
            reply_markup=build_navigation_markup()
        )
        
    elif data == "nav_about": 
        about_text = (
            "🛡️ **О Цифровом Телохранителе**\n\n"
            "Я — ваш личный эксперт по кибербезопасности на базе нейросети Gemini 2.5 Flash. "
            "Моя миссия: мгновенно оценить угрозу, дать четкий вердикт и предоставить инструкцию для немедленной защиты.\n\n"
            "**С чем я помогу:**\n"
            "— **Анализ ссылок:** Проверка URL на фишинг и мошенничество.\n" # Используем тире вместо звездочки
            "— **Анализ текста/фото:** Выявление признаков социальной инженерии.\n"
            "— **Консультации:** Ответы на любые вопросы по безопасности.\n\n"
            "👤 **Создатель:** Аскарбеков Альберт. Ученик 2 курса (Используйте /reset для сброса контекста)"
        )
        await query.edit_message_text(
            about_text,
            parse_mode='Markdown',
            reply_markup=build_navigation_markup()
        )
        
    elif data == "nav_help":
        help_text = (
            "🛡️ **Список команд и функций:**\n\n"
            "* /start - Главное меню.\n"
            "* /reset - Сбросить контекст разговора.\n"
            "* **[Текст/Ссылка/Фото]** - Автоматический анализ.\n"
        )
        await query.edit_message_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=build_navigation_markup()
        )


# Обработчик текста
async def handle_text(update, context):
    user_id = update.message.from_user.id
    msg = update.message.text
    
    # --- ОБЫЧНАЯ ЛОГИКА ТЕКСТА ---
    if not client:
        await update.message.reply_text("❌ Gemini не инициализирован.")
        return
        
    chat = get_or_create_chat(user_id) 
    
    try:
        response = chat.send_message(msg) 
        
        await update.message.reply_text(
            response.text, 
            reply_markup=build_summary_markup(update.effective_message.message_id + 1)
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка Gemini: {e}")

# Обработчик: Анализ ссылок
async def handle_link_analysis(update: Update, context):
    if not client:
        await update.message.reply_text("❌ Gemini не инициализирован.")
        return
    
    user_id = update.message.from_user.id
    chat = get_or_create_chat(user_id)
    link = update.message.text
    
    analysis_prompt = (
        f"Проведи поверхностный анализ следующего URL-адреса, НЕ ПЕРЕХОДЯ ПО НЕМУ. "
        f"Оцени его на предмет фишинга, подозрительных доменов, скрытия символов или "
        f"попытки имитировать известный бренд. Дай четкий вердикт и рекомендацию. "
        f"URL: {link}"
    )

    await update.message.reply_text(f"⏳ Анализирую ссылку: `{link}` на предмет угроз...", parse_mode='Markdown')

    try:
        response = chat.send_message(analysis_prompt)
        
        await update.message.reply_text(
            response.text, 
            reply_markup=build_summary_markup(update.effective_message.message_id + 1)
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка анализа ссылки: {e}")


# Обработка фото (с контекстом)
async def handle_photo(update, context):
    if not client:
        await update.message.reply_text("❌ Gemini не инициализирован.")
        return
        
    user_id = update.message.from_user.id
    chat = get_or_create_chat(user_id) 

    await update.message.reply_text("⏳ Анализ фото...")
    
    photo_file = await update.message.effective_attachment[-1].get_file()
    
    photo_data = io.BytesIO()
    await photo_file.download_to_memory(photo_data)
    image_bytes = photo_data.getvalue()
    
    vision_prompt = "Проанализируй изображение на угрозы: фишинг, личные данные, ссылки. Дай вердикт и рекомендации."
    
    try:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg') 
        response = chat.send_message([image_part, vision_prompt])
        
        await update.message.reply_text(
            response.text, 
            reply_markup=build_summary_markup(update.effective_message.message_id + 1)
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Критическая ошибка фотоанализа: {e}")

# --- ОБРАБОТЧИК ОШИБОК ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибки, вызванные обработчиками обновлений."""
    print(f"⚠️ Update {update} вызвал ошибку: {context.error}")

    if update and update.effective_message:
        # Попытка уведомить пользователя об ошибке
        try:
            error_message = f"🚨 **Внутренняя ошибка!** 🚨\n\nПроизошла непредвиденная ошибка. "
            
            if isinstance(context.error, BadRequest) and 'Can\'t parse entities' in str(context.error):
                 error_message += "Вероятно, проблема в форматировании Markdown от Gemini. Попробуйте сбросить чат командой /reset."
            else:
                 error_message += "Пожалуйста, повторите запрос или сбросьте контекст /reset."

            await update.effective_message.reply_text(
                error_message,
                parse_mode='Markdown'
            )
        except Exception:
            # Если даже отправка сообщения об ошибке не удалась
            print("Не удалось отправить сообщение об ошибке пользователю.")


# --- 4. ЗАПУСК ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Фильтр для ссылок
    url_filter = filters.Regex(r'^(http|https)://[^\s]+')

    # Добавление обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_chat)) 
    
    # Обработчик нажатия Inline-кнопок
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Обработчик ссылок 
    app.add_handler(MessageHandler(filters.TEXT & url_filter, handle_link_analysis))
    
    # Обработчик общего текста 
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Обработчик фото
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # !!! ОБРАБОТЧИК ОШИБОК !!!
    app.add_error_handler(error_handler)
    
    print("🤖 Бот запущен! Жду сообщений...")
    app.run_polling(poll_interval=3)

if __name__ == "__main__":
    main()