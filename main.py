import asyncio
import logging
import os
import re
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
    1: ("Сжатое изложение", "Прослушай исходный текст два раза. Передай главную мысль и все микротемы, сохрани последовательность и авторскую позицию. Используй исключение, обобщение и упрощение. Минимальный объём по демоверсии 2027 года — 70 слов."),
    2: ("Грамматическая основа", "Найди подлежащее и сказуемое в указанных предложениях или частях сложного предложения. Учитывай односоставные и безличные конструкции, составные сказуемые и случаи, когда подлежащее выражено не одним словом. Не принимай второстепенные члены за основу."),
    3: ("Характеристика предложений", "Проверь, верно ли описано строение предложения: простое или сложное, вид связи между частями, осложняющие конструкции, тип придаточного. Сначала найди грамматические основы, затем определи границы частей и средства связи."),
    4: ("Соответствие пунктуационных правил", "Соотнеси каждое пунктуационное правило с подходящим предложением. Для каждого варианта найди конструкцию, к которой относится правило: приложение, деепричастный оборот, тире между подлежащим и сказуемым и другие случаи."),
    5: ("Пунктуационный анализ", "Расставь знаки препинания и укажи все позиции, где они нужны. Найди грамматические основы, границы частей сложного предложения, однородные члены, вводные слова и обособленные обороты. Проверяй каждую запятую отдельно."),
    6: ("Орфографический анализ", "Выбери варианты, в которых объяснение написания слова верно. Недостаточно знать написание: проверь само правило, часть слова, часть речи и условия его применения. Обязательно проверяй, не подменено ли правило похожим."),
    7: ("Правописание гласных и согласных", "Вставь пропущенные буквы и укажи нужные позиции. Определи часть речи и морфему, подбери проверочное слово или примени правило чередования, приставок, суффиксов и окончаний. Не угадывай по звучанию."),
    8: ("Морфологические нормы", "Образуй правильную грамматическую форму слова. Определи начальную форму и часть речи, затем проверь норму образования формы: род, число, падеж, степень сравнения или форму глагола."),
    9: ("Связь слов в словосочетании", "Преобразуй словосочетание с одним видом подчинительной связи в требуемый вид, сохранив смысл. Различай согласование, управление и примыкание; следи за падежом зависимого слова и формой главного."),
    10: ("Понимание содержания текста", "Сверь каждое утверждение с прочитанным текстом. Отмечай не только полностью верные, но и частично искажённые высказывания. Не добавляй факты от себя и проверяй, кто, что, где и когда сделал."),
    11: ("Средства выразительности", "Определи, какое средство выразительности использовано в каждом примере. Различай метафору, сравнение, эпитет, олицетворение и другие средства. Объясняй выбор по конкретным словам и их значению в контексте."),
    12: ("Фразеологизмы", "Найди устойчивое сочетание слов с целостным значением. Проверь, можно ли понять его буквально: у фразеологизма значение обычно не равно простой сумме значений отдельных слов. Выпиши сочетание точно, без лишних слов."),
    13: ("Сочинение-рассуждение", "Выбери одно задание: 13.1, 13.2 или 13.3. Дай прямой ответ на вопрос, приведи два точных примера из текста, обязательно поясни каждый пример и сделай вывод. По демоверсии 2027 года минимальный объём — 70 слов; максимальный балл за сочинение — 8.")
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


LESSON_QUIZZES = {
    "orfo": [
        {"q":"Выбери правильное написание: «Он ___ высокий, а низкий».","opts":["невысокий","не высокий","ни высокий"],"a":1,"why":"Есть противопоставление с союзом «а»: не высокий, а низкий. Поэтому НЕ пишется раздельно."},
        {"q":"В каком варианте НЕ пишется слитно?","opts":["(не)навидеть ложь","(не) знал ответа","вовсе (не)интересный фильм"],"a":0,"why":"Слово «ненавидеть» не употребляется без НЕ, поэтому пишется слитно."}
    ],
    "n": [
        {"q":"Выбери правильный вариант: «Задача уже реше..а».","opts":["решена","решённа","решённая"],"a":0,"why":"Это краткое страдательное причастие: задача решена. В кратких страдательных причастиях пишется одна Н."},
        {"q":"В каком слове пишется НН?","opts":["ветре..ый","време..ый","ю..ый"],"a":1,"why":"В слове «временный» суффикс -ЕНН-, поэтому пишется НН."}
    ],
    "punct": [
        {"q":"Где нужна запятая?","opts":["Закончив работу ученик ушёл.","Закончив работу, ученик ушёл.","Закончив, работу ученик ушёл."],"a":1,"why":"«Закончив работу» — деепричастный оборот в начале предложения. Он отделяется запятой."},
        {"q":"В каком предложении слово является вводным?","opts":["Он говорил уверенно.","Кажется, дождь начинается.","Мне это кажется странным."],"a":1,"why":"В предложении «Кажется, дождь начинается» слово «кажется» выражает предположение и является вводным. В остальных вариантах это часть сказуемого или обстоятельственная характеристика."}
    ],
    "compress": [
        {"q":"Как называется приём сжатия, когда ряд однородных слов заменяют одним общим понятием?","opts":["Исключение","Обобщение","Упрощение"],"a":1,"why":"Обобщение заменяет перечисление общим понятием: например, «яблоки, груши, сливы» — «фрукты»."},
        {"q":"Что важно сохранить при сжатии исходного текста?","opts":["Все примеры и повторы","Только красивые выражения","Основную мысль и микротемы"],"a":2,"why":"При сжатии нужно сохранить главную мысль, все микротемы и их последовательность, убрав второстепенные детали."}
    ],
    "essay": [
        {"q":"Что обязательно должно быть после тезиса в сочинении по тексту?","opts":["Два примера из текста с пояснениями","Большой пересказ всего текста","Только личное мнение"],"a":0,"why":"Нужно привести два точных примера из текста и пояснить, как каждый подтверждает тезис."},
        {"q":"Для чего нужен вывод в сочинении?","opts":["Чтобы добавить новую тему","Чтобы подвести итог рассуждению","Чтобы повторить весь исходный текст"],"a":1,"why":"Вывод завершает рассуждение и возвращает читателя к основной мысли."}
    ]
}

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
        [InlineKeyboardButton(text="🧩 Разбор заданий", callback_data="tasks")],
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
        "Здесь можно изучать правила, решать тренировочные задания, разбирать ошибки и следить за прогрессом.\n\n"
        "Выбирай раздел 👇", reply_markup=main_kb())

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("Используй кнопки меню. Чтобы вернуться к началу, отправь /start.")

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
    await call.message.edit_text(f"📖 <b>{title}</b>\n\n{body}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📝 Решить", callback_data=f"lessonquiz:{key}:0")],[InlineKeyboardButton(text="⬅️ К темам обучения", callback_data="learn")]]))
    await call.answer()

@dp.callback_query(F.data.startswith("lessonquiz:"))
async def lesson_quiz(call: CallbackQuery):
    _, key, index = call.data.split(":")
    index = int(index)
    questions = LESSON_QUIZZES[key]
    q = questions[index]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{i+1}. {option}", callback_data=f"lessonanswer:{key}:{index}:{i}")]
        for i, option in enumerate(q["opts"])
    ] + [[InlineKeyboardButton(text="⬅️ К уроку", callback_data=f"lesson:{key}")]])
    await call.message.edit_text(
        f"📝 <b>Проверка знаний · {LESSONS[key][0]}</b>\\nВопрос {index+1} из {len(questions)}\\n\\n{q['q']}",
        reply_markup=keyboard
    )
    await call.answer()

@dp.callback_query(F.data.startswith("lessonanswer:"))
async def lesson_answer(call: CallbackQuery):
    _, key, index, option = call.data.split(":")
    index, option = int(index), int(option)
    q = LESSON_QUIZZES[key][index]
    correct = option == q["a"]
    db.execute(
        "UPDATE users SET correct=correct+?, wrong=wrong+? WHERE user_id=?",
        (int(correct), int(not correct), call.from_user.id)
    )
    db.commit()
    result = "✅ Верно!" if correct else "❌ Неверно."
    text = (
        f"{result}\\n\\n<b>Правильный ответ:</b> "
        f"{q['a']+1}. {q['opts'][q['a']]}\\n\\n"
        f"<b>Объяснение:</b> {q['why']}"
    )
    if index + 1 < len(LESSON_QUIZZES[key]):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Следующий вопрос ➡️", callback_data=f"lessonquiz:{key}:{index+1}")],
            [InlineKeyboardButton(text="⬅️ К уроку", callback_data=f"lesson:{key}")]
        ])
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Решить ещё раз", callback_data=f"lessonquiz:{key}:0")],
            [InlineKeyboardButton(text="📖 Вернуться к уроку", callback_data=f"lesson:{key}")],
            [InlineKeyboardButton(text="📊 Мой прогресс", callback_data="stats")]
        ])
    await call.message.edit_text(text, reply_markup=keyboard)
    await call.answer("Ответ сохранён")

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
        "Разбирай условие по шагам и сверяй каждый этап с правилом из конспекта.",
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
        "Используй памятки из обучения как план работы и самостоятельно проверь структуру, логику и грамотность текста.",
        reply_markup=back_kb())
    await call.answer()

@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    row=db.execute("SELECT correct,wrong FROM users WHERE user_id=?",(call.from_user.id,)).fetchone() or (0,0)
    total=row[0]+row[1]
    pct=round(row[0]/total*100) if total else 0
    await call.message.edit_text(f"📊 <b>Твой прогресс</b>\n\n✅ Верных ответов: {row[0]}\n❌ Ошибок: {row[1]}\n🎯 Точность: {pct}%\n\nПродолжай тренироваться — статистика обновляется после каждого ответа.", reply_markup=back_kb())
    await call.answer()

@dp.message(F.text)
async def text_message(message: Message):
    touch_user(message.from_user)
    await message.answer(
        "Я работаю без ИИ и отвечаю через разделы меню. Выбери «Обучение», «Практика» или «Разбор заданий» 👇",
        reply_markup=main_kb()
    )

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
