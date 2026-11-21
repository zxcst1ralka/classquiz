# Запуск на сервере

Инструкция для обычного VPS с Ubuntu 22.04 или 24.04 (сервер, домен и доступ по SSH нужны заранее).
Схема: **nginx** принимает запросы и отдаёт статику, **gunicorn** запускает Django, **PostgreSQL** хранит данные.

> Инструкция составлена по документации и проверена в части настроек проекта (`check --deploy`, тесты).
> На живом сервере она не прогонялась, поэтому при первом запуске сверяйтесь с выводом команд.

## 1. Подготовка сервера

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git nginx postgresql postgresql-client certbot python3-certbot-nginx
```

База и пользователь PostgreSQL:

```bash
sudo -u postgres psql
CREATE USER classquiz WITH PASSWORD 'придумайте-пароль';
CREATE DATABASE classquiz OWNER classquiz;
\q
```

## 2. Код проекта

```bash
sudo mkdir -p /srv/classquiz && sudo chown $USER /srv/classquiz
git clone https://github.com/zxcst1ralka/classquiz.git /srv/classquiz
cd /srv/classquiz
python3 -m venv venv
venv/bin/pip install -r requirements.txt -r requirements-prod.txt
```

## 3. Настройки (.env)

```bash
cp .env.example .env
nano .env
```

Заполните `DJANGO_SECRET_KEY` (команда для генерации написана в файле), адрес сайта и пароль базы.
Пока нет HTTPS, поставьте `DJANGO_SSL_REDIRECT=0`.

## 4. База и статика

```bash
venv/bin/python manage.py migrate
venv/bin/python manage.py createsuperuser
venv/bin/python manage.py collectstatic --noinput
venv/bin/python manage.py check --deploy
```

## 5. gunicorn как служба

Файл `/etc/systemd/system/classquiz.service`:

```ini
[Unit]
Description=ClassQuiz
After=network.target postgresql.service

[Service]
User=www-data
WorkingDirectory=/srv/classquiz
ExecStart=/srv/classquiz/venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo chown -R www-data /srv/classquiz
sudo systemctl daemon-reload
sudo systemctl enable --now classquiz
```

## 6. nginx

Файл `/etc/nginx/sites-available/classquiz` (замените `example.ru` на свой домен):

```nginx
server {
    listen 80;
    server_name example.ru www.example.ru;

    location /static/ {
        alias /srv/classquiz/staticfiles/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/classquiz /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d example.ru -d www.example.ru     # HTTPS
```

После выпуска сертификата проверьте, что в `.env` стоит `DJANGO_SSL_REDIRECT=1`, и перезапустите службу:
`sudo systemctl restart classquiz`.

## 7. Ежедневное резервное копирование

Команда `backup_db` сама определяет, SQLite или PostgreSQL используется (для PostgreSQL нужен `pg_dump`,
он ставится вместе с `postgresql-client`). Добавьте в cron пользователя `www-data`
(`sudo crontab -u www-data -e`):

```
0 3 * * * cd /srv/classquiz && venv/bin/python manage.py backup_db
```

Копии лежат в `/srv/classquiz/backups/`, хранятся последние 30. Раз в неделю скачивайте их к себе
или копируйте в облачное хранилище: резервная копия на том же сервере не спасёт, если пропадёт сам сервер.

## 8. Обновление сайта

```bash
cd /srv/classquiz
git pull
venv/bin/pip install -r requirements.txt -r requirements-prod.txt
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart classquiz
```
