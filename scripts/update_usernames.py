#!/usr/bin/env python
"""
Standalone script in scripts/ to change usernames on VM or local environment to:
    pench_firstname_lastname
First name and last name are added if available, else skipped.
Strictly NO numbers are added.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.core.management import execute_from_command_line

if __name__ == "__main__":
    args = [sys.argv[0], "update_usernames"] + sys.argv[1:]
    execute_from_command_line(args)
