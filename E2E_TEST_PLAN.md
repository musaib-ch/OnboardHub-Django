# End-to-End Testing Plan
## Complete Workflow Verification

**Date**: 2026-06-20  
**Status**: Ready to Test  
**Total Test Cases**: 20+

---

## PHASE 1: SETUP TEST DATA ✅

### Create 3 Locations & 3 Departments
```
Location 1: New York (US-NY)
Location 2: London (UK-LON)
Location 3: Dubai (UAE-DXB)

Department 1: Engineering
Department 2: Human Resources
Department 3: Sales
```

### Create 3 Test Employees

| Name | Email | Dept | Location | Status |
|------|-------|------|----------|--------|
| **Emp1** John Engineer | john.eng@test.com | Engineering | New York | New |
| **Emp2** Sarah HR | sarah.hr@test.com | HR | London | New |
| **Emp3** Mike Sales | mike.sales@test.com | Sales | Dubai | New |

---

## PHASE 2: EMPLOYEE CREATION TEST

### Test Case 1: Create Employee via Admin
**URL**: `/admin/employees/`
```
Step 1: Click "Add Employee"
Step 2: Fill form:
  - Name: John Engineer
  - Email: john.eng@test.com
  - Employee ID: ENG-001
  - Department: Engineering
  - Date of Joining: 2026-06-20
  - Position: Software Engineer
Step 3: Click Save
Expected: Employee created, redirects to profile
```

**Verify**: 
- [ ] Employee appears in employee list
- [ ] Profile page loads
- [ ] Status shows "pending"
- [ ] Onboarding journey visible

---

## PHASE 3: MEDICAL FLOW TEST

### Test Case 2: Submit Medical as Employee
**URL**: `/employee/medical/`

**As John Engineer**:
```
Step 1: Log in as john.eng@test.com
Step 2: Go to Employee Home → Medical
Step 3: Upload medical document (PDF or image)
Step 4: Fill medical form if required
Step 5: Click "Submit"
Expected: Submission captured, status changes to "submitted"
```

**Verify**:
- [ ] Medical form loads
- [ ] File upload works
- [ ] Form validation works
- [ ] Submission saved in database
- [ ] Status changes

---

### Test Case 3: Medical Approver Reviews & Approves
**URL**: `/admin/medical/review/`

**As Medical Approver**:
```
Step 1: Log in as medical@onboardhub.local
Step 2: Go to Medical Review Queue
Step 3: See John Engineer's submission
Step 4: Click to review
Step 5: Add note: "Medical check passed"
Step 6: Click "Approve Medical"
Expected: Status changes to "approved", employee notified
```

**Verify**:
- [ ] Medical approver sees submissions
- [ ] Can view documents
- [ ] Approval button works
- [ ] Employee gets email notification
- [ ] Status updates correctly
- [ ] Dashboard updates

---

## PHASE 4: PRE-ONBOARDING FLOW TEST

### Test Case 4: Submit Pre-Onboarding Form
**URL**: `/employee/pre-onboarding/`

**As John Engineer**:
```
Step 1: Go to Pre-Onboarding section
Step 2: Fill text fields:
  - Full Name: John Engineer
  - Emergency Contact: Jane Engineer
  - Phone: +1-555-0001
Step 3: Attach documents:
  - Upload Resume (PDF)
  - Upload ID Proof (Image)
Step 4: Click "Submit"
Expected: Form saved, HRBP can review
```

**Verify**:
- [ ] Form loads correctly
- [ ] Text fields save
- [ ] File uploads work (PDF, images)
- [ ] Required fields validated
- [ ] Submission appears in admin queue

---

### Test Case 5: HRBP Reviews & Approves Pre-Onboarding
**URL**: `/admin/employees/{id}/`

**As HRBP (Sarah HR)**:
```
Step 1: Log in as hrbp@onboardhub.local
Step 2: Go to People > Employees (filtered to your dept)
Step 3: Click on John Engineer (in Engineering dept)
Step 4: Scroll to "Current Stage" → "Awaiting Your Review"
Step 5: Add note: "Documents look good"
Step 6: Click "Approve"
Expected: Employee advances to next stage
```

**Verify**:
- [ ] HRBP sees only their department
- [ ] Approval interface visible
- [ ] Note saves
- [ ] Employee advances automatically
- [ ] Email sent to employee

---

## PHASE 5: ONBOARDING FORMS TEST

### Test Case 6: Submit Onboarding Forms
**URL**: `/employee/onboarding/`

**As John Engineer**:
```
Step 1: Go to Onboarding section
Step 2: Fill onboarding form:
  - Confirm Contact Info
  - Confirm Salary Details
  - Accept Company Policy (checkbox)
  - Upload signed agreement
Step 3: Click "Submit"
Expected: Form submitted, visible in dashboard
```

**Verify**:
- [ ] Form renders
- [ ] File upload works
- [ ] Checkbox saves
- [ ] Email sent on submission
- [ ] Admin sees submission

---

### Test Case 7: Admin/HRBP Approves Onboarding
```
Step 1: As admin/HRBP, go to employee profile
Step 2: See "Onboarding" in Current Stage section
Step 3: Review submission
Step 4: Approve with comment
Expected: Employee advances to next stage
```

---

## PHASE 6: POST-ONBOARDING FORMS TEST

### Test Case 8: Submit Post-Onboarding Forms
**URL**: `/employee/post-onboarding/`

**As John Engineer**:
```
Step 1: Go to Post-Onboarding section
Step 2: Fill feedback form:
  - How was onboarding? (Rating)
  - Any feedback? (Text)
  - Attach photos/documents
Step 3: Click "Submit"
Expected: Form saved
```

**Verify**:
- [ ] Form appears
- [ ] File attachments work
- [ ] Rating/feedback saves
- [ ] Admin can view

---

## PHASE 7: ORIENTATION SETUP & ASSIGNMENT

### Test Case 9: Create Orientation Session
**URL**: `/sessions/create/`

**As Admin/HRBP**:
```
Step 1: Go to Live Sessions
Step 2: Click "Create Session"
Step 3: Fill details:
  - Title: Company Orientation
  - Date: 2026-06-25
  - Time: 10:00 AM
  - Duration: 2 hours
  - Description: Welcome to company
  - Enable Zoom: Yes
Step 4: Click "Create"
Expected: Session created, Zoom link generated
```

**Verify**:
- [ ] Session appears in dashboard
- [ ] Zoom link auto-generated
- [ ] Email sent to admins
- [ ] Time displays correctly

---

### Test Case 10: Assign Orientation to Employees
**URL**: `/admin/content/orientation/`

**As Admin**:
```
Step 1: Go to Admin > Onboarding > Orientation
Step 2: Click "Assign" or go to employee profile
Step 3: Select orientation session
Step 4: Click "Assign to Employee"
Expected: Employee sees session, receives email
```

**Verify**:
- [ ] Assignment saved
- [ ] Employee receives email with Zoom link
- [ ] Session shows in employee dashboard
- [ ] Registration link in email works

---

## PHASE 8: TRAINING & LEARNING PATHS

### Test Case 11: Create Learning Path
**URL**: `/admin/training/paths/`

**As Admin**:
```
Step 1: Go to Learning > Learning Paths
Step 2: Click "Create Path"
Step 3: Fill details:
  - Title: Onboarding Training
  - Description: Training for new employees
  - Add modules: 
    * Module 1: Company Basics (PDF)
    * Module 2: Systems Training (Video)
    * Module 3: Quiz
Step 4: Click "Save"
Expected: Path created
```

**Verify**:
- [ ] Path appears in list
- [ ] Can edit/delete
- [ ] Modules display correctly

---

### Test Case 12: Assign Training to Employee
**URL**: `/admin/training/assignments/`

**As Admin/HRBP**:
```
Step 1: Go to Training > Assignments
Step 2: Click "Assign Training"
Step 3: Select employees: John, Sarah, Mike
Step 4: Select training path: Onboarding Training
Step 5: Click "Assign"
Expected: All 3 employees assigned
```

**Verify**:
- [ ] Bulk assignment works
- [ ] Employees receive emails
- [ ] Training appears in "My Learning"
- [ ] Progress tracking starts

---

### Test Case 13: Employee Takes Training
**URL**: `/learn/my-learning/`

**As John Engineer**:
```
Step 1: Go to My Learning
Step 2: Click on "Onboarding Training"
Step 3: Go through modules:
  - Read Module 1 (Company Basics)
  - Watch Module 2 (Systems Training)
  - Take Quiz Module 3
Step 4: Complete all modules
Expected: Certificate generated
```

**Verify**:
- [ ] Modules load
- [ ] Progress saves
- [ ] Quiz works
- [ ] Certificate appears
- [ ] Dashboard updates

---

## PHASE 9: DASHBOARDS & VIEWS

### Test Case 14: Admin Dashboard
**URL**: `/admin/dashboard/`

**As Super Admin**:
```
View and verify:
- [ ] Total Employees: 3
- [ ] In Progress: 3
- [ ] Joining in 10 Days: 3 (if today is 2026-06-20)
- [ ] Learning Paths: 1
- [ ] Active Enrollments: 3
- [ ] Recent Employees table shows all 3
- [ ] Click tiles to filter
```

**Expected Tiles**:
| Metric | Expected Value |
|--------|----------------|
| Total Employees | 3 |
| In Progress | 3 |
| Completed | 0 |
| On Hold | 0 |
| Joining in 10 Days | 3 |
| Learning Paths | 1+ |
| Active Enrollments | 3+ |
| Completed Trainings | 0 |
| Overdue | 0 |

---

### Test Case 15: Analytics Dashboard
**URL**: `/admin/analytics/`

**As Admin/HRBP**:
```
Verify:
- [ ] Completion rates chart loads
- [ ] Stage progress chart shows
- [ ] Department breakdown visible
- [ ] Can filter by department
- [ ] Export button works
- [ ] Data accurate
```

---

### Test Case 16: HRBP Dashboard (Department View)
**URL**: `/admin/dashboard/`

**As HRBP (Sarah HR)**:
```
Verify:
- [ ] Only sees Engineering employees (3)
- [ ] Cannot see other departments
- [ ] Can view their team's progress
- [ ] Can approve their team's submissions
- [ ] Analytics shows only their dept
- [ ] Assignments show only their scope
```

---

### Test Case 17: Medical Approver Dashboard
**URL**: `/admin/medical/review/`

**As Medical Approver**:
```
Verify:
- [ ] Medical queue shows 3 submissions
- [ ] Can view documents
- [ ] Can approve/reject
- [ ] Cannot see training or forms
- [ ] Medical metrics show correctly
```

---

### Test Case 18: Employee Dashboard
**URL**: `/employee/home/`

**As John Engineer**:
```
Verify:
- [ ] Onboarding progress: 50% complete
- [ ] Current stage: Onboarding
- [ ] Next action: Complete onboarding forms
- [ ] Upcoming orientation session shows
- [ ] My Learning shows assigned training
- [ ] Notifications show updates
```

---

## PHASE 10: EMAIL & NOTIFICATIONS

### Test Case 19: Email Verification
**Check Email Logs**: `/admin/settings/email-logs/`

**Verify emails sent for**:
- [ ] Employee created (welcome email)
- [ ] Medical submitted (admin notification)
- [ ] Medical approved (employee notification)
- [ ] Pre-onboarding submitted (HRBP notification)
- [ ] Pre-onboarding approved (employee notification)
- [ ] Onboarding submitted (admin notification)
- [ ] Orientation assigned (employee with Zoom link)
- [ ] Training assigned (employee with course link)
- [ ] Quiz reminder emails

**Check Email Format**:
- [ ] Subject lines clear
- [ ] Body has proper formatting (bold, lists, etc. from rich editor)
- [ ] Zoom links included in session emails
- [ ] Action buttons clickable
- [ ] No broken links

---

### Test Case 20: In-App Notifications
**Check Notifications Bell**: `/notifications/`

**Verify notifications for**:
- [ ] Form submissions
- [ ] Approvals
- [ ] Assignments
- [ ] New sessions
- [ ] Upcoming deadlines
- [ ] Task reminders

---

## PHASE 11: ZOOM INTEGRATION

### Test Case 21: Zoom Invite Links
**In Session Email**:
```
Employee receives email with:
- [ ] Session title: Company Orientation
- [ ] Date and time
- [ ] Zoom meeting link: zoom.us/j/...
- [ ] Join instructions
- [ ] Reminder button (24hrs before)
- [ ] Recording link (after session)
```

---

### Test Case 22: Zoom Settings
**URL**: `/admin/settings/zoom/`

**Verify**:
- [ ] Zoom OAuth form loads
- [ ] Can enter credentials
- [ ] Test Connection button works
- [ ] Callback URL displays: `http://127.0.0.1:8000/auth/zoom/callback/`
- [ ] Instructions clear
- [ ] Status shows "Connected" after credentials saved

---

## PHASE 12: 30/60/90 DAY PLANS

### Test Case 23: Create 30/60/90 Plan
**URL**: `/admin/onboarding-plans/`

**As Manager/Admin**:
```
Step 1: Go to 30/60/90 Plans
Step 2: Click "Create Plan" for John Engineer
Step 3: Fill:
  - 30 Day Goals:
    * Learn systems: Complete by 2026-07-20
    * Shadow team: Complete by 2026-07-15
  - 60 Day Goals:
    * Independent tasks
    * Project assignments
  - 90 Day Goals:
    * Full responsibility
Step 4: Click "Save"
Expected: Plan created, milestones tracked
```

**Verify**:
- [ ] Plan saves
- [ ] Milestones show in dashboard
- [ ] Progress trackable
- [ ] Employee can update progress
- [ ] Feedback can be added

---

## PHASE 13: NAVIGATION & ACCESSIBILITY

### Test Case 24: Navigation Menus
**Verify all users can access**:

**Super Admin**:
- [ ] Dashboard
- [ ] Analytics
- [ ] People (Employees, Users)
- [ ] Onboarding (Forms, Documents, Medical, Orientation, Training)
- [ ] Learning (Paths, Assignments)
- [ ] Live Sessions
- [ ] Setup (All options + Zoom)
- [ ] Medical Review
- [ ] Mobile responsive

**Admin**:
- [ ] Same as Super Admin (except Users/Roles/Email SMTP)
- [ ] Can see Zoom settings
- [ ] Can create sessions

**HRBP**:
- [ ] People (only their dept)
- [ ] Analytics (filtered)
- [ ] Live Sessions
- [ ] Learning
- [ ] Cannot see Setup menu

**Medical Approver**:
- [ ] Medical Review
- [ ] Medical Requirements
- [ ] Cannot see most other menus

**Employee**:
- [ ] Home
- [ ] Medical
- [ ] Pre-Onboarding
- [ ] Onboarding
- [ ] Post-Onboarding
- [ ] My Learning
- [ ] 30/60/90 Plans
- [ ] Notifications

---

## TEST EXECUTION CHECKLIST

### Before Testing
- [ ] Database clean (or backup created)
- [ ] Server running on http://127.0.0.1:8000
- [ ] Test email configured (logs viewable)
- [ ] Zoom credentials configured (or skip Zoom tests)

### During Testing
- [ ] Note any errors in browser console
- [ ] Check Django logs for errors
- [ ] Verify database updates
- [ ] Take screenshots of key flows

### After Testing
- [ ] Document any bugs found
- [ ] Note missing features
- [ ] Performance observations
- [ ] UI/UX improvements

---

## CRITICAL PATH TEST (Quick 15-min validation)

If short on time, run this path:
1. Create 1 employee (John)
2. Submit medical as John
3. Approve medical as Medical Approver
4. Approve pre-onboarding as HRBP
5. Assign training
6. Check Dashboard metrics
7. Check email log

---

## TEST DATA CLEANUP

```sql
-- After testing, cleanup:
DELETE FROM core_formresponse WHERE employee_id IN (
  SELECT id FROM core_user WHERE email LIKE '%@test.com'
);
DELETE FROM core_user WHERE email LIKE '%@test.com';
DELETE FROM core_orgunit WHERE name IN ('Engineering', 'HR', 'Sales');
```

---

## SUCCESS CRITERIA

✅ All 23 test cases pass  
✅ No critical errors  
✅ All emails send correctly  
✅ All dashboards display accurate data  
✅ Role-based access enforced  
✅ Forms save and validate  
✅ File uploads work  
✅ Zoom links generate  
✅ Notifications trigger  

**Status**: Ready to test! 🚀

