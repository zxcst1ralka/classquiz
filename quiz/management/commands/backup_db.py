import gzip
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Делает резервную копию базы данных (SQLite или PostgreSQL), сжимает её и удаляет старые копии.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep', type=int, default=30,
            help='Сколько последних копий хранить (по умолчанию 30, то есть примерно месяц ежедневных копий).',
        )

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        backup_dir = Path(getattr(settings, 'BACKUP_DIR', settings.BASE_DIR / 'backups'))
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

        if 'sqlite3' in db['ENGINE']:
            result_path = self._backup_sqlite(db, backup_dir, stamp)
        elif 'postgresql' in db['ENGINE']:
            result_path = self._backup_postgres(db, backup_dir, stamp)
        else:
            raise CommandError('Команда умеет копировать только SQLite и PostgreSQL.')

        # Удаляем самые старые копии, оставляем последние --keep штук
        keep = options['keep']
        copies = sorted(backup_dir.glob('db-*.gz'))
        removed = 0
        for old in (copies[:-keep] if keep > 0 else []):
            old.unlink()
            removed += 1

        size_kb = result_path.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(f'Резервная копия создана: {result_path} ({size_kb:.0f} КБ)'))
        if removed:
            self.stdout.write(f'Удалено старых копий: {removed}')

    def _backup_sqlite(self, db, backup_dir, stamp):
        source_path = Path(db['NAME'])
        if not source_path.exists():
            raise CommandError(f'Файл базы не найден: {source_path}')

        raw_path = backup_dir / f'db-{stamp}.sqlite3'
        gz_path = backup_dir / f'db-{stamp}.sqlite3.gz'

        # Встроенный механизм SQLite делает целостную копию, даже если сайт в это время работает
        source = sqlite3.connect(source_path)
        target = sqlite3.connect(raw_path)
        try:
            with target:
                source.backup(target)
        finally:
            target.close()
            source.close()

        with open(raw_path, 'rb') as f_in, gzip.open(gz_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
        raw_path.unlink()
        return gz_path

    def _backup_postgres(self, db, backup_dir, stamp):
        gz_path = backup_dir / f'db-{stamp}.sql.gz'
        env = os.environ.copy()
        if db.get('PASSWORD'):
            env['PGPASSWORD'] = db['PASSWORD']
        command = [
            'pg_dump',
            '-h', db.get('HOST') or 'localhost',
            '-p', str(db.get('PORT') or 5432),
            '-U', db.get('USER') or 'postgres',
            '-d', db['NAME'],
            '--no-owner', '--no-privileges',
        ]
        try:
            result = subprocess.run(command, env=env, capture_output=True, check=True)
        except FileNotFoundError:
            raise CommandError('Программа pg_dump не найдена. Установите клиент PostgreSQL (пакет postgresql-client).')
        except subprocess.CalledProcessError as error:
            raise CommandError('pg_dump завершился с ошибкой: ' + error.stderr.decode(errors='replace'))

        with gzip.open(gz_path, 'wb') as f_out:
            f_out.write(result.stdout)
        return gz_path
