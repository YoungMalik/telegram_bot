import logging
import requests
import datetime
import io
import matplotlib.pyplot as plt

from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, MessageAutoDeleteTimerChanged, InputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from pyexpat.errors import messages

from states import ProfileStates, FoodLogStates
from config import API
import aiohttp

# Настройка логирования для отладки (опционально)
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

router = Router()

# Глобальный словарь для хранения данных о пользователях.
# Структура:
# users = {
#    user_id: {
#        "weight": ...,
#        "height": ...,
#        "age": ...,
#        "activity": ...,
#        "city": ...,
#        "water_goal": ...,
#        "calorie_goal": ...,
#        "logged_water": 0,
#        "logged_calories": 0,
#        "burned_calories": 0
#    }
# }
users = {}

# Глобальный словарь для хранения истории прогресса.
# Структура:
# progress_history = {
#    user_id: {
#         "time": [datetime, ...],
#         "water": [logged_water, ...],
#         "calories": [logged_calories, ...],
#         "burned": [burned_calories, ...]
#    }
# }
progress_history = {}


def update_history(user_id):
    """Обновляет историю прогресса для пользователя."""
    now = datetime.datetime.now()
    if user_id not in progress_history:
        progress_history[user_id] = {"time": [], "water": [], "calories": [], "burned": []}
    progress_history[user_id]["time"].append(now)
    progress_history[user_id]["water"].append(users[user_id]["logged_water"])
    progress_history[user_id]["calories"].append(users[user_id]["logged_calories"])
    progress_history[user_id]["burned"].append(users[user_id]["burned_calories"])


##############################
# Функция для поиска информации о продукте по OpenFoodFacts
##############################

def get_food_info(product_name):
    url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={product_name}&json=true"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        products = data.get('products', [])
        if products:  # Проверяем, есть ли найденные продукты
            first_product = products[0]
            return {
                'name': first_product.get('product_name', 'Неизвестно'),
                'calories': first_product.get('nutriments', {}).get('energy-kcal_100g', 0)
            }
        return None
    print(f"Ошибка: {response.status_code}")
    return None


############################
# Обработчики команд
############################

# Команда /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("Добро пожаловать! Я Ваш бот.\nВведите /help для списка команд.")


# Команда /help
@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.reply(
        "Доступные команды:\n"
        "/start - Начало работы\n"
        "/help - Список команд\n"
        "/set_profile - Заполнение профиля пользователя\n"
        "/log_water <количество> - Логирование воды\n"
        "/log_food <название продукта> - Логирование съеденной еды\n"
        "/log_burned <количество> - Логирование сожжённых ккал\n"
        "/log_workout <тип тренировки> <время (мин)> - Логирование тренировки\n"
        "/check_progress - Показать прогресс по воде и калориям\n"
        "/graph_progress - Показать графики прогресса"
    )


#########################
# FSM: Диалог заполнения профиля
#########################

@router.message(Command("set_profile"))
async def start_profile(message: Message, state: FSMContext):
    """
    Обработчик команды /set_profile. Запускает процесс заполнения профиля.
    """
    await message.reply("Введите Ваш вес (в кг):")
    await state.set_state(ProfileStates.weight)


@router.message(ProfileStates.weight)
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text)
        await state.update_data(weight=weight)
    except ValueError:
        await message.reply("Пожалуйста, введите число для веса.")
        return
    await message.reply("Введите Ваш рост (в см):")
    await state.set_state(ProfileStates.height)


@router.message(ProfileStates.height)
async def process_height(message: Message, state: FSMContext):
    try:
        height = float(message.text)
        await state.update_data(height=height)
    except ValueError:
        await message.reply("Пожалуйста, введите число для роста.")
        return
    await message.reply("Введите Ваш возраст:")
    await state.set_state(ProfileStates.age)


@router.message(ProfileStates.age)
async def process_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        await state.update_data(age=age)
    except ValueError:
        await message.reply("Пожалуйста, введите число для возраста.")
        return
    await message.reply("Введите уровень Вашей активности (минуты в день):")
    await state.set_state(ProfileStates.activity)


@router.message(ProfileStates.activity)
async def process_activity(message: Message, state: FSMContext):
    try:
        activity = int(message.text)
        await state.update_data(activity=activity)
    except ValueError:
        await message.reply("Пожалуйста, введите число для уровня активности.")
        return
    await message.reply("Введите Ваш город (для получения температуры):")
    await state.set_state(ProfileStates.city)


@router.message(ProfileStates.city)
async def process_city(message: Message, state: FSMContext):
    data = await state.get_data()
    weight = data.get("weight")
    height = data.get("height")
    age = data.get("age")
    activity = data.get("activity")
    city = message.text

    # Расчёт нормы воды
    base_norm = weight * 30
    activity_bonus_water = (activity // 30) * 500
    additional_water = 0

    weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={API}&units=metric"
    try:
        response = requests.get(weather_url)
        weather_data = response.json()
        if weather_data.get("main"):
            temp = weather_data["main"]["temp"]
            if temp > 25:
                additional_water = 1000 if temp > 30 else 500
        else:
            await message.reply("Не удалось получить данные о погоде. Дополнительная вода не будет добавлена.")
    except Exception:
        await message.reply("Ошибка при получении данных о погоде. Дополнительная вода не будет добавлена.")

    water_goal = int(base_norm + activity_bonus_water + additional_water)

    # Расчёт нормы калорий
    calorie_base = 10 * weight + 6.25 * height - 5 * age
    if activity < 30:
        activity_bonus_calories = 200
    elif activity <= 60:
        activity_bonus_calories = 300
    else:
        activity_bonus_calories = 400
    calorie_goal = int(calorie_base + activity_bonus_calories)

    reply_text = (
        f"Ваши параметры:\n"
        f"Вес: {weight} кг\n"
        f"Рост: {height} см\n"
        f"Возраст: {age} лет\n"
        f"Активность: {activity} минут в день\n"
        f"Город: {city}\n\n"
        f"Рассчитанная дневная норма:\n"
        f"Воды: {water_goal} мл\n"
        f"Калорий: {calorie_goal} ккал"
    )
    if 'temp' in locals():
        reply_text += f"\nПогода в {city}: {temp}°C"

    await message.reply(reply_text)

    users[message.from_user.id] = {
        "weight": weight,
        "height": height,
        "age": age,
        "activity": activity,
        "city": city,
        "water_goal": water_goal,
        "calorie_goal": calorie_goal,
        "logged_water": 0,
        "logged_calories": 0,
        "burned_calories": 0
    }
    update_history(message.from_user.id)
    await state.clear()


#########################
# Логирование воды
#########################

@router.message(Command("log_water"))
async def cmd_log_water(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: /log_water <количество>")
        return
    try:
        amount = int(parts[1])
    except ValueError:
        await message.reply("Пожалуйста, укажите число после команды /log_water")
        return

    user_id = message.from_user.id
    if user_id not in users:
        await message.reply("Сначала заполните профиль командой /set_profile.")
        return

    users[user_id]["logged_water"] += amount
    update_history(user_id)

    water_goal = users[user_id]["water_goal"]
    logged_water = users[user_id]["logged_water"]
    remaining = water_goal - logged_water if water_goal > logged_water else 0

    await message.reply(
        f"Вода:\n- Выпито: {logged_water} мл из {water_goal} мл.\n- Осталось: {remaining} мл."
    )


#########################
# Логирование еды
#########################

@router.message(Command("log_food"))
async def cmd_log_food(message: Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: /log_food <название продукта>")
        return
    product_name = parts[1]
    food_info = get_food_info(product_name)
    if not food_info:
        await message.reply("Не удалось найти информацию о данном продукте.")
        return

    reply = f"🍽 {food_info['name']} — {food_info['calories']} ккал на 100 г. Сколько грамм вы съели?"
    await message.reply(reply)
    await state.update_data(food_info=food_info)
    await state.set_state(FoodLogStates.waiting_for_grams)


@router.message(FoodLogStates.waiting_for_grams)
async def process_food_quantity(message: Message, state: FSMContext):
    try:
        grams = float(message.text)
    except ValueError:
        await message.reply("Пожалуйста, введите число, обозначающее количество граммов.")
        return

    data = await state.get_data()
    food_info = data.get('food_info')
    if not food_info:
        await message.reply("Ошибка: информация о продукте не найдена. Попробуйте снова.")
        await state.clear()
        return

    kcal_per_100 = food_info['calories']
    total_cal = grams * kcal_per_100 / 100

    user_id = message.from_user.id
    if user_id not in users:
        await message.reply("Сначала заполните профиль командой /set_profile.")
        await state.clear()
        return

    users[user_id]["logged_calories"] += total_cal
    update_history(user_id)

    await message.reply(f"Записано: {total_cal:.1f} ккал.")
    await state.clear()


#########################
# Логирование сожжённых калорий
#########################

@router.message(Command("log_burned"))
async def cmd_log_burned(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: /log_burned <количество>")
        return
    try:
        amount = float(parts[1])
    except ValueError:
        await message.reply("Пожалуйста, введите число после команды /log_burned")
        return

    user_id = message.from_user.id
    if user_id not in users:
        await message.reply("Сначала заполните профиль командой /set_profile.")
        return

    users[user_id]["burned_calories"] += amount
    update_history(user_id)
    await message.reply(f"Записано: сожжено {users[user_id]['burned_calories']} ккал.")


#########################
# Логирование тренировок
#########################

@router.message(Command("log_workout"))
async def cmd_log_workout(message: Message):
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("Использование: /log_workout <тип тренировки> <время (мин)>")
        return

    workout_type = parts[1]
    try:
        time_min = int(parts[2])
    except ValueError:
        await message.reply("Пожалуйста, введите число для времени тренировки.")
        return

    coefficients = {
        "бег": 10,
        "силовая": 8,
        "плавание": 11,
        "йога": 4
    }
    coef = coefficients.get(workout_type.lower(), 10)
    burned = time_min * coef

    user_id = message.from_user.id
    if user_id not in users:
        await message.reply("Сначала заполните профиль командой /set_profile.")
        return

    users[user_id]["burned_calories"] += burned
    update_history(user_id)

    extra_water = (time_min // 30) * 200
    reply_text = f"🏃‍♂️ {workout_type.capitalize()} {time_min} минут — {burned} ккал."
    if extra_water > 0:
        reply_text += f" Дополнительно: выпейте {extra_water} мл воды."
    await message.reply(reply_text)


#########################
# Проверка прогресса по воде и калориям
#########################

@router.message(Command("check_progress"))
async def cmd_check_progress(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.reply("Сначала заполните профиль командой /set_profile.")
        return

    user_data = users[user_id]
    water_goal = user_data["water_goal"]
    logged_water = user_data["logged_water"]
    remaining = water_goal - logged_water if water_goal > logged_water else 0

    calorie_goal = user_data["calorie_goal"]
    logged_calories = user_data["logged_calories"]
    burned_calories = user_data["burned_calories"]
    balance = logged_calories - burned_calories

    reply_text = (
        "📊 Прогресс:\n\n"
        "Вода:\n"
        f"- Выпито: {logged_water} мл из {water_goal} мл.\n"
        f"- Осталось: {remaining} мл.\n\n"
        "Калории:\n"
        f"- Потреблено: {logged_calories:.1f} ккал из {calorie_goal} ккал.\n"
        f"- Сожжено: {burned_calories:.1f} ккал.\n"
        f"- Баланс: {balance:.1f} ккал."
    )
    await message.reply(reply_text)


#########################
# Построение графиков прогресса
#########################

@router.message(Command("graph_progress"))
async def cmd_graph_progress(message: Message):
    user_id = message.from_user.id
    if user_id not in progress_history or len(progress_history[user_id]["time"]) < 2:
        await message.reply("Недостаточно данных для построения графиков. Попробуйте позже.")
        return

    times = progress_history[user_id]["time"]
    water = progress_history[user_id]["water"]
    calories = progress_history[user_id]["calories"]
    burned = progress_history[user_id]["burned"]
    net_cal = [cal - br for cal, br in zip(calories, burned)]

    fig, axs = plt.subplots(2, 1, figsize=(8, 10))

    axs[0].plot(times, water, marker='o')
    axs[0].set_title("Прогресс по воде")
    axs[0].set_xlabel("Время")
    axs[0].set_ylabel("Выпито воды (мл)")
    axs[0].grid(True)

    axs[1].plot(times, calories, label="Потреблено", marker='o')
    axs[1].plot(times, burned, label="Сожжено", marker='o')
    axs[1].plot(times, net_cal, label="Баланс", marker='o')
    axs[1].set_title("Прогресс по калориям")
    axs[1].set_xlabel("Время")
    axs[1].set_ylabel("Калории")
    axs[1].legend()
    axs[1].grid(True)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    photo = InputFile(buf, filename="progress.png")
    await message.answer_photo(photo, caption="Графики прогресса по воде и калориям")
    plt.close(fig)


#########################
# Функция для подключения обработчиков
#########################

def setup_handlers(dp):
    dp.include_router(router)