import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection, transaction
from django_tenants.utils import schema_context
from tenants.models import City


def run_fix():
    schemas = [city.schema_name for city in City.objects.exclude(schema_name="public")]
    print(f"Found schemas to check: {schemas}")

    for schema in schemas:
        print(f"\nProcessing schema: {schema}...")
        with schema_context(schema):
            with connection.cursor() as cursor:
                # 1. Check if raw_material_id already exists in inventory_stock (filtered by schema!)
                cursor.execute(
                    """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_schema = %s AND table_name = 'inventory_stock' AND column_name = 'raw_material_id'
                """,
                    [schema],
                )
                has_raw_material = cursor.fetchone()

                if has_raw_material:
                    print(
                        f"  [i] Schema '{schema}' already has 'raw_material_id' in 'inventory_stock'. Checking product_id..."
                    )
                else:
                    print(
                        f"  [*] Adding 'raw_material_id' column to 'inventory_stock' in '{schema}'..."
                    )
                    with transaction.atomic():
                        # Add raw_material_id column as nullable UUID
                        cursor.execute(
                            """
                            ALTER TABLE inventory_stock 
                            ADD COLUMN raw_material_id uuid REFERENCES inventory_rawmaterial(id) ON DELETE CASCADE
                        """
                        )
                    print(f"  [+] Column 'raw_material_id' added successfully.")

                # 2. Check if product_id exists to migrate data (filtered by schema!)
                cursor.execute(
                    """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_schema = %s AND table_name = 'inventory_stock' AND column_name = 'product_id'
                """,
                    [schema],
                )
                has_product = cursor.fetchone()

                if has_product:
                    print(
                        f"  [*] Migrating stock data from products to raw materials in '{schema}'..."
                    )
                    with transaction.atomic():
                        # Copy raw_material_id from product to stock
                        cursor.execute(
                            """
                            UPDATE inventory_stock s
                            SET raw_material_id = p.raw_material_id
                            FROM inventory_product p
                            WHERE s.product_id = p.id AND p.raw_material_id IS NOT NULL
                        """
                        )

                        # Drop unique together constraint on product + warehouse if exists
                        try:
                            cursor.execute(
                                "ALTER TABLE inventory_stock DROP CONSTRAINT IF EXISTS inventory_stock_product_id_warehouse_id_74744dca_uniq"
                            )
                        except Exception as e:
                            print(f"  [i] Unique constraint drop info: {e}")

                        # Drop product_id column
                        cursor.execute(
                            "ALTER TABLE inventory_stock DROP COLUMN product_id"
                        )
                        print("  [+] product_id column dropped and data migrated.")

                # 3. Ensure unique constraint exists on raw_material_id + warehouse_id
                try:
                    with transaction.atomic():
                        cursor.execute(
                            """
                            ALTER TABLE inventory_stock 
                            ADD CONSTRAINT inventory_stock_raw_material_id_warehouse_id_uniq 
                            UNIQUE (raw_material_id, warehouse_id)
                        """
                        )
                        print(
                            "  [+] Added unique constraint (raw_material_id, warehouse_id)."
                        )
                except Exception as e:
                    print(
                        f"  [i] Unique constraint on raw_material_id + warehouse_id already exists or error: {e}"
                    )


if __name__ == "__main__":
    run_fix()
