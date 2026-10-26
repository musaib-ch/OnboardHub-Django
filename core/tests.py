from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

import django.template.context as dj_ctx
def _fixed_context_copy(self):
    if hasattr(self, 'request'):
        duplicate = self.__class__(self.request)
    else:
        duplicate = self.__class__()
    duplicate.dicts = [d.copy() for d in getattr(self, 'dicts', [])]
    return duplicate
dj_ctx.BaseContext.__copy__ = _fixed_context_copy

<<<<<<< HEAD
from .models import Content, Tenant
from .models_offers import (
    OfferTemplate, OfferEmailTemplate, Offer, OfferApproval, OfferSendToken,
    OfferSignature, OfferFieldDefinition, OfferFieldValue,
)
=======
from .models_offers import OfferTemplate, OfferEmailTemplate, Offer, OfferApproval, OfferSendToken, OfferSignature
>>>>>>> origin/main
import core.tasks as tasks

tasks.send_email_async.delay = lambda *a, **k: None
tasks.send_raw_email_async.delay = lambda *a, **k: None

User = get_user_model()


<<<<<<< HEAD
class EmployeeLandingPageTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Northstar")
        self.other_tenant = Tenant.objects.create(name="Other Company")
        self.employee = User.objects.create(
            email="employee@northstar.test",
            full_name="Taylor Employee",
            role="employee",
            tenant=self.tenant,
            must_change_password=False,
        )
        self.teammate = User.objects.create(
            email="teammate@northstar.test",
            full_name="Morgan Teammate",
            role="employee",
            tenant=self.tenant,
            must_change_password=False,
        )
        self.other_employee = User.objects.create(
            email="other@company.test",
            full_name="Other Employee",
            role="employee",
            tenant=self.other_tenant,
            must_change_password=False,
        )
        Content.objects.create(
            tenant=self.tenant,
            kind="portal_resource",
            title="Northstar Handbook",
            body="Company policies and resources.",
            is_active=True,
        )
        Content.objects.create(
            tenant=self.other_tenant,
            kind="portal_resource",
            title="Other Company Handbook",
            body="Private company content.",
            is_active=True,
        )
        self.client.force_login(self.employee)

    def test_portal_renders_existing_employee_context(self):
        from django.urls import reverse

        response = self.client.get(reverse("portal"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Taylor Employee")
        self.assertContains(response, "Your Onboarding Roadmap")
        self.assertContains(response, "My Roadmap")

    def test_my_roadmap_shows_empty_state_without_assigned_plan(self):
        from django.urls import reverse

        response = self.client.get(reverse("my_onboarding_plan"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your roadmap is being prepared")

    def test_directory_and_resources_are_tenant_scoped(self):
        from django.urls import reverse

        directory = self.client.get(reverse("employee_directory"))
        self.assertEqual(directory.status_code, 200)
        self.assertContains(directory, "Morgan Teammate")
        self.assertNotContains(directory, "Other Employee")

        resources = self.client.get(reverse("employee_resources"))
        self.assertEqual(resources.status_code, 200)
        self.assertContains(resources, "Northstar Handbook")
        self.assertNotContains(resources, "Other Company Handbook")


class PortalCmsEditingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Northstar")
        self.admin = User.objects.create(
            email="admin@northstar.test",
            full_name="Northstar Admin",
            role="super_admin",
            tenant=self.tenant,
            must_change_password=False,
        )
        self.client.force_login(self.admin)

    def test_portal_content_can_create_edit_and_publish_resources(self):
        from django.urls import reverse

        content_url = reverse("admin_portal_cms")
        page = self.client.get(content_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Resources &amp; Perks")

        response = self.client.post(content_url, {
            "kind": "portal_resource",
            "title": "Security Handbook",
            "category": "Security",
            "body": "Protect company information.",
            "link": "https://example.com/security",
            "display_order": "0",
        })
        self.assertEqual(response.status_code, 302)
        item = Content.objects.get(tenant=self.tenant, kind="portal_resource", title="Security Handbook")

        response = self.client.post(content_url, {
            "action": "edit",
            "item_id": item.id,
            "title": "Updated Security Handbook",
            "category": "Security",
            "body": "Updated company security guidance.",
            "link": "https://example.com/security",
            "display_order": "1",
        })
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.title, "Updated Security Handbook")
        self.assertEqual(item.body, "Updated company security guidance.")

        resources = self.client.get(reverse("employee_resources"))
        self.assertEqual(resources.status_code, 200)
        self.assertContains(resources, "Updated Security Handbook")
        self.assertContains(resources, "Updated company security guidance.")

        Content.objects.create(
            tenant=self.tenant,
            kind="portal_resource",
            category="Toolkit",
            title="Company SSO",
            body="Sign in with your organization account.",
            meta={"link": "https://example.com/sso"},
        )
        Content.objects.create(
            tenant=self.tenant,
            kind="portal_resource",
            category="Principle",
            title="Share context",
            body="Document decisions and share useful context.",
        )
        landing = self.client.get(reverse("portal"))
        self.assertContains(landing, "Company SSO")
        self.assertContains(landing, "Share context")


=======
>>>>>>> origin/main
class ApprovalAutoSendTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.hr = User.objects.create(email='hr@example.com', full_name='HR')
        self.hr.set_password('pass')
        self.hr.must_change_password = False
        self.hr.role = 'super_admin'
        self.hr.save()
        self.hr.has_perm_key = lambda k: True
        self.tpl = OfferTemplate.objects.create(name='T', html_content='<p>Hello {{candidate_name}}</p>')

    def test_approvals_create_and_auto_send(self):
        o = Offer.objects.create(created_by=self.hr, candidate_name='Jane', candidate_email='jane@example.com', template=self.tpl)
        ap1 = OfferApproval.objects.create(offer=o, order=0, status='pending')
        ap2 = OfferApproval.objects.create(offer=o, order=1, status='pending')
        self.client.force_login(self.hr)
        resp1 = self.client.post(f'/api/offers/{o.id}/approvals/{ap1.id}/approve/')
        self.assertEqual(resp1.status_code, 200)
        o.refresh_from_db()
        self.assertIn(o.status, ('draft', 'pending_approval', 'pending'))
        resp2 = self.client.post(f'/api/offers/{o.id}/approvals/{ap2.id}/approve/')
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        if data2.get('sent'):
            self.assertIn('view_token', data2)
            self.assertIn('accept_token', data2)
            self.assertIn('reject_token', data2)
        o.refresh_from_db()
        self.assertEqual(o.status, 'sent')
        self.assertTrue(OfferSendToken.objects.filter(offer=o, token_type='accept').exists())


class PublicOfferFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.hr = User.objects.create(email='hr2@example.com', full_name='HR2')
        self.hr.set_password('pass')
        self.hr.must_change_password = False
        self.hr.role = 'super_admin'
        self.hr.save()
        self.hr.has_perm_key = lambda k: True
        self.tpl = OfferTemplate.objects.create(name='Tpl', html_content='<p>Offer for {{candidate_name}}</p>')

    def test_snapshot_send_and_public_accept_reject(self):
        o = Offer.objects.create(created_by=self.hr, candidate_name='Alice', candidate_email='alice@example.com', template=self.tpl)
        self.client.force_login(self.hr)
        resp = self.client.post(f'/api/offers/{o.id}/snapshot/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('status'), 'sent')
        view_token = data.get('view_token')
        accept_token = data.get('accept_token')
        reject_token = data.get('reject_token')
        
        vresp = self.client.get(f'/offers/view/{view_token}/')
        self.assertEqual(vresp.status_code, 200)

        # Accept via public endpoint with drawn signature payload
        payload = {
            'signer_name': 'Alice Smith',
            'signature_method': 'drawn',
            'signature_blob': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        }
        aparent = self.client.post(f'/offers/{accept_token}/accept/', content_type='application/json', data=payload)
        self.assertEqual(aparent.status_code, 200)
        o.refresh_from_db()
        self.assertEqual(o.status, 'accepted')
        self.assertTrue(OfferSignature.objects.filter(offer=o, signature_method='drawn').exists())

        # Duplicate accept should fail
        aparent2 = self.client.post(f'/offers/{accept_token}/accept/', content_type='application/json', data='{}')
        self.assertNotEqual(aparent2.status_code, 200)

        # Reject test
        o2 = Offer.objects.create(created_by=self.hr, candidate_name='Bob', candidate_email='bob@example.com', template=self.tpl)
        r = self.client.post(f'/api/offers/{o2.id}/snapshot/')
        self.assertEqual(r.status_code, 200)
        reject_token2 = r.json().get('reject_token')
        rresp = self.client.post(f'/offers/{reject_token2}/reject/', content_type='application/json', data='{"reason":"Not interested"}')
        self.assertEqual(rresp.status_code, 200)
        o2.refresh_from_db()
        self.assertEqual(o2.status, 'rejected')


class OfferPDFAndExportTests(TestCase):
    def setUp(self):
        self.client = Client()
<<<<<<< HEAD
        self.tenant = Tenant.objects.create(name='Demo Company')
        self.hr = User.objects.create(email='hr3@example.com', full_name='HR Exporter', tenant=self.tenant)
=======
        self.hr = User.objects.create(email='hr3@example.com', full_name='HR Exporter')
>>>>>>> origin/main
        self.hr.set_password('pass')
        self.hr.must_change_password = False
        self.hr.role = 'super_admin'
        self.hr.save()
        self.hr.has_perm_key = lambda k: True
<<<<<<< HEAD
        self.tpl = OfferTemplate.objects.create(tenant=self.tenant, name='Export Tpl', html_content='<h1>Offer Document</h1><p>Candidate: {{candidate_name}}</p>')
        self.offer = Offer.objects.create(tenant=self.tenant, created_by=self.hr, candidate_name='Charlie', candidate_email='charlie@example.com', template=self.tpl, rendered_html='<h1>Offer Document</h1>')

    def test_company_and_shared_placeholder_settings_from_organization_tabs(self):
        from django.urls import reverse

        self.client.force_login(self.hr)
        page = self.client.get(reverse('admin_organization'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Company Profile')
        self.assertContains(page, 'Shared Placeholders')

        response = self.client.post(reverse('admin_organization'), {
            'action': 'save_company_name',
            'company_name': 'Northstar Labs',
        })
        self.assertEqual(response.status_code, 302)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.name, 'Northstar Labs')

        response = self.client.post(reverse('admin_organization'), {
            'action': 'add_offer_placeholder',
            'placeholder_name': 'Office Address',
            'placeholder_key': 'office_address',
            'default_value': '42 Main Street',
        })
        self.assertEqual(response.status_code, 302)
        field = OfferFieldDefinition.objects.get(tenant=self.tenant, key='office_address')
        self.assertEqual(field.meta['default_value'], '42 Main Street')

    def test_shared_values_are_available_in_offer_and_notification_templates(self):
        from unittest.mock import patch
        from .email_service import employee_email_context, render_email
        from .services.email_service import EmailService
        from .services.template_context import offer_template_context
        from .views.offer_api_views import _perform_offer_send

        field = OfferFieldDefinition.objects.create(
            tenant=self.tenant,
            name='Office Address',
            key='office_address',
            meta={'default_value': '42 Main Street'},
        )
        OfferFieldValue.objects.create(offer=self.offer, field_definition=field, value='Offer-specific office')
        self.tpl.html_content = '<p>{{ company_name }}|{{ office_address }}|{{ offer_number }}|{{ current_date }}</p>'
        self.tpl.save()

        context = offer_template_context(self.offer)
        self.assertEqual(context['company_name'], 'Demo Company')
        self.assertEqual(context['office_address'], 'Offer-specific office')
        self.assertTrue(context['offer_number'])
        self.assertTrue(context['current_date'])

        employee = User.objects.create(
            email='employee@example.com', full_name='Demo Employee', role='employee', tenant=self.tenant,
        )
        notification_context = employee_email_context(employee)
        self.assertEqual(notification_context['office_address'], '42 Main Street')

        with patch('core.email_service.get_email_templates', return_value={
            'reminder': {'subject': '{{ company_name }} / {office_address}', 'body': '{{ office_address }}'}
        }), patch('core.email_service.get_custom_templates', return_value={}):
            subject, body = render_email('reminder', notification_context)
        self.assertEqual(subject, 'Demo Company / 42 Main Street')
        self.assertEqual(body, '42 Main Street')

        with patch.object(EmailService, 'get_template', return_value={
            'subject': '{{ company_name }} / {{ office_address }}',
            'title': 'Shared values',
            'body': '{{ office_address }}',
        }), patch('core.services.email_service.send_mail') as send_mail:
            EmailService.send_email(
                to_email=employee.email,
                template_key='shared_test',
                context={'full_name': employee.full_name},
                log_event=False,
            )
        self.assertEqual(send_mail.call_args.kwargs['subject'], 'Demo Company / 42 Main Street')
        self.assertIn('42 Main Street', send_mail.call_args.kwargs['html_message'])

        _perform_offer_send(self.offer, acting_user=self.hr)
        self.offer.refresh_from_db()
        self.assertIn('Demo Company|Offer-specific office|', self.offer.rendered_html)
=======
        self.tpl = OfferTemplate.objects.create(name='Export Tpl', html_content='<h1>Offer Document</h1><p>Candidate: {{candidate_name}}</p>')
        self.offer = Offer.objects.create(created_by=self.hr, candidate_name='Charlie', candidate_email='charlie@example.com', template=self.tpl, rendered_html='<h1>Offer Document</h1>')
>>>>>>> origin/main

    def test_pdf_export_endpoint(self):
        self.client.force_login(self.hr)
        resp = self.client.get(f'/api/offers/{self.offer.id}/pdf/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.has_header('Content-Disposition'))
<<<<<<< HEAD
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF-'))

    def test_pdf_export_reports_missing_renderer(self):
        from unittest.mock import patch

        self.client.force_login(self.hr)
        with patch('core.services.pdf_service.XHTML2PDF_AVAILABLE', False):
            resp = self.client.get(f'/api/offers/{self.offer.id}/pdf/')
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp['Content-Type'], 'text/plain; charset=utf-8')
        self.assertFalse(resp.has_header('Content-Disposition'))
=======
>>>>>>> origin/main

    def test_bulk_zip_export_endpoint(self):
        self.client.force_login(self.hr)
        resp = self.client.get('/admin/offers/export/zip/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/zip')

    def test_resend_rejected_offer(self):
        # Set offer status to rejected
        self.offer.status = 'rejected'
        self.offer.save()
        
        # Create a mock user who is the candidate
        candidate = User.objects.create(email='charlie@example.com', full_name='Charlie Candidate', role='employee', status='offer_rejected')
        self.offer.candidate_user = candidate
        self.offer.save()

        self.client.force_login(self.hr)
        post_data = {
            'position_title': 'Lead Developer',
            'salary': '150000',
            'currency': 'USD',
            'start_date': (timezone.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
            'expiry_date': (timezone.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M"),
            'benefits': 'Premium health cover',
            'note': 'Welcome back!',
            'offer_template_id': self.tpl.id,
        }
        resp = self.client.post(f'/admin/offers/{self.offer.id}/resend/', data=post_data)
        self.assertEqual(resp.status_code, 302)
        
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, 'sent')
        self.assertEqual(self.offer.offer_data['position_title'], 'Lead Developer')
        self.assertEqual(self.offer.offer_data['salary'], '150000')
        
        # Candidate status should go back to 'offer'
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, 'offer')


class OfferExpiryTaskTests(TestCase):
    def setUp(self):
        self.hr = User.objects.create(email='hr4@example.com', full_name='HR Expiry')
        self.tpl = OfferTemplate.objects.create(name='Tpl', html_content='<p>Test</p>')

    def test_check_expired_offers_task(self):
        past_date = timezone.now() - timedelta(days=2)
        o = Offer.objects.create(
            created_by=self.hr,
            candidate_name='Expired User',
            candidate_email='exp@example.com',
            template=self.tpl,
            status='sent',
            metadata={'expiry_date': past_date.isoformat()}
        )
        tok = OfferSendToken.objects.create(offer=o, token_type='accept', used=False)

        res = tasks.check_expired_offers_task()
        self.assertGreaterEqual(res.get('expired_count', 0), 1)

        o.refresh_from_db()
        self.assertEqual(o.status, 'expired')
        tok.refresh_from_db()
        self.assertTrue(tok.used)


class OnboardingBuddyNavbarTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.employee = User.objects.create(email='emp@example.com', full_name='John Employee', role='employee', status='pre_onboarding')
        self.employee.set_password('pass')
        self.employee.must_change_password = False
        self.employee.save()
        
        self.buddy = User.objects.create(email='buddy@example.com', full_name='Jane Buddy', role='employee')
        self.buddy.set_password('pass')
        self.buddy.must_change_password = False
        self.buddy.save()

    def test_buddy_navbar_visibility(self):
        # 1. Login as employee, buddy should NOT be visible
        self.client.force_login(self.employee)
        resp = self.client.get('/portal/')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context.get('has_buddy', False))
        
        # 2. Pair employee with buddy
        from .models import Engagement
        Engagement.objects.create(
            kind="mentorship",
            user=self.employee,
            counterparty=self.buddy,
            status="active"
        )
        
        # 3. Request page again, has_buddy should be True
        resp = self.client.get('/portal/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context.get('has_buddy', False))
