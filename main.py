import asyncio
import logging
import os
import re
import html
import sqlite3
from datetime import datetime, timezone

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ogenius")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "ogenius.sqlite3")

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения Render")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
    correct INTEGER NOT NULL DEFAULT 0, wrong INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
)""")
db.commit()

TASKS = {
    1: ("Сжатое изложение", "Как выделять микротемы, находить главную мысль и применять три приёма сжатия: исключение, обобщение и упрощение."),
    2: ("Синтаксический анализ", "Учимся находить грамматические основы, виды сказуемого, односоставные и осложнённые предложения. Всегда сначала ищи грамматическую основу."),
    3: ("Пунктуационный анализ", "Разбираем запятые при однородных членах, вводных словах, обращениях, причастных и деепричастных оборотах, сложных предложениях."),
    4: ("Пунктуационный анализ", "Определи грамматические основы и границы частей. Проверь союзы, вводные конструкции и обособленные обороты."),
    5: ("Орфографический анализ", "Проверяем написание приставок, корней, суффиксов, окончаний, Н/НН, НЕ/НИ и слитное, раздельное, дефисное написание."),
    6: ("Анализ содержания текста", "Ищи ответ в самом тексте. Не добавляй сведения, которых автор не сообщал. Сверяй каждую часть утверждения."),
    7: ("Средства выразительности", "Различаем эпитет, метафору, сравнение, олицетворение, фразеологизм, гиперболу и другие средства."),
    8: ("Лексический анализ", "Определяем значение слова по контексту, подбираем синонимы и антонимы, различаем прямое и переносное значение."),
    9: ("Анализ языковых явлений", "Внимательно определи, какое языковое явление проверяется в формулировке. Найди нужный фрагмент, примени правило и проверь, что ответ соответствует всем условиям."),
    10: ("Грамматические нормы", "Разбираем формы слов, согласование, управление, построение словосочетаний и предложений."),
    11: ("Речевые нормы", "Убираем речевую избыточность, повторы, неправильное употребление слов и нарушения сочетаемости."),
    12: ("Комплексный анализ", "Проверь, что именно требуется найти или объяснить. Сопоставь условие с текстом, выпиши языковые признаки и обоснуй выбор. Номер и формулировку сверяй с демоверсией своего года."),
    13: ("Сочинение-рассуждение", "Структура: ответ на вопрос темы, два примера из текста с пояснениями, логичная связь между ними и вывод. Следи за объёмом, точностью примеров и критериями текущего года."),
}

LESSONS = {
    "orfo": ("Орфография: НЕ и НИ", """**НЕ с существительными, прилагательными и наречиями на -О**
• Слитно, если слово можно заменить синонимом без НЕ: невысокий = низкий.
• Раздельно при противопоставлении с А: не высокий, а низкий.
• Раздельно с усилителями отрицания: вовсе не, далеко не, ничуть не.

**НЕ с глаголами и деепричастиями** обычно раздельно: не знал, не заметив. Исключения: слова, которые без НЕ не употребляются (ненавидеть).

**НИ** усиливает отрицание: не сказал ни слова. В конструкции «кто ни…» часто имеет уступительное значение: кто ни придёт, всем рады.

**Алгоритм:** определи часть речи → найди зависимые слова и противопоставление → проверь, употребляется ли слово без НЕ."""),
    "n": ("Н и НН", """**В прилагательных**
• НН часто пишется на стыке основы и суффикса: сон + н → сонный.
• Суффиксы -ОНН-, -ЕНН- обычно дают НН: традиционный, временный.
• Исключения и особые слова нужно запоминать: ветреный, но безветренный.

**В причастиях**
Полная форма страдательного причастия обычно имеет НН: решённая задача.
Краткое страдательное причастие — одна Н: задача решена.

**Порядок:** определи часть речи → найди суффикс → проверь зависимые слова, приставку и краткую форму."""),
    "punct": ("Запятые при оборотах", """**Причастный оборот** — причастие с зависимыми словами. После определяемого слова обычно обособляется: Дом, построенный у реки, был красив.

**Деепричастный оборот** обычно выделяется запятыми: Закончив работу, ученик ушёл.

**Вводные слова** выражают отношение говорящего: конечно, вероятно, к счастью. Они выделяются запятыми. Не путай их с членами предложения: «Он говорил уверенно» — уверенно не вводное слово.

**Алгоритм:** найди грамматическую основу → определи оборот → найди определяемое слово или границы конструкции."""),
    "essay": ("Сочинение-рассуждение", """Универсальный план:
1. **Ответ на вопрос темы** — сформулируй тезис своими словами.
2. **Первый пример из текста** — укажи конкретный эпизод/факт и объясни, как он подтверждает тезис.
3. **Второй пример из текста** — приведи другой эпизод и поясни его.
4. **Вывод** — коротко вернись к основной мысли.

Не пересказывай весь текст. Каждый пример должен работать на тезис. Проверяй абзацы, связки, фактическую точность и объём по актуальным критериям ФИПИ."""),
    "compress": ("Сжатое изложение", """Три приёма сжатия:
• **Исключение:** убираем повторы, уточнения, примеры и детали, без которых смысл сохраняется.
• **Обобщение:** заменяем ряд однородных понятий одним общим.
• **Упрощение:** объединяем сложные конструкции, заменяем фрагмент более короткой формулировкой.

Порядок работы:
1. При первом прослушивании пойми тему и основную мысль.
2. При втором запиши ключевые слова каждой микротемы.
3. Составь план из трёх микротем.
4. Сожми каждую часть, сохранив важные мысли и последовательность.
5. Проверь связность и объём."""),
}

QUIZ = [
    {"q":"В каком слове на месте пропуска пишется НН?","opts":["ветре..ый день","серебря..ая ложка","решё..ая задача","ю..ый художник"],"a":2,"why":"«Решённая» — полное страдательное причастие прошедшего времени; пишется НН. В краткой форме было бы: задача решена."},
    {"q":"Укажи вводное слово.","opts":["кажется, дождь начинается","он кажется усталым","мне это кажется странным","лицо кажется знакомым"],"a":0,"why":"В первом предложении «кажется» можно убрать без разрушения грамматической основы: это вводное слово. В остальных случаях это сказуемое."},
    {"q":"В каком предложении нужна запятая при деепричастном обороте?","opts":["Он шёл не спеша.","Улыбаясь девочка вошла в комнату.","Снег блестел на солнце.","Мы решили отдохнуть."],"a":1,"why":"«Улыбаясь» — деепричастие, обозначает добавочное действие. Оборот в начале предложения отделяется запятой: «Улыбаясь, девочка вошла…»."},
    {"q":"Выбери правильное написание.","opts":["не смотря на дождь","несмотря на дождь","не смотря, на дождь","ни смотря на дождь"],"a":1,"why":"«Несмотря на» в значении «вопреки» — производный предлог, пишется слитно."},
    {"q":"Какой приём сжатия заменяет несколько однородных понятий одним общим?","opts":["Исключение","Обобщение","Упрощение","Цитирование"],"a":1,"why":"При обобщении ряд однородных слов заменяется общим понятием: «яблоки, груши, сливы» → «фрукты»."},
    {"q":"В каком варианте грамматическая основа указана верно: «Вечером быстро стемнело»?","opts":["вечером стемнело","быстро стемнело","стемнело","вечером быстро"],"a":2,"why":"«Стемнело» — главный член безличного предложения. Слова «вечером» и «быстро» — обстоятельства."}
]

def touch_user(user):
    db.execute("""INSERT INTO users(user_id, username, first_name, created_at)
        VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
        username=excluded.username, first_name=excluded.first_name""",
        (user.id, user.username, user.first_name, datetime.now(timezone.utc).isoformat()))
    db.commit()

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Обучение", callback_data="learn"),
         InlineKeyboardButton(text="✍️ Практика", callback_data="practice")],
        [InlineKeyboardButton(text="🧩 Разбор заданий", callback_data="tasks"),
         InlineKeyboardButton(text="🤖 ИИ-репетитор", callback_data="tutor")],
        [InlineKeyboardButton(text="📝 Изложение и сочинение", callback_data="writing"),
         InlineKeyboardButton(text="📊 Мой прогресс", callback_data="stats")],
        [InlineKeyboardButton(text="🔗 Материалы ФИПИ", url="https://fipi.ru/oge/demoversii-specifikacii-kodifikatory")]
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="home")]])

def task_kb():
    rows=[]
    for n in range(1,14):
        title=TASKS[n][0]
        rows.append([InlineKeyboardButton(text=f"№{n} · {title}", callback_data=f"task:{n}")])
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def learn_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="НЕ и НИ", callback_data="lesson:orfo"),
         InlineKeyboardButton(text="Н и НН", callback_data="lesson:n")],
        [InlineKeyboardButton(text="Запятые и обороты", callback_data="lesson:punct")],
        [InlineKeyboardButton(text="Сжатое изложение", callback_data="lesson:compress"),
         InlineKeyboardButton(text="Сочинение", callback_data="lesson:essay")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="home")]
    ])

def quiz_kb(index):
    q=QUIZ[index]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{i+1}. {v}", callback_data=f"answer:{index}:{i}")]
        for i,v in enumerate(q["opts"])
    ] + [[InlineKeyboardButton(text="⬅️ В меню", callback_data="home")]])

@dp.message(CommandStart())
async def start(message: Message):
    touch_user(message.from_user)
    await message.answer(
        f"Привет, {message.from_user.first_name or 'ученик'}! 👋\n\n"
        "<b>OGENIUS</b> — твой помощник в подготовке к ОГЭ по русскому языку.\n\n"
        "Здесь можно изучать правила, решать тренировочные задания, разбирать ошибки и задавать вопросы репетитору.\n\n"
        "Выбирай раздел 👇", reply_markup=main_kb())

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("Используй кнопки меню. Чтобы вернуться к началу, отправь /start.\n"
                         "Для ИИ-репетитора отправь вопрос обычным сообщением после нажатия кнопки «ИИ-репетитор».")

@dp.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.message.edit_text("🏠 <b>Главное меню OGENIUS</b>\nВыбирай, чем займёмся:", reply_markup=main_kb())
    await call.answer()

@dp.callback_query(F.data == "learn")
async def learn(call: CallbackQuery):
    await call.message.edit_text("📚 <b>Обучение</b>\nВыбери тему. В каждом конспекте — правило и алгоритм применения.", reply_markup=learn_kb())
    await call.answer()

@dp.callback_query(F.data.startswith("lesson:"))
async def lesson(call: CallbackQuery):
    key=call.data.split(":",1)[1]
    title,body=LESSONS[key]
        body = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", body, flags=re.S)
    await call.message.edit_text(f"📖 <b>{title}</b>\n\n{body}", reply_markup=back_kb())
    await call.answer()

@dp.callback_query(F.data == "tasks")
async def tasks(call: CallbackQuery):
    await call.message.edit_text("🧩 <b>Разбор заданий</b>\nВыбери номер. Бот объяснит, на что обращать внимание и с чего начинать решение.", reply_markup=task_kb())
    await call.answer()

@dp.callback_query(F.data.startswith("task:"))
async def task(call: CallbackQuery):
    n=int(call.data.split(":")[1])
    title,desc=TASKS[n]
    await call.message.edit_text(f"🧩 <b>Задание №{n}: {title}</b>\n\n{desc}\n\n"
        "💡 <b>Как разбирать:</b> сначала внимательно прочитай условие, затем выдели ключевые слова, выполни нужное действие и только после этого записывай ответ. "
        "Если пришлёшь конкретное условие или фото задания, репетитор поможет разобрать его по шагам.",
        reply_markup=back_kb())
    await call.answer()

@dp.callback_query(F.data == "practice")
async def practice(call: CallbackQuery):
    await call.message.edit_text("✍️ <b>Практика</b>\nНебольшая тренировка из 6 вопросов. После ответа покажу правильный вариант и объяснение.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать тренировку", callback_data="quiz:0")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="home")]
    ]))
    await call.answer()

@dp.callback_query(F.data.startswith("quiz:"))
async def quiz(call: CallbackQuery):
    index=int(call.data.split(":")[1])
    await call.message.edit_text(f"✍️ <b>Вопрос {index+1} из {len(QUIZ)}</b>\n\n{QUIZ[index]['q']}", reply_markup=quiz_kb(index))
    await call.answer()

@dp.callback_query(F.data.startswith("answer:"))
async def answer(call: CallbackQuery):
    _,idx,opt=call.data.split(":")
    idx,opt=int(idx),int(opt)
    q=QUIZ[idx]
    good=opt==q["a"]
    col="✅ Верно!" if good else "❌ Пока неверно."
    db.execute("UPDATE users SET correct=correct+?, wrong=wrong+? WHERE user_id=?",
               (int(good),int(not good),call.from_user.id))
    db.commit()
    explanation=f"{col}\n\n<b>Правильный ответ:</b> {q['a']+1}. {q['opts'][q['a']]}\n\n<b>Разбор:</b> {q['why']}"
    if idx+1<len(QUIZ):
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Следующий вопрос ➡️", callback_data=f"quiz:{idx+1}")],[InlineKeyboardButton(text="В меню", callback_data="home")]])
    else:
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔁 Пройти ещё раз", callback_data="quiz:0")],[InlineKeyboardButton(text="📊 Мой прогресс", callback_data="stats")],[InlineKeyboardButton(text="В меню", callback_data="home")]])
    await call.message.edit_text(explanation, reply_markup=kb)
    await call.answer("Ответ принят")

@dp.callback_query(F.data == "writing")
async def writing(call: CallbackQuery):
    await call.message.edit_text("📝 <b>Изложение и сочинение</b>\n\n"
        "В разделе обучения есть пошаговые памятки по сжатому изложению и сочинению-рассуждению. "
        "Можешь прислать свой текст следующим сообщением — ИИ-репетитор проверит его, если подключён ИИ-ключ.",
        reply_markup=back_kb())
    await call.answer()

@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    row=db.execute("SELECT correct,wrong FROM users WHERE user_id=?",(call.from_user.id,)).fetchone() or (0,0)
    total=row[0]+row[1]
    pct=round(row[0]/total*100) if total else 0
    await call.message.edit_text(f"📊 <b>Твой прогресс</b>\n\n✅ Верных ответов: {row[0]}\n❌ Ошибок: {row[1]}\n🎯 Точность: {pct}%\n\nПродолжай тренироваться — статистика обновляется после каждого ответа.", reply_markup=back_kb())
    await call.answer()

@dp.callback_query(F.data == "tutor")
async def tutor(call: CallbackQuery):
    await call.message.edit_text("🤖 <b>ИИ-репетитор OGENIUS</b>\n\nНапиши вопрос по русскому языку, пришли условие задания или свой вариант сочинения. Я объясню решение по шагам.\n\n"
        + ("ИИ подключён. Можешь задавать вопрос сообщением." if OPENAI_API_KEY else "⚠️ ИИ пока не подключён: для него нужно добавить OPENAI_API_KEY в Render → Environment. Пока доступны уроки и тренировки."),
        reply_markup=back_kb())
    await call.answer()

async def ask_ai(text: str) -> str:
    system = ("Ты — доброжелательный и точный репетитор по русскому языку для подготовки к ОГЭ. "
              "Отвечай на русском. Объясняй пошагово: 1) что требуется, 2) правило, 3) ход решения, "
              "4) ответ, 5) почему другие варианты неверны (если есть). Не выдумывай критерии ФИПИ. "
              "Если просят проверить сочинение или изложение, оцени структуру, аргументацию, логику, грамотность и объём; "
              "отделяй предварительную учебную оценку от официальной оценки эксперта. Если условие неполное — попроси его прислать.")
    headers={"Authorization":f"Bearer {OPENAI_API_KEY}","Content-Type":"application/json"}
    payload={"model":AI_MODEL,"messages":[{"role":"system","content":system},{"role":"user","content":text}],"temperature":0.3}
    timeout=aiohttp.ClientTimeout(total=75)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(f"{AI_BASE_URL}/chat/completions",headers=headers,json=payload) as resp:
            data=await resp.json()
            if resp.status>=400:
                log.error("AI API error: %s", data)
                return "Не удалось получить ответ ИИ. Проверьте настройки API-ключа и модели в Render."
            return data["choices"][0]["message"]["content"].strip()

@dp.message(F.text)
async def text_message(message: Message):
    touch_user(message.from_user)
    if not OPENAI_API_KEY:
        await message.answer("Я получил сообщение! 🤝\n\nЧтобы включить подробные ответы ИИ, добавьте OPENAI_API_KEY в Render → Environment. "
                             "А пока загляни в «Обучение» или «Практика».", reply_markup=main_kb())
        return
    status=await message.answer("🤔 Разбираю вопрос…")
    try:
        result=await ask_ai(message.text)
        # Telegram message limit is 4096 characters.
        for start in range(0,len(result),3900):
            part=html.escape(result[start:start+3900])
            if start==0:
                await status.edit_text(part)
            else:
                await message.answer(part)
    except Exception:
        log.exception("AI request failed")
        await status.edit_text("Произошла ошибка при обращении к ИИ. Попробуй ещё раз позже.")

async def health(request):
    return web.json_response({"status":"ok","service":"OGENIUS","time":datetime.now(timezone.utc).isoformat()})

async def run_web():
    app=web.Application()
    app.router.add_get("/",health)
    app.router.add_get("/health",health)
    runner=web.AppRunner(app)
    await runner.setup()
    site=web.TCPSite(runner,"0.0.0.0",PORT)
    await site.start()
    log.info("Health server listening on port %s",PORT)
    return runner

async def main():
    runner=await run_web()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("OGENIUS bot polling started")
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()
        db.close()

if __name__=="__main__":
    asyncio.run(main())
