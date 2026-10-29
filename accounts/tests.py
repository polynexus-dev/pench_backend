from django.contrib.auth import get_user_model
from django.db import connection
from unittest import mock

from django.core.cache.backends.locmem import LocMemCache
from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient

from accounts.models import OTP, UserLocation


class UserLocationAPITestCase(TenantTestCase):
    URL = "/api/accounts/locations/"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
        tenant.create_schema(sync_schema=True)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        User = get_user_model()
        self.user = User.objects.create_user(username="loc_user", phone="9000000501")
        self.other = User.objects.create_user(username="loc_other", phone="9000000502")
        connection.set_tenant(self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _post(self, **data):
        payload = {"address": "12 Main St", "latitude": "21.145800", "longitude": "79.088200"}
        payload.update(data)
        return self.client.post(self.URL, payload, format="json", HTTP_HOST="tenant.test.com")

    def test_first_location_becomes_default(self):
        response = self._post(tag="home")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["is_default"])

    def test_only_one_home_but_many_other(self):
        self.assertEqual(self._post(tag="home").status_code, 201)
        self.assertEqual(self._post(tag="home").status_code, 400)
        self.assertEqual(self._post(tag="other", label="Gym").status_code, 201)
        self.assertEqual(self._post(tag="other", label="Mom").status_code, 201)

    def test_invalid_coordinates_rejected(self):
        self.assertEqual(self._post(latitude="95").status_code, 400)

    def test_set_default_and_delete_promotes(self):
        home = self._post(tag="home").data
        work = self._post(tag="work", is_default=True).data
        self.assertFalse(UserLocation.objects.get(pk=home["id"]).is_default)

        r = self.client.post(f"{self.URL}{home['id']}/set-default/", HTTP_HOST="tenant.test.com")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(UserLocation.objects.get(pk=work["id"]).is_default)

        r = self.client.delete(f"{self.URL}{home['id']}/", HTTP_HOST="tenant.test.com")
        self.assertEqual(r.status_code, 204)
        self.assertTrue(UserLocation.objects.get(pk=work["id"]).is_default)

    def test_update(self):
        loc = self._post(tag="home").data
        r = self.client.patch(
            f"{self.URL}{loc['id']}/", {"landmark": "Near park"}, format="json", HTTP_HOST="tenant.test.com"
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["landmark"], "Near park")

    def test_cannot_see_or_touch_other_users_locations(self):
        theirs = UserLocation.objects.create(
            user=self.other, tag="home", address="x", latitude=1, longitude=1
        )
        self.assertEqual(self.client.get(self.URL, HTTP_HOST="tenant.test.com").data, [])
        r = self.client.delete(f"{self.URL}{theirs.pk}/", HTTP_HOST="tenant.test.com")
        self.assertEqual(r.status_code, 404)


class DefaultLocationSyncTestCase(TenantTestCase):
    URL = "/api/accounts/locations/"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
        tenant.create_schema(sync_schema=True)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.user = get_user_model().objects.create_user(
            username="sync_user", phone="9000000701", is_customer=True, tenant_schema="test"
        )
        connection.set_tenant(self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _post(self, **data):
        return self.client.post(self.URL, data, format="json", HTTP_HOST="tenant.test.com")

    def _customer_coords(self):
        from crm.models import Customer, _parse_coordinates

        customer = Customer.objects.get(user=self.user)
        lng, lat = _parse_coordinates(customer.location)
        return round(lat, 6), round(lng, 6), customer.address

    def test_default_location_is_copied_to_customer(self):
        self._post(tag="home", address="Home addr", landmark="Near temple", latitude="21.1", longitude="79.1")
        self.assertEqual(self._customer_coords(), (21.1, 79.1, "Home addr, Landmark: Near temple"))

    def test_non_default_location_does_not_change_customer(self):
        self._post(tag="home", address="Home addr", latitude="21.1", longitude="79.1")
        self._post(tag="work", address="Work addr", latitude="21.2", longitude="79.2")
        self.assertEqual(self._customer_coords()[2], "Home addr")

    def test_set_default_and_delete_resync_customer(self):
        home = self._post(tag="home", address="Home addr", latitude="21.1", longitude="79.1").data
        work = self._post(tag="work", address="Work addr", latitude="21.2", longitude="79.2").data

        self.client.post(f"{self.URL}{work['id']}/set-default/", HTTP_HOST="tenant.test.com")
        self.assertEqual(self._customer_coords(), (21.2, 79.2, "Work addr"))

        self.client.delete(f"{self.URL}{work['id']}/", HTTP_HOST="tenant.test.com")
        self.assertEqual(self._customer_coords(), (21.1, 79.1, "Home addr"))

    def test_editing_default_location_resyncs_customer(self):
        home = self._post(tag="home", address="Home addr", latitude="21.1", longitude="79.1").data
        self.client.patch(
            f"{self.URL}{home['id']}/", {"address": "New addr"}, format="json", HTTP_HOST="tenant.test.com"
        )
        self.assertEqual(self._customer_coords()[2], "New addr")


# The login/OTP views are throttled through the Redis cache; keep tests off Redis.
@mock.patch("rest_framework.throttling.SimpleRateThrottle.cache", LocMemCache("throttle-tests", {}))
class InactiveUserOTPLoginTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
        tenant.create_schema(sync_schema=True)

    def test_inactive_user_cannot_request_or_use_otp(self):
        from datetime import timedelta
        from django.utils import timezone

        connection.set_tenant(self.tenant)
        get_user_model().objects.create_user(
            username="inactive_otp", phone="9000000601", is_active=False
        )
        client = APIClient()

        r = client.post("/api/accounts/request-otp/", {"phone": "9000000601"}, format="json", HTTP_HOST="tenant.test.com")
        self.assertEqual(r.status_code, 403)

        OTP.objects.create(phone="9000000601", code="123456", expires_at=timezone.now() + timedelta(minutes=5))
        r = client.post(
            "/api/accounts/login-otp/", {"phone": "9000000601", "code": "123456"}, format="json", HTTP_HOST="tenant.test.com"
        )
        self.assertEqual(r.status_code, 403)
