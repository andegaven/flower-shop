# Flowermag - онлайн-магазин цветов и букетов

**Архитектура проекта:** микросервисная архитектура

**Сервисы:**

```
auth_service - сервис пользователей
gateway - сервис, работающий в роли шлюза
notification_service - сервис нотификаций
order_service - сервис заказов
products_service - сервис товаров
```

**Запуск проекта:**

```
pyhton -m fastapi dev gateway/main.py
```

**Используемые сервисы и инструменты:**

- VSCode
- PyCharm
- Docker
- RabbitMQ
- MySQL
- Бэкенд: язык программирования Python с использованием модуля FastAPI и SQLAlchemy
- Фронтенд: HTML и CSS

Структура проекта:

```
.
├── auth_service/
│   ├── auth_service.py
│   ├── requirements.txt
│   └── test_auth_service.py
├── gateway/
│   ├── config.py
│   ├── dependencies.py
│   ├── main.py
│   └── requirements.txt
├── notitfication_service/
│   ├── notif_service.py
│   └── requirements.txt
├── order/
│   ├── order_service.py
│   └── requirements.txt
├── products/
│   ├── Products.py
│   └── requirements.txt
├── static/
│   ├── flooo/
│   ├── images/
│   ├── cart.html
│   ├── catalog.html
│   ├── contructor.html
│   ├── index.html
│   ├── profile.html
│   ├── registration_list.html
│   ├── ss.html
│   ├── sss.html
│   └── styles.css
└── .gitignore
```
