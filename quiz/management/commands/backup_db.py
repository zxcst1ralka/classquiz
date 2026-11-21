import gzip
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Делает резервную копию базы данных (SQLite), сжимает её и удаляет старые копии.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep', type=int, default=30,
            help='Сколько последних копий хранить (по умолчанию 30, то есть примерно месяц ежедневных копий).',
        )

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        if 'sqlite3' not in db['ENGINE']:
            raise CommandError('Команда умеет копировать только SQLite. Для PostgreSQL используйте pg_dump.')

        source_path = Path(db['NAME'])
        if not source_path.exists():
            raise CommandError(f'Файл базы не найден: {source_path}')

        backup_dir = Path(getattr(settings, 'BACKUP_DIR', settings.BASE_DIR / 'backups'))
        backup_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
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

        # Удаляем самые старые копии, оставляем последние --keep штук
        copies = sorted(backup_dir.glob('db-*.sqlite3.gz'))
        removed = 0
        for old in copies[:-options['keep']] if options['keep'] > 0 else []:
            old.unlink()
            removed += 1

        size_kb = gz_path.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(f'Резервная копия создана: {gz_path} ({size_kb:.0f} КБ)'))
        if removed:
            self.stdout.write(f'Удалено старых копий: {removed}')
