"""
FSM states для всех диалогов бота.

Группы:
  PaymentFSM   — процесс покупки VPS
  BroadcastFSM — рассылка сообщений
  AdminFSM     — поиск и действия в админ-панели
"""
from aiogram.fsm.state import State, StatesGroup


class PaymentFSM(StatesGroup):
    """Состояния процесса покупки VPS."""
    choosing_tariff = State()    # выбор тарифа
    choosing_payment = State()   # выбор способа оплаты
    waiting_payment = State()    # инвойс создан, ждём оплаты


class BroadcastFSM(StatesGroup):
    """Рассылка: ввод текста → подтверждение → отправка."""
    waiting_text = State()
    confirming = State()


class AdminFSM(StatesGroup):
    """Поиск и действия в админ-панели."""
    find_user_by_id = State()       # ввод Telegram ID
    find_user_by_username = State() # ввод username
    find_vps_by_ip = State()        # ввод IP адреса
    send_message_to_user = State()  # личное сообщение юзеру
