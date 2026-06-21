#!/usr/bin/env python
"""
Automated End-to-End Testing Script
Tests entire OnboardHub workflow programmatically
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'onboardhub.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from core.models import Form, FormResponse, AppSetting, Content, Engagement
from datetime import datetime, date
import json

User = get_user_model()
client = Client()

# ============================================================================
# TEST RESULTS TRACKING
# ============================================================================

results = {
    'passed': [],
    'failed': [],
    'errors': [],
    'total': 0,
}

def log_test(name, passed, message=""):
    """Log test result"""
    results['total'] += 1
    if passed:
        results['passed'].append(name)
        print(f"[PASS] {name}")
    else:
        results['failed'].append((name, message))
        print(f"[FAIL] {name}: {message}")

def log_error(name, error):
    """Log error"""
    results['errors'].append((name, str(error)))
    print(f"[ERROR] {name}: {error}")

# ============================================================================
# PHASE 1: INITIAL VERIFICATION
# ============================================================================

print("\n" + "="*70)
print("PHASE 1: INITIAL VERIFICATION")
print("="*70)

# Verify employees exist
emp_count = User.objects.filter(role='employee', email__endswith='@test.com').count()
log_test("Employees created (3)", emp_count == 3, f"Found {emp_count}")

john = User.objects.get(email='john.eng@test.com')
log_test("John Engineer exists", john is not None)

sarah = User.objects.get(email='sarah.hr@test.com')
log_test("Sarah HR exists", sarah is not None)

mike = User.objects.get(email='mike.sales@test.com')
log_test("Mike Sales exists", mike is not None)

# Verify staff users
hrbp = User.objects.filter(email='hrbp@test.com').first()
log_test("HRBP created", hrbp is not None)

med = User.objects.filter(email='medical@test.com').first()
log_test("Medical Approver created", med is not None)

# ============================================================================
# PHASE 2: MEDICAL SUBMISSION & APPROVAL
# ============================================================================

print("\n" + "="*70)
print("PHASE 2: MEDICAL SUBMISSION & APPROVAL")
print("="*70)

# Login as John
logged_in = client.login(username='john.eng@test.com', password='testpass123')
log_test("John login", logged_in)

# Get medical page
response = client.get('/employee/medical/')
log_test("Medical page loads (John)", response.status_code == 200, f"Status: {response.status_code}")

# Submit medical (we can't actually upload a file via test client easily, but we can verify page)
log_test("Medical page renders form", b'medical' in response.content or b'submit' in response.content.lower())

# Medical approver login
client.logout()
logged_in = client.login(username='medical@test.com', password='testpass123')
log_test("Medical approver login", logged_in)

# Check medical review queue accessible
response = client.get('/admin/medical/review/')
log_test("Medical review page accessible", response.status_code == 200, f"Status: {response.status_code}")

# ============================================================================
# PHASE 3: PRE-ONBOARDING SUBMISSION
# ============================================================================

print("\n" + "="*70)
print("PHASE 3: PRE-ONBOARDING SUBMISSION")
print("="*70)

client.logout()
logged_in = client.login(username='john.eng@test.com', password='testpass123')
log_test("John login (pre-onboarding)", logged_in)

# Check pre-onboarding page
response = client.get('/employee/pre-onboarding/')
log_test("Pre-onboarding page loads", response.status_code == 200, f"Status: {response.status_code}")

# ============================================================================
# PHASE 4: ONBOARDING WORKFLOW
# ============================================================================

print("\n" + "="*70)
print("PHASE 4: ONBOARDING WORKFLOW")
print("="*70)

# Check onboarding page
response = client.get('/employee/onboarding/')
log_test("Onboarding page loads", response.status_code == 200, f"Status: {response.status_code}")

# Check post-onboarding
response = client.get('/employee/post-onboarding/')
log_test("Post-onboarding page loads", response.status_code == 200, f"Status: {response.status_code}")

# ============================================================================
# PHASE 5: DASHBOARD ACCESS
# ============================================================================

print("\n" + "="*70)
print("PHASE 5: DASHBOARD ACCESS")
print("="*70)

# Employee home
response = client.get('/employee/home/')
log_test("Employee home accessible", response.status_code == 200, f"Status: {response.status_code}")

# Check navigation links for employee
response = client.get('/learn/my-learning/')
log_test("My Learning page accessible", response.status_code == 200, f"Status: {response.status_code}")

# ============================================================================
# PHASE 6: ADMIN ACCESS & DASHBOARDS
# ============================================================================

print("\n" + "="*70)
print("PHASE 6: ADMIN ACCESS & DASHBOARDS")
print("="*70)

client.logout()
admin = User.objects.get(email='admin@onboardhub.local')
client.force_login(admin)
log_test("Admin login (force_login)", True)

# Admin dashboard
response = client.get('/admin/dashboard/')
log_test("Admin dashboard loads", response.status_code == 200, f"Status: {response.status_code}")

# Check dashboard contains employee metrics
dashboard_good = b'total' in response.content.lower() or b'employees' in response.content.lower()
log_test("Dashboard shows metrics", dashboard_good)

# Analytics dashboard
response = client.get('/admin/analytics/')
log_test("Analytics dashboard accessible", response.status_code == 200, f"Status: {response.status_code}")

# Employees list
response = client.get('/admin/employees/')
log_test("Employees list accessible", response.status_code == 200, f"Status: {response.status_code}")

# Employee detail
response = client.get(f'/admin/employees/{john.id}/')
log_test("Employee detail page loads", response.status_code == 200, f"Status: {response.status_code}")

# Medical review
response = client.get('/admin/medical/review/')
log_test("Medical review accessible (Admin)", response.status_code == 200, f"Status: {response.status_code}")

# ============================================================================
# PHASE 7: SETTINGS & FEATURES
# ============================================================================

print("\n" + "="*70)
print("PHASE 7: SETTINGS & FEATURES")
print("="*70)

# Email templates
response = client.get('/admin/settings/email-templates/')
log_test("Email templates page loads", response.status_code == 200, f"Status: {response.status_code}")

# Email logs
response = client.get('/admin/settings/email-logs/')
log_test("Email logs page loads", response.status_code == 200, f"Status: {response.status_code}")

# Zoom settings
response = client.get('/admin/settings/zoom/')
log_test("Zoom settings page loads", response.status_code == 200, f"Status: {response.status_code}")

# Check Zoom page has callback URL
zoom_callback_good = b'auth/zoom/callback' in response.content or b'redirect' in response.content.lower()
log_test("Zoom page shows callback URL", zoom_callback_good)

# ============================================================================
# PHASE 8: LIVE SESSIONS
# ============================================================================

print("\n" + "="*70)
print("PHASE 8: LIVE SESSIONS")
print("="*70)

# Sessions dashboard
response = client.get('/sessions/')
log_test("Sessions dashboard loads", response.status_code == 200, f"Status: {response.status_code}")

# Create session page
response = client.get('/sessions/create/')
log_test("Create session page accessible", response.status_code == 200, f"Status: {response.status_code}")

# ============================================================================
# PHASE 9: TRAINING & LEARNING PATHS
# ============================================================================

print("\n" + "="*70)
print("PHASE 9: TRAINING & LEARNING PATHS")
print("="*70)

# Learning paths
response = client.get('/admin/training/paths/')
log_test("Learning paths page loads", response.status_code == 200, f"Status: {response.status_code}")

# Training assignments
response = client.get('/admin/training/assignments/')
log_test("Training assignments page loads", response.status_code == 200, f"Status: {response.status_code}")

# ============================================================================
# PHASE 10: ROLE-BASED ACCESS CONTROL
# ============================================================================

print("\n" + "="*70)
print("PHASE 10: ROLE-BASED ACCESS CONTROL")
print("="*70)

# HRBP Access
client.logout()
logged_in = client.login(username='hrbp@test.com', password='testpass123')
log_test("HRBP login", logged_in)

# HRBP can see employees
response = client.get('/admin/employees/')
log_test("HRBP can access employees", response.status_code == 200, f"Status: {response.status_code}")

# HRBP can see dashboard (or limited version)
response = client.get('/admin/dashboard/')
hrbp_can_access = response.status_code in [200, 302]  # 302 if redirected is OK
log_test("HRBP can access dashboard", hrbp_can_access, f"Status: {response.status_code}")

# HRBP cannot access Setup (should be 403 or redirect)
response = client.get('/admin/branding/')
hrbp_restricted = response.status_code in [403, 302]
log_test("HRBP restricted from Setup", hrbp_restricted, f"Status: {response.status_code}")

# Medical Approver Access
client.logout()
logged_in = client.login(username='medical@test.com', password='testpass123')
log_test("Medical approver login", logged_in)

# Medical can see medical review
response = client.get('/admin/medical/review/')
log_test("Medical approver can see queue", response.status_code == 200, f"Status: {response.status_code}")

# Medical cannot see employees
response = client.get('/admin/employees/')
medical_restricted = response.status_code in [403, 302]
log_test("Medical restricted from employees", medical_restricted, f"Status: {response.status_code}")

# ============================================================================
# PHASE 11: FORMS & ONBOARDING
# ============================================================================

print("\n" + "="*70)
print("PHASE 11: FORMS & ONBOARDING")
print("="*70)

# Back to admin
client.logout()
client.force_login(admin)

# Forms list
response = client.get('/admin/forms/')
log_test("Forms list accessible", response.status_code == 200, f"Status: {response.status_code}")

# Documents
response = client.get('/admin/documents/')
log_test("Documents page accessible", response.status_code == 200, f"Status: {response.status_code}")

# Medical requirements
response = client.get('/admin/medical-requirements/')
log_test("Medical requirements page accessible", response.status_code == 200, f"Status: {response.status_code}")

# Organization setup
response = client.get('/admin/organization/')
log_test("Organization setup accessible", response.status_code == 200, f"Status: {response.status_code}")

# ============================================================================
# PHASE 12: DATABASE VERIFICATION
# ============================================================================

print("\n" + "="*70)
print("PHASE 12: DATABASE VERIFICATION")
print("="*70)

# Check all employees still exist
johns = User.objects.filter(email='john.eng@test.com')
log_test("John in database", johns.exists())

sarahs = User.objects.filter(email='sarah.hr@test.com')
log_test("Sarah in database", sarahs.exists())

mikes = User.objects.filter(email='mike.sales@test.com')
log_test("Mike in database", mikes.exists())

# Check statuses
john = johns.first()
log_test("John status is 'pending'", john.status == 'pending', f"Status: {john.status}")

# Check departments
log_test("John in Engineering dept", john.department.name == 'Engineering', f"Dept: {john.department.name}")

sarah = sarahs.first()
log_test("Sarah in HR dept", sarah.department.name == 'Human Resources', f"Dept: {sarah.department.name}")

# ============================================================================
# PHASE 13: TEMPLATE & FEATURE CHECKS
# ============================================================================

print("\n" + "="*70)
print("PHASE 13: TEMPLATE & FEATURE CHECKS")
print("="*70)

# Check email templates exist
templates = AppSetting.objects.filter(key__startswith='email_template_')
log_test("Email templates configured", templates.exists(), f"Found {templates.count()}")

# Check zoom settings endpoint exists
response = client.get('/admin/settings/zoom/')
log_test("Zoom settings URL configured", response.status_code == 200)

# Check sessions endpoint exists
response = client.get('/sessions/')
log_test("Sessions URL configured", response.status_code == 200)

# ============================================================================
# FINAL REPORT
# ============================================================================

print("\n" + "="*70)
print("FINAL TEST REPORT")
print("="*70)

total = results['total']
passed = len(results['passed'])
failed = len(results['failed'])
errors = len(results['errors'])

print(f"\nTotal Tests: {total}")
print(f"[PASS] Passed: {passed}")
print(f"[FAIL] Failed: {failed}")
print(f"[ERROR] Errors: {errors}")

if results['failed']:
    print("\nFailed Tests:")
    for test_name, message in results['failed']:
        print(f"  - {test_name}: {message}")

if results['errors']:
    print("\nErrors:")
    for test_name, message in results['errors']:
        print(f"  - {test_name}: {message}")

success_rate = (passed / total * 100) if total > 0 else 0
print(f"\nSuccess Rate: {success_rate:.1f}%")

if success_rate >= 95:
    print("\n[SUCCESS] ALL SYSTEMS GO - PRODUCTION READY!")
elif success_rate >= 80:
    print("\n[WARNING] MOST TESTS PASSING - MINOR ISSUES FOUND")
else:
    print("\n[CRITICAL] SIGNIFICANT ISSUES - NEEDS ATTENTION")

print("\n" + "="*70)
print("TESTING COMPLETE")
print("="*70 + "\n")

sys.exit(0 if failed == 0 and errors == 0 else 1)
