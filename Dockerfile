# Используем официальный образ Python
FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Копируем requirements.txt
COPY requirements.txt /app/

# Устанавливаем Python зависимости
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копируем весь проект
COPY . /app/

# Применяем миграции и запускаем сервер
CMD python manage.py migrate && python manage.py runserver 0.0.0.0:8000