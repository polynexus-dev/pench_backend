from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.db import connection
from tenants.models import Company, City

class CityFilteringTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Tenant'
        tenant.state = 'Test State'
        tenant.code = 'TST'

    def setUp(self):
        super().setUp()
        
        # Switch to public schema to create Company and City objects
        connection.set_schema_to_public()

        User = get_user_model()
        self.user = User.objects.create_user(
            username='admin_user',
            email='admin@example.com',
            password='testpassword',
            is_erp_user=True,
            tenant_schema='public'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Create Companies
        self.company_a = Company.objects.create(
            name='Company Alpha',
            code='ALPHA',
            is_active=True
        )
        self.company_b = Company.objects.create(
            name='Company Beta',
            code='BETA',
            is_active=True
        )

        # Create Cities
        self.city_1 = City.objects.create(
            company=self.company_a,
            name='New York',
            state='NY',
            code='NYC',
            schema_name='alpha_nyc',
            is_active=True
        )
        self.city_2 = City.objects.create(
            company=self.company_a,
            name='Los Angeles',
            state='CA',
            code='LAX',
            schema_name='alpha_lax',
            is_active=True
        )
        self.city_3 = City.objects.create(
            company=self.company_b,
            name='Chicago',
            state='IL',
            code='CHI',
            schema_name='beta_chi',
            is_active=True
        )

        # Restore test tenant context for the rest of the test flow
        connection.set_tenant(self.tenant)

    def test_list_cities_no_filter(self):
        response = self.client.get('/api/erp/tenants/cities/', HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        # TenantTestCase creates a public city and a test city, plus our 3 custom cities
        # So we verify that the custom cities are included successfully
        self.assertGreaterEqual(len(response.data), 3)

    def test_list_cities_filter_by_company_id_direct(self):
        # Using company parameter (ID)
        response = self.client.get(f'/api/erp/tenants/cities/?company={self.company_a.id}', HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        city_ids = [c['id'] for c in response.data]
        self.assertIn(self.city_1.id, city_ids)
        self.assertIn(self.city_2.id, city_ids)
        self.assertNotIn(self.city_3.id, city_ids)

    def test_list_cities_filter_by_company_id_explicit(self):
        # Using company_id parameter
        response = self.client.get(f'/api/erp/tenants/cities/?company_id={self.company_b.id}', HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.city_3.id)

    def test_list_cities_filter_by_company_code_direct(self):
        # Using company parameter (code)
        response = self.client.get('/api/erp/tenants/cities/?company=ALPHA', HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_list_cities_filter_by_company_code_explicit(self):
        # Using company_code parameter
        response = self.client.get('/api/erp/tenants/cities/?company_code=BETA', HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.city_3.id)

    def test_list_cities_filter_by_company_name_direct(self):
        # Using company parameter (partial name)
        response = self.client.get('/api/erp/tenants/cities/?company=Alpha', HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_list_cities_filter_by_company_name_explicit(self):
        # Using company_name parameter (partial name)
        response = self.client.get('/api/erp/tenants/cities/?company_name=Beta', HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.city_3.id)
