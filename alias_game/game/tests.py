from django.test import TestCase
from .models import Room
from .views import fetch_room_by_str
import uuid


class RoomIdTests(TestCase):
    def test_numeric_id_lookup(self):
        r = Room.objects.create(creator_telegram_id='123')
        self.assertEqual(len(r.id), 6)
        self.assertTrue(r.id.isdigit())
        found = fetch_room_by_str(r.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, r.id)

    def test_lookup_strips_whitespace(self):
        r = Room.objects.create(creator_telegram_id='456')
        found = fetch_room_by_str(f'  {r.id}  ')
        self.assertIsNotNone(found)
        self.assertEqual(found.id, r.id)

    def test_uuid_lookup_returns_none(self):
        fake_uuid = str(uuid.uuid4())
        self.assertIsNone(fetch_room_by_str(fake_uuid))

    def test_non_numeric_is_none(self):
        self.assertIsNone(fetch_room_by_str('abc123'))
