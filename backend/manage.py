#!/usr/bin/env python
import os
import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "check_env":
        # Runs before any settings load, so it can report what would stop the production settings
        # from loading at all.
        from config.env_check import main as check_env

        sys.exit(check_env(sys.argv[2:]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
