#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


<<<<<<< HEAD
def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'onboardhub.settings')
=======
def _load_dotenv():
    """Load .env file into environment if it exists (development convenience)."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def main():
    """Run administrative tasks."""
    _load_dotenv()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onboardhub.settings")
>>>>>>> origin/main
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


<<<<<<< HEAD
if __name__ == '__main__':
=======
if __name__ == "__main__":
>>>>>>> origin/main
    main()
