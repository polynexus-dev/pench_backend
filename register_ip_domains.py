import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from tenants.models import City, Domain

# 1. Fetch relevant cities/tenants
public_tenant = City.objects.get(schema_name="public")
pench_nagpur_tenant = City.objects.get(schema_name="pench-nagpur")
nagpur_tenant = City.objects.get(schema_name="nagpur")
pune_tenant = City.objects.get(schema_name="pune")

domains_to_register = [
    # domain, tenant_obj
    ("192.168.1.196", public_tenant),
    ("192.168.1.196.nip.io", public_tenant),
    ("pench-nagpur.192.168.1.196.nip.io", pench_nagpur_tenant),
    ("nagpur.192.168.1.196.nip.io", nagpur_tenant),
    ("pune.192.168.1.196.nip.io", pune_tenant),
    # Dev api domains
    ("pench.dev.api.polynexus.in", public_tenant),
    ("nagpur.pench.dev.api.polynexus.in", nagpur_tenant),
    ("pench-nagpur.pench.dev.api.polynexus.in", pench_nagpur_tenant),
    ("pune.pench.dev.api.polynexus.in", pune_tenant),
]

print("Registering local IP domains:")
for domain_name, tenant in domains_to_register:
    domain_obj, created = Domain.objects.get_or_create(
        domain=domain_name, defaults={"tenant": tenant, "is_primary": False}
    )
    if created:
        print(
            f"  [CREATED] Domain '{domain_name}' mapped to tenant schema '{tenant.schema_name}'"
        )
    else:
        # If it exists but belongs to a different tenant, update it
        if domain_obj.tenant != tenant:
            domain_obj.tenant = tenant
            domain_obj.save()
            print(
                f"  [UPDATED] Domain '{domain_name}' moved to tenant schema '{tenant.schema_name}'"
            )
        else:
            print(
                f"  [EXISTS] Domain '{domain_name}' already mapped to tenant schema '{tenant.schema_name}'"
            )

print("All domains registered successfully!")
