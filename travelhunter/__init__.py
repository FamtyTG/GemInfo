"""TravelHunter — Telegram-бот для подбора путешествий выходного дня.

Проект построен на трёхслойной архитектуре:

    presentation  — слой представления (экраны бота, клавиатуры, тексты);
    domain        — слой бизнес-логики (сущности, сервисы, интерфейсы);
    infrastructure— слой доступа к данным (PostgreSQL через SQLAlchemy,
                    внешние API: Ninjas, GeoNames, Wikipedia).

Зависимости направлены только внутрь: presentation -> domain <- infrastructure.
"""

__version__ = "1.0.0"
__project__ = "TravelHunter"
