from django.test import TestCase
from accounts.models import User
from accounts.management.commands.update_usernames import (
    clean_alpha_string,
    parse_names,
    build_pench_username,
    get_alpha_suffix,
    DEFAULT_PLACEHOLDERS,
)
from django.core.management import call_command
from io import StringIO


class UpdateUsernamesLogicTest(TestCase):
    def test_clean_alpha_string(self):
        self.assertEqual(clean_alpha_string("John123"), "John")
        self.assertEqual(clean_alpha_string("Driver 1"), "Driver")
        self.assertEqual(clean_alpha_string("12345"), "")
        self.assertEqual(clean_alpha_string("VM-Driver-2"), "VMDriver")
        self.assertEqual(clean_alpha_string("Mr. Rajesh"), "Mr Rajesh")

    def test_parse_names_with_placeholders(self):
        # Both first and last name present
        self.assertEqual(parse_names("Rahul", "Sharma"), ("rahul", "sharma"))
        # First name only
        self.assertEqual(parse_names("Rahul", ""), ("rahul", None))
        # Last name only
        self.assertEqual(parse_names("", "Sharma"), ("sharma", None))
        # Titles stripped
        self.assertEqual(parse_names("Mr. Rahul", "Sharma"), ("rahul", "sharma"))
        self.assertEqual(parse_names("Dr.", "Sharma"), ("sharma", None))
        # Numbers stripped completely
        self.assertEqual(parse_names("Driver 1", ""), (None, None))
        # Placeholders stripped!
        self.assertEqual(parse_names("John", "Placeholder"), ("john", None))
        self.assertEqual(parse_names("Rahul", "User"), ("rahul", None))
        self.assertEqual(parse_names("Pooja", "Customer"), ("pooja", None))
        self.assertEqual(parse_names("Raju", "Delivery"), ("raju", None))
        self.assertEqual(parse_names("Sneha", "NA"), ("sneha", None))
        self.assertEqual(parse_names("Vikram", "None"), ("vikram", None))
        self.assertEqual(parse_names("Amit", "Unknown"), ("amit", None))
        # Both placeholder
        self.assertEqual(parse_names("User", "Placeholder"), (None, None))

    def test_build_pench_username_with_placeholders(self):
        # Format: pench_firstname_lastname
        self.assertEqual(build_pench_username("Rahul", "Sharma"), "pench_rahul_sharma")
        # Format: pench_firstname when last name is placeholder
        self.assertEqual(build_pench_username("John", "Placeholder"), "pench_john")
        self.assertEqual(build_pench_username("Rahul", "User"), "pench_rahul")
        self.assertEqual(build_pench_username("Pooja", "Customer"), "pench_pooja")
        self.assertEqual(build_pench_username("Raju", "Delivery"), "pench_raju")
        self.assertEqual(build_pench_username("Sneha", "NA"), "pench_sneha")
        self.assertEqual(build_pench_username("Vikram", "None"), "pench_vikram")
        # Format: pench_lastname when first name is placeholder
        self.assertEqual(build_pench_username("Customer", "Sharma"), "pench_sharma")
        # No numbers added
        self.assertEqual(build_pench_username("Aditya 1", "Parsodiya 2"), "pench_aditya_parsodiya")
        # Empty or placeholder names returns None
        self.assertIsNone(build_pench_username("", ""))
        self.assertIsNone(build_pench_username("123", "456"))
        self.assertIsNone(build_pench_username("User", "Placeholder"))

    def test_get_alpha_suffix(self):
        self.assertEqual(get_alpha_suffix(0), "a")
        self.assertEqual(get_alpha_suffix(1), "b")
        self.assertEqual(get_alpha_suffix(25), "z")
        self.assertEqual(get_alpha_suffix(26), "aa")

    def test_command_dry_run_and_apply(self):
        # Create test users
        u1 = User.objects.create(
            username="old_user_1",
            first_name="Amit",
            last_name="Verma",
            phone="9000000001",
        )
        u2 = User.objects.create(
            username="old_user_2",
            first_name="Pooja",
            last_name="User",  # Placeholder last name
            phone="9000000002",
        )
        u3 = User.objects.create(
            username="old_user_3",
            first_name="123",
            last_name="456",
            phone="9000000003",
        )
        u4 = User.objects.create(
            username="old_user_4",
            first_name="Raju",
            last_name="Placeholder",  # Literal placeholder
            phone="9000000004",
        )

        out = StringIO()
        # 1. Test Dry Run
        call_command("update_usernames", dry_run=True, stdout=out)
        u1.refresh_from_db()
        u2.refresh_from_db()
        self.assertEqual(u1.username, "old_user_1")
        self.assertEqual(u2.username, "old_user_2")

        # 2. Test Apply
        out_apply = StringIO()
        call_command("update_usernames", apply=True, stdout=out_apply)
        u1.refresh_from_db()
        u2.refresh_from_db()
        u3.refresh_from_db()
        u4.refresh_from_db()

        self.assertEqual(u1.username, "pench_amit_verma")
        # Placeholder "User" skipped -> pench_pooja
        self.assertEqual(u2.username, "pench_pooja")
        # All numbers -> skipped
        self.assertEqual(u3.username, "old_user_3")
        # Placeholder "Placeholder" skipped -> pench_raju
        self.assertEqual(u4.username, "pench_raju")

    def test_command_collision_handling(self):
        # Two users with the same name
        u1 = User.objects.create(
            username="test_a",
            first_name="Ravi",
            last_name="Sharma",
            phone="9100000001",
        )
        u2 = User.objects.create(
            username="test_b",
            first_name="Ravi",
            last_name="Sharma",
            phone="9100000002",
        )

        # By default (on_collision='skip'): first gets pench_ravi_sharma, second is skipped (no numbers!)
        out = StringIO()
        call_command("update_usernames", apply=True, on_collision="skip", stdout=out)
        u1.refresh_from_db()
        u2.refresh_from_db()

        self.assertEqual(u1.username, "pench_ravi_sharma")
        self.assertEqual(u2.username, "test_b")  # Skipped without error or number

        # Now test on_collision='alpha'
        out_alpha = StringIO()
        call_command("update_usernames", apply=True, on_collision="alpha", stdout=out_alpha)
        u2.refresh_from_db()
        self.assertEqual(u2.username, "pench_ravi_sharma_a")
