# Phase 1 Implementation Plan

**Duration:** 2 weeks | **Effort:** 35 hours | **Team:** 1-2 developers

## Overview
Phase 1 focuses on progress visualization and task urgency (highest ROI improvements).

## Breakdown & Timeline

### Week 1: Data Model & Backend (15 hours)

#### Day 1-2: Due Dates & Status System (8 hours)
- [ ] Add `due_date` field to Stage model
- [ ] Add `status` enum (pending, in_progress, completed, overdue)
- [ ] Create migration for both fields
- [ ] Add manager methods for status calculation
- [ ] Create fixtures for testing

**Files to modify:**
- `core/models.py` - Add Stage fields
- `core/migrations/` - New migration
- `core/managers.py` - Add status calculation logic

**Estimated Effort:** 8 hours

---

#### Day 3-5: Reminder System Architecture (7 hours)
- [ ] Create `Reminder` model (task_id, recipient, scheduled_date, status, sent_at)
- [ ] Create migration
- [ ] Setup Celery beat schedule (if not already done)
- [ ] Create reminder signal handlers
- [ ] Create email template manager

**Files to create:**
- `core/models/reminder.py` - Reminder model
- `core/tasks.py` - Celery tasks for reminder dispatch
- `core/signals.py` - Signal handlers for task creation
- `core/migrations/` - New migration

**Files to modify:**
- `settings.py` - Configure Celery beat schedule

**Estimated Effort:** 7 hours

---

### Week 2: Frontend & Templates (20 hours)

#### Day 1-2: Progress Visualization (12 hours)
- [ ] Create progress bar component
- [ ] Create status badge component (✓ green, ⏳ blue, ○ gray, ⚠️ red)
- [ ] Create checklist view template
- [ ] Update employee detail page
- [ ] Add progress calculation to view
- [ ] Mobile-optimize progress bar
- [ ] Add color scheme constants

**Files to create:**
- `templates/components/progress_bar.html` - Progress bar component
- `templates/components/status_badge.html` - Status badge component
- `templates/components/task_checklist.html` - Checklist view

**Files to modify:**
- `templates/admin/employee_detail.html` - Integrate progress/checklist
- `core/views/admin_views.py` - Add progress calculation
- `static/css/components.css` - Component styles
- `static/css/colors.css` - Status color definitions

**Estimated Effort:** 12 hours

---

#### Day 3-5: Dashboard Redesign & Mobile (8 hours)
- [ ] Restructure new hire dashboard (progress top, tasks middle, team bottom)
- [ ] Add "Next Steps" section with top 3 actionable tasks
- [ ] Implement mobile-first responsive layout
- [ ] Fix touch targets (44x44px minimum)
- [ ] Add welcome greeting
- [ ] Mobile menu optimization

**Files to modify:**
- `templates/employee/home.html` - New hire dashboard
- `templates/admin/dashboard.html` - Admin dashboard
- `static/css/dashboard.css` - Dashboard styles
- `static/css/mobile.css` - Mobile optimizations

**Estimated Effort:** 8 hours

---

## Implementation Sequence

### Priority Order (Start with these):

1. **Due Dates Model** (Day 1-2)
   - Foundational for reminders and progress
   - Must be done first
   - 8 hours

2. **Progress Visualization** (Day 3-4)
   - High visual impact
   - Doesn't depend on reminders
   - 12 hours

3. **Reminder System** (Day 5 onwards)
   - Complex but parallelizable
   - Can work while frontend is being polished
   - 7 hours

4. **Dashboard Redesign** (Week 2)
   - Uses progress component
   - Uses task list
   - 8 hours

---

## Database Changes

### Stage Model Addition
```python
class Stage(models.Model):
    # ... existing fields ...
    due_date_days = IntegerField(default=7)  # Days from creation
    
    @property
    def actual_due_date(self, employee):
        return employee.created_at + timedelta(days=self.due_date_days)

    @property
    def is_overdue(self, employee):
        return timezone.now() > self.actual_due_date(employee)
    
    @property
    def days_remaining(self, employee):
        delta = self.actual_due_date(employee) - timezone.now()
        return delta.days
    
    def get_status(self, employee):
        if employee.status == self.status:
            return 'completed'
        elif self.is_overdue(employee):
            return 'overdue'
        elif employee.current_stage == self:
            return 'in_progress'
        else:
            return 'pending'
```

### Reminder Model
```python
class Reminder(models.Model):
    REMINDER_TYPES = [
        ('due_soon', '3 Days Before Due'),
        ('due_today', 'Due Today'),
        ('overdue', 'Overdue'),
    ]
    
    employee = ForeignKey(Employee, on_delete=models.CASCADE)
    stage = ForeignKey(Stage, on_delete=models.CASCADE)
    reminder_type = CharField(max_length=20, choices=REMINDER_TYPES)
    scheduled_date = DateTimeField()
    sent_at = DateTimeField(null=True, blank=True)
    status = CharField(max_length=20, default='pending')  # pending, sent, failed
    
    class Meta:
        unique_together = ['employee', 'stage', 'reminder_type']
```

---

## UI Components to Build

### 1. Progress Bar
```html
<div class="progress-section">
  <h6>Onboarding Progress</h6>
  <div class="progress" style="height: 24px;">
    <div class="progress-bar bg-success" style="width: 45%">
      <span class="progress-text">45% Complete</span>
    </div>
  </div>
  <p class="text-muted small">2 of 5 stages completed</p>
</div>
```

### 2. Status Badge Component
```html
<span class="badge" data-status="completed">✓ Complete</span>
<span class="badge" data-status="in_progress">⏳ In Progress</span>
<span class="badge" data-status="pending">○ Pending</span>
<span class="badge" data-status="overdue">⚠ Overdue</span>
```

### 3. Task Checklist
```html
<div class="task-checklist">
  <h6>Your Tasks</h6>
  <ul class="checklist">
    <li class="completed">
      <i class="bi bi-check-circle-fill"></i>
      <span>Complete Medical Documents</span>
      <small>Completed 2 days ago</small>
    </li>
    <li class="in-progress">
      <i class="bi bi-hourglass-split"></i>
      <span>Pre-Onboarding Forms</span>
      <small>Due in 3 days • <a href="#">Start</a></small>
    </li>
    <li class="pending">
      <i class="bi bi-circle"></i>
      <span>Onboarding Training</span>
      <small>Due in 7 days</small>
    </li>
  </ul>
</div>
```

---

## Testing Plan

### Unit Tests
- [ ] Test due_date calculations
- [ ] Test status determination logic
- [ ] Test reminder scheduling
- [ ] Test progress percentage calculation

### Integration Tests
- [ ] Create employee → check progress bar shows 0%
- [ ] Complete stage → check progress updates
- [ ] Check reminders scheduled correctly
- [ ] Check overdue status calculation

### Manual Testing
- [ ] Test progress bar on desktop (1920px, 1280px)
- [ ] Test progress bar on tablet (768px)
- [ ] Test progress bar on mobile (375px)
- [ ] Test touch targets (44x44px minimum)
- [ ] Test badge colors on different backgrounds
- [ ] Test checklist expand/collapse

---

## Rollout Plan

### Step 1: Local Development
- Implement and test locally
- Get feedback from team
- Fix any issues

### Step 2: Staging
- Deploy to staging environment
- Full QA testing
- User acceptance testing with real HR admin

### Step 3: Production
- Deploy during low-traffic window
- Monitor for errors
- Be ready to rollback

---

## Rollback Plan

If issues occur:
1. Revert migrations: `python manage.py migrate core <previous_migration>`
2. Restore previous code from git
3. Restart services
4. Verify dashboard and employee detail page still work

---

## Success Metrics

After Phase 1 completion, track:
- ✅ Progress bar visible on 100% of employee detail pages
- ✅ Reminders sent for 100% of overdue tasks
- ✅ Mobile interface tested on 3+ devices
- ✅ Zero 500 errors related to progress calculation
- ✅ Page load time < 2 seconds (employee detail page)

---

## Dependencies & Prerequisites

### Required
- [ ] Celery configured in project
- [ ] Redis running for Celery broker
- [ ] Email sending configured (for reminders)
- [ ] Frontend build process working

### Optional
- [ ] Design system colors finalized
- [ ] Bootstrap 5 version confirmed
- [ ] Mobile testing devices available

---

## Questions Before Starting

1. **Due date strategy**: Should due dates be:
   - A) Fixed days (7 days per stage for everyone)
   - B) Customizable per role/department
   - C) Both (default + override)
   
   **Recommendation**: Start with A (simple), add B in Phase 2

2. **Reminder timing**: Should we send:
   - A) Email only
   - B) Email + Slack/Teams (if integrated)
   - C) Email + dashboard notification
   
   **Recommendation**: Start with A (email), add B in Phase 2

3. **Mobile priority**: Should we:
   - A) Mobile-optimize in Phase 1
   - B) Desktop-first, mobile in Phase 2
   
   **Recommendation**: Fix critical touch targets in Phase 1, full mobile redesign in Phase 2

4. **Effort realism**: 35 hours is 1 week at full-time. Realistic timeline:
   - With 1 developer: 2-3 weeks (part-time)
   - With 2 developers: 1-2 weeks (full-time)
   
   **Recommendation**: 2 devs working 5-6 days = 1.5-2 weeks realistic

---

## Files to Create
```
core/
  migrations/
    XXXX_add_due_dates_to_stage.py
    XXXX_create_reminder_model.py
  models/
    reminder.py (new)
  tasks.py (add reminder tasks)
  signals.py (create if not exists)

templates/
  components/
    progress_bar.html (new)
    status_badge.html (new)
    task_checklist.html (new)

static/
  css/
    components.css (new)
    colors.css (new)
    mobile.css (new)
```

## Files to Modify
```
core/models.py
core/views/admin_views.py
templates/admin/employee_detail.html
templates/employee/home.html
templates/admin/dashboard.html
settings.py
```

---

**Status**: Ready to start  
**Start Date**: 2026-06-18  
**Expected Completion**: 2026-07-02
