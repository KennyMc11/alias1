# game/management/commands/cleanup_rooms.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from game.models import Room

class Command(BaseCommand):
    help = 'Удаляет старые неактивные комнаты'
    
    def handle(self, *args, **options):
        # Удаляем комнаты, созданные более 24 часов назад, которые не активны (не в статусе 'playing')
        cutoff_time = timezone.now() - timedelta(hours=24)
        old_rooms = Room.objects.filter(
            created_at__lt=cutoff_time
        ).exclude(status='playing')
        
        count = old_rooms.count()
        old_rooms.delete()
        
        self.stdout.write(
            self.style.SUCCESS(f'Удалено {count} старых комнат')
        )