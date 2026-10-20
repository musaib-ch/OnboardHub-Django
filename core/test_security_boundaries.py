"""Regression tests for sensitive offer API access boundaries."""
from types import SimpleNamespace

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from core.views.offer_api_views import offer_access_required


class OfferAccessBoundaryTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = offer_access_required(lambda request: HttpResponse('ok'))

    def make_request(self, role, permitted=False, authenticated=True):
        request = self.factory.get('/api/offers/')
        request.user = SimpleNamespace(
            is_authenticated=authenticated,
            role=role,
            has_perm_key=lambda key: permitted and key == 'manage_offers',
        )
        return request

    def test_employee_denied(self):
        response = self.view(self.make_request('employee'))
        self.assertEqual(response.status_code, 403)

    def test_unprivileged_staff_denied(self):
        response = self.view(self.make_request('hrbp'))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_denied(self):
        response = self.view(self.make_request('employee', authenticated=False))
        self.assertEqual(response.status_code, 403)

    def test_offer_manager_allowed(self):
        response = self.view(self.make_request('offer_sender', permitted=True))
        self.assertEqual(response.status_code, 200)

    def test_super_admin_allowed(self):
        response = self.view(self.make_request('super_admin'))
        self.assertEqual(response.status_code, 200)
