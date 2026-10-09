#!/usr/bin/env python
"""
Standalone script to change usernames on VM or local environment to:
    pench_firstname_lastname
First name and last name are added if available, else skipped.
Strictly NO numbers are added.

Usage:
    python update_usernames.py [options]

Examples:
    # 1. Preview changes (Dry Run - no DB modifications):
    python update_usernames.py

    # 2. Apply and save changes to DB:
    python update_usernames.py --apply

    # 3. Apply changes including superusers/staff (by default protected):
    python update_usernames.py --apply --include-superusers

    # 4. Filter by role (drivers, customers, erp):
    python update_usernames.py --apply --role drivers

    # 5. Resolve duplicate collisions with letters (_a, _b, etc.) without numbers:
    python update_usernames.py --apply --on-collision alpha
"""

import os
import sys
import django

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Set Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Setup Django
django.setup()

from django.core.management import execute_from_command_line

if __name__ == "__main__":
    # Insert 'update_usernames' command name into sys.argv
    args = [sys.argv[0], "update_usernames"] + sys.argv[1:]
    execute_from_command_line(args)
