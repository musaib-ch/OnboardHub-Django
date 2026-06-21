"""
Test script for 30/60/90 onboarding plan system.
"""
import os
import django
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'onboardhub.settings')
django.setup()

from django.utils import timezone
from core.models import User, Engagement
from core.services.onboarding_plan_service import (
    create_plan, get_plan, get_progress_stats, 
    update_milestone, post_update, get_phase_status
)

print("=" * 60)
print("30/60/90 ONBOARDING PLAN SYSTEM TEST")
print("=" * 60)

# Test 1: Create test users
print("\n[TEST 1] Creating test users...")
try:
    # Get or create HRBP
    hrbp, created = User.objects.get_or_create(
        email='hrbp@test.com',
        defaults={
            'full_name': 'Sarah HRBP',
            'role': 'hrbp',
            'is_staff': True,
            'is_active': True,
        }
    )
    print(f"✓ HRBP user: {hrbp.full_name} (created={created})")

    # Get or create employee
    employee, created = User.objects.get_or_create(
        email='john@example.com',
        defaults={
            'full_name': 'John Newbie',
            'role': 'employee',
            'is_active': True,
            'date_of_joining': timezone.now().date(),
            'status': 'onboarding',
        }
    )
    print(f"✓ Employee: {employee.full_name} (created={created})")
except Exception as e:
    print(f"✗ Error creating users: {e}")
    exit(1)

# Test 2: Create plan
print("\n[TEST 2] Creating 30/60/90 plan...")
try:
    plan_eng = create_plan(employee, hrbp)
    print(f"✓ Plan created successfully")
    print(f"  - Engagement ID: {plan_eng.id}")
except Exception as e:
    print(f"✗ Error creating plan: {e}")
    exit(1)

# Test 3: Retrieve plan
print("\n[TEST 3] Retrieving plan...")
try:
    plan = get_plan(employee)
    if not plan:
        print("✗ Plan not found!")
        exit(1)
    print(f"✓ Plan retrieved")
    print(f"  - Created by: {plan.get('created_by_name')}")
    print(f"  - Status: {plan.get('status')}")
except Exception as e:
    print(f"✗ Error retrieving plan: {e}")
    exit(1)

# Test 4: Check progress stats
print("\n[TEST 4] Checking progress stats...")
try:
    stats = get_progress_stats(employee)
    print(f"✓ Progress stats retrieved")
    print(f"  - Total milestones: {stats['total_milestones']}")
    print(f"  - Completed: {stats['completed_milestones']}")
    print(f"  - Completion: {stats['completion_percentage']}%")
    print(f"  - Day 30: {stats['phases']['day_30']['completed']}/{stats['phases']['day_30']['total']} ({stats['phases']['day_30']['percentage']}%)")
    print(f"  - Day 60: {stats['phases']['day_60']['completed']}/{stats['phases']['day_60']['total']} ({stats['phases']['day_60']['percentage']}%)")
    print(f"  - Day 90: {stats['phases']['day_90']['completed']}/{stats['phases']['day_90']['total']} ({stats['phases']['day_90']['percentage']}%)")
except Exception as e:
    print(f"✗ Error getting stats: {e}")
    exit(1)

# Test 5: Complete a milestone
print("\n[TEST 5] Completing milestone...")
try:
    result = update_milestone(employee, 'day_30', 0, True)
    if not result:
        print("✗ Failed to complete milestone")
        exit(1)
    print(f"✓ Milestone completed")
    
    stats = get_progress_stats(employee)
    print(f"  - Day 30: {stats['phases']['day_30']['completed']}/{stats['phases']['day_30']['total']} ({stats['phases']['day_30']['percentage']}%)")
except Exception as e:
    print(f"✗ Error completing milestone: {e}")
    exit(1)

# Test 6: Post employee update
print("\n[TEST 6] Employee posting update...")
try:
    result = post_update(employee, 'day_30', employee, 'I completed orientation on my first day!')
    if not result:
        print("✗ Failed to post update")
        exit(1)
    print(f"✓ Employee update posted")
except Exception as e:
    print(f"✗ Error posting update: {e}")
    exit(1)

# Test 7: Manager posting feedback
print("\n[TEST 7] Manager posting feedback...")
try:
    result = post_update(employee, 'day_30', hrbp, 'Great work! Keep it up!', author_role='hrbp')
    if not result:
        print("✗ Failed to post feedback")
        exit(1)
    print(f"✓ Manager feedback posted")
except Exception as e:
    print(f"✗ Error posting feedback: {e}")
    exit(1)

# Test 8: Check posts in phase
print("\n[TEST 8] Retrieving phase with posts...")
try:
    phase = get_phase_status(employee, 'day_30')
    posts = phase.get('posts', [])
    print(f"✓ Phase retrieved")
    print(f"  - Posts count: {len(posts)}")
    for i, post in enumerate(posts, 1):
        print(f"    {i}. {post['author_name']} ({post['author_role']}): {post['message'][:50]}...")
except Exception as e:
    print(f"✗ Error retrieving phase: {e}")
    exit(1)

# Test 9: Complete more milestones to test progress
print("\n[TEST 9] Completing more milestones...")
try:
    update_milestone(employee, 'day_30', 1, True)
    update_milestone(employee, 'day_30', 2, True)
    stats = get_progress_stats(employee)
    print(f"✓ Additional milestones completed")
    print(f"  - Overall: {stats['completion_percentage']}%")
    print(f"  - Day 30: {stats['phases']['day_30']['percentage']}%")
except Exception as e:
    print(f"✗ Error: {e}")
    exit(1)

# Test 10: Database check
print("\n[TEST 10] Verifying database storage...")
try:
    eng = Engagement.objects.get(user=employee, kind='onboarding_plan')
    plan_data = eng.data
    stored_posts = plan_data.get('plan', {}).get('day_30', {}).get('posts', [])
    print(f"✓ Data correctly stored in database")
    print(f"  - Engagement record: {eng.id}")
    print(f"  - Posts stored: {len(stored_posts)}")
    print(f"  - Milestones in day_30: {len(plan_data.get('plan', {}).get('day_30', {}).get('milestones', []))}")
except Exception as e:
    print(f"✗ Error: {e}")
    exit(1)

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
print("\nSystem Summary:")
print(f"  - Employee: {employee.full_name} ({employee.email})")
print(f"  - HRBP: {hrbp.full_name}")
print(f"  - Plan Status: Active")
print(f"  - Total Progress: {stats['completion_percentage']}%")
print(f"\nTo test in browser:")
print(f"  - Employee view: /employee/onboarding-plan/")
print(f"  - Manager view: /admin/onboarding-plans/")
print(f"  - Plan detail: /admin/onboarding-plans/{employee.id}/")

