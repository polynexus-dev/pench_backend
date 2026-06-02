import os
import django
import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django_tenants.utils import schema_context
from django.db import transaction
from inventory.models import Product
from crm.models import Customer
from subscriptions.models import (
    Subscription,
    SubscriptionItem,
    SubscriptionStatus,
    DeliveryFrequency,
)

# 1. Product Definitions
prod_1_lit = {
    "id": "b1bd59ce-fb5f-465e-83ba-b81257749f0e",
    "name": "A2 Gir Cow Milk (1 Litre)",
    "sku": "MILK-A2-1L",
    "description": "Pure Gir Cow A2 Milk in Glass Bottle",
    "unit_price": "108.00",
    "unit": "litre",
    "is_active": True,
    "is_returnable": False,
}

prod_half_lit = {
    "id": "84056666-7130-4428-89a1-a76919a77245",
    "name": "A2 Gir Cow Milk (1/2 Litre)",
    "sku": "MILK-A2-1/2L",
    "description": "Pure Gir Cow A2 Milk in Glass Bottle",
    "unit_price": "60.00",
    "unit": "litre",
    "is_active": True,
    "is_returnable": False,
}

customer_data = [
    {
        "id": "aa0171c4-c6ee-4552-86af-7d3e0837d523",
        "name": "akshay_jain",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "a46dbd3d-13cb-4b72-8f3b-835171249a30",
        "name": "akshay_tadas",
        "notes": "Milk Qty: 1 daily",
    },
    {
        "id": "48fd0730-36a1-4fbb-b314-15041ebc8f1e",
        "name": "alpna_patne",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "e3c152ae-e9a6-44d6-9325-131cdd8a6564",
        "name": "alwin_bobby",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "b07bdb14-c7ba-4a8c-b685-b0a0ca28e8fa",
        "name": "ankush_jaiswal",
        "notes": "Milk Qty: 2 lit Daily",
    },
    {
        "id": "45d1f7d5-b0b9-4ecd-87c5-2dca85655500",
        "name": "badal_gadbail",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "4ee93684-5a2a-499f-a6d7-7b6cc66468db",
        "name": "bhuahan_bawankar",
        "notes": "Milk Qty: 1.5 alt days",
    },
    {
        "id": "cde64178-1809-4798-8059-8242fe30f6c0",
        "name": "bhupesh_uikey",
        "notes": "Milk Qty: 1 lit Daily",
    },
    {
        "id": "982b1c2c-177a-452b-8095-d97698660201",
        "name": "chetan_gampawar",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "bca5f360-b93e-4700-8853-5527de247b27",
        "name": "harshal_mahajan",
        "notes": "Milk Qty: 1 lit Daily",
    },
    {
        "id": "95c2dda5-ec5a-4bab-89b6-09dc464d123d",
        "name": "kailash_ukunde",
        "notes": "Milk Qty: 1 daily",
    },
    {
        "id": "8cd39e0c-beca-4a89-83e7-63903d2d1519",
        "name": "kajol_modi",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "50763581-51ca-4787-a8bd-f4a66df39a35",
        "name": "karan_joshi",
        "notes": "Milk Qty: 1 lit",
    },
    {
        "id": "797611ba-2e4b-4d14-9994-b5c7e8627a8e",
        "name": "krishnarao_bande",
        "notes": "Milk Qty: 1.5 daily",
    },
    {
        "id": "3d2e0075-f1b9-4fb2-842c-26ae1c207a70",
        "name": "kushali_bagde",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "84b3e07f-88f4-4bd0-9be8-90ad066aeab5",
        "name": "mahesh_devgade",
        "notes": "Milk Qty: 1 alt days (same loc as Karan joshi)",
    },
    {
        "id": "b9f9abc3-53a3-4010-8b13-239f48f224fd",
        "name": "maheshwar_palaskar",
        "notes": "Milk Qty: 1 daily",
    },
    {
        "id": "d95e34f6-ecb0-47d6-9f51-1039b4f07a0b",
        "name": "mayuri_mahalley",
        "notes": "Milk Qty: 1 lit Daily",
    },
    {
        "id": "9afa9e52-40f7-40a4-938c-23c3f7abc445",
        "name": "minal_bhasme",
        "notes": "Milk Qty: 1 lit Daily",
    },
    {
        "id": "84cd20a3-e889-4fdd-8688-a929d39df0e6",
        "name": "nitin_chamorshikar",
        "notes": "Milk Qty: 0.5 lit daily",
    },
    {
        "id": "d33646c5-c0c9-44d7-af63-f9706d2eb011",
        "name": "pankaj_shrivastava",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "7fbe43f4-7a3a-4408-a6b0-08633f6a282b",
        "name": "piyush_bajpai",
        "notes": "Milk Qty: 1 daily",
    },
    {
        "id": "474de35b-2590-4528-9586-7a2a79ccca30",
        "name": "pranjali_kamble",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "1dbc1eb5-69b6-4246-b8b0-0c66839bf861",
        "name": "rajat_kukde",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "7a6f34b3-3dc9-4c44-8322-ccba7741c777",
        "name": "ranjeet_mankar",
        "notes": "Milk Qty: 1 daily",
    },
    {
        "id": "c1a92dd0-cef1-42ba-a8e1-3668217d390e",
        "name": "rupali_krushnamurthy",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "2e6000c3-3000-46b0-913d-7c9caad6f3c8",
        "name": "satish_chandrayaan",
        "notes": "Milk Qty: 1 lit Daily",
    },
    {
        "id": "a999ba01-a21c-4dab-a9a7-d92095eb3222",
        "name": "shailesh_gajapure",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "5666d398-36a0-4fe5-9fa1-323e1f133321",
        "name": "shital_ukunde",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "afa7bd6b-9279-4e44-a298-75dd81ae7f23",
        "name": "shivani_urkude",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "07e06e44-6606-41d5-85e8-d7d3fcd66022",
        "name": "sneha_nagarkar",
        "notes": "Milk Qty: 1 alt days",
    },
    {
        "id": "eddd280a-6669-43e4-b912-920160edc98a",
        "name": "sudhir_burde",
        "notes": "Milk Qty: 0.5 daily",
    },
    {
        "id": "22e5e7f2-6dbb-4bd7-b771-5b57b8704b27",
        "name": "vandana_gadwe",
        "notes": "Milk Qty: 1.5 alt days",
    },
    {
        "id": "40c68747-ffbe-4b46-b996-6c35411753f3",
        "name": "vimal_kumar_ojha",
        "notes": "Milk Qty: 2 lit Daily",
    },
    {
        "id": "72aa327a-2413-41f1-bdd8-d09acdc1738e",
        "name": "vinod_kelkar",
        "notes": "Milk Qty: 2 daily",
    },
]

schema_name = "pench-nagpur"

print(f"Switching to schema: {schema_name}")
with schema_context(schema_name):
    # 2. Ensure Products exist in the tenant schema
    for p_data in [prod_1_lit, prod_half_lit]:
        Product.objects.update_or_create(
            id=p_data["id"],
            defaults={
                "name": p_data["name"],
                "sku": p_data["sku"],
                "description": p_data["description"],
                "unit_price": p_data["unit_price"],
                "unit": p_data["unit"],
                "is_active": p_data["is_active"],
                "is_returnable": p_data["is_returnable"],
            },
        )
    print("Products verified/created successfully.")

    # 3. Process Customer Subscriptions in an atomic transaction
    with transaction.atomic():
        created_count = 0
        for c in customer_data:
            cust_id = c["id"]
            notes = c["notes"].lower()

            # Fetch the customer
            try:
                customer = Customer.objects.get(id=cust_id)
            except Customer.DoesNotExist:
                print(
                    f"WARNING: Customer {c['name']} (ID: {cust_id}) not found! Skipping."
                )
                continue

            # Determine frequency
            if "alt" in notes:
                frequency = DeliveryFrequency.ALTERNATE
            else:
                frequency = DeliveryFrequency.DAILY

            # Parse quantity and items
            items_to_create = []  # tuples of (product_id, quantity)

            if "1.5" in notes:
                # 1.5 Litres = one 1 Litre + one 1/2 Litre
                items_to_create.append((prod_1_lit["id"], 1))
                items_to_create.append((prod_half_lit["id"], 1))
            elif "0.5" in notes:
                # 0.5 Litres = one 1/2 Litre
                items_to_create.append((prod_half_lit["id"], 1))
            elif "2" in notes:
                # 2 Litres = two 1 Litre
                items_to_create.append((prod_1_lit["id"], 2))
            elif "1" in notes:
                # 1 Litre = one 1 Litre
                items_to_create.append((prod_1_lit["id"], 1))
            else:
                # Default fallback
                print(
                    f"Unknown quantity pattern in notes: '{c['notes']}' for customer {c['name']}. Defaulting to 1 Litre daily."
                )
                items_to_create.append((prod_1_lit["id"], 1))
                frequency = DeliveryFrequency.DAILY

            # Check if this customer already has active subscriptions to avoid duplicates
            existing_subs = Subscription.objects.filter(
                customer=customer, status=SubscriptionStatus.ACTIVE
            )
            if existing_subs.exists():
                print(
                    f"Customer {customer.name} already has active subscription(s). Skipping creation."
                )
                continue

            # Create the Subscription
            subscription = Subscription.objects.create(
                customer=customer,
                status=SubscriptionStatus.ACTIVE,
                frequency=frequency,
                start_date=datetime.date(2026, 5, 20),
                delivery_address=customer.address or "Address not specified",
            )

            # Create items
            for p_id, qty in items_to_create:
                SubscriptionItem.objects.create(
                    subscription=subscription, product_id=p_id, quantity=qty
                )

            created_count += 1
            print(
                f"Created subscription for {customer.name}: {items_to_create} ({frequency})"
            )

        print(
            f"\nSuccessfully created {created_count} subscriptions out of {len(customer_data)} customers!"
        )
