"""Vercel entry point: exposes the Django WSGI app as `app`."""
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent / 'chess_club'
sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chess_club.settings')

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()
