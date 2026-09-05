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

from .models_offers import OfferTemplate, OfferEmailTemplate, Offer, OfferApproval, OfferSendToken, OfferSignature
import core.tasks as tasks

tasks.send_email_async.delay = lambda *a, **k: None
tasks.send_raw_email_async.delay = lambda *a, **k: None

User = get_user_model()


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
        self.hr = User.objects.create(email='hr3@example.com', full_name='HR Exporter')
        self.hr.set_password('pass')
        self.hr.must_change_password = False
        self.hr.role = 'super_admin'
        self.hr.save()
        self.hr.has_perm_key = lambda k: True
        self.tpl = OfferTemplate.objects.create(name='Export Tpl', html_content='<h1>Offer Document</h1><p>Candidate: {{candidate_name}}</p>')
        self.offer = Offer.objects.create(created_by=self.hr, candidate_name='Charlie', candidate_email='charlie@example.com', template=self.tpl, rendered_html='<h1>Offer Document</h1>')

    def test_pdf_export_endpoint(self):
        self.client.force_login(self.hr)
        resp = self.client.get(f'/api/offers/{self.offer.id}/pdf/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.has_header('Content-Disposition'))

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
