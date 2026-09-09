import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "payment_config.settings")
from django.core.management import execute_from_command_line

execute_from_command_line(sys.argv)
