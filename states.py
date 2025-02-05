from aiogram.fsm.state import State, StatesGroup

class ProfileStates(StatesGroup):
    age = State() # Состояние ожидания ввода возраста
    weight = State() # Состояние ожидания ввода веса (в кг)
    height = State() # Состояние ожидания ввода роста (в см)
    activity = State() # Состояние ожидания ввода уровня активности (минут в день)
    city = State() # Состояние ожидания ввода города (для получения температуры)


class FoodLogStates(StatesGroup):
    waiting_for_grams = State() # Состояние ожидания ввода количества съеденных граммов