# Quick E2E Testing Guide
## Ready-to-Test OnboardHub Platform

**Last Updated**: 2026-06-20  
**Test Status**: ✅ READY TO START  
**Estimated Time**: 60-90 minutes for full workflow

---

## WHAT'S BEEN SET UP

✅ **3 Test Employees Created**
- John Engineer (john.eng@test.com) - Engineering Dept
- Sarah HR (sarah.hr@test.com) - HR Dept
- Mike Sales (mike.sales@test.com) - Sales Dept

✅ **3 Locations Created**
- New York (US-NY)
- London (UK-LON)  
- Dubai (UAE-DXB)

✅ **3 Departments Created**
- Engineering (ENG)
- Human Resources (HR)
- Sales (SAL)

✅ **Staff Accounts Created**
- HRBP: hrbp@test.com
- Medical Approver: medical@test.com
- Super Admin: admin@onboardhub.local

✅ **All Features Ready**
- Medical submission & approval
- Pre-onboarding, onboarding, post-onboarding forms
- Live sessions & Zoom integration
- Training paths & learning
- Rich text editors
- Email templates with formatting
- Role-based dashboards
- Orientation management

---

## START TESTING

### Step 0: Start Server
```bash
cd C:\Users\H&M\Desktop\OnboardHub-Django
python manage.py runserver
```
Open: http://127.0.0.1:8000

---

## TESTING WORKFLOW (30 mins - Critical Path)

### 1. LOGIN & VERIFY DASHBOARD (2 min)
**URL**: http://127.0.0.1:8000/admin/dashboard/

**Login as**: admin@onboardhub.local

**Verify**:
- [ ] Dashboard loads
- [ ] Total Employees: 3
- [ ] Joining in 10 Days: 3
- [ ] Recent employees shows all 3
- [ ] Live Sessions visible in menu

---

### 2. SUBMIT MEDICAL (5 min)
**URL**: http://127.0.0.1:8000/login/

**Login as**: john.eng@test.com (Password: testpass123)

**Steps**:
1. Click Medical in left menu
2. Upload a PDF or image (any file)
3. Click Submit
4. Confirm submission saved

**Verify Medical Email**:
- Go to http://127.0.0.1:8000/admin/settings/email-logs/
- Should see email to medical@onboardhub.local

---

### 3. APPROVE MEDICAL (3 min)
**URL**: http://127.0.0.1:8000/login/

**Login as**: medical@test.com (Password: testpass123)

**Steps**:
1. Go to Medical Review queue
2. Click on John Engineer
3. Click "Approve Medical"
4. Add comment: "Medical check passed"
5. Submit

**Verify**:
- [ ] Status changes to "approved"
- [ ] Email sent to John
- [ ] Dashboard updates

---

### 4. SUBMIT PRE-ONBOARDING (5 min)
**Login as**: john.eng@test.com

**Steps**:
1. Go to Pre-Onboarding in left menu
2. Fill text form:
   - Emergency Contact: Jane Engineer
   - Phone: +1-555-0001
3. Upload file (any PDF/image)
4. Click Submit

**Verify**:
- [ ] Form saves
- [ ] Email sent to HRBP

---

### 5. HRBP APPROVES PRE-ONBOARDING (3 min)
**Login as**: hrbp@test.com (Password: testpass123)

**Steps**:
1. Go to People > Employees
2. Click on John Engineer
3. Scroll to "Current Stage" section
4. See "Awaiting Your Review"
5. Add comment: "Documents approved"
6. Click "Approve"

**Verify**:
- [ ] John's status advances
- [ ] Email confirmation sent
- [ ] Dashboard updates

---

### 6. SUBMIT ONBOARDING FORMS (5 min)
**Login as**: john.eng@test.com

**Steps**:
1. Go to Onboarding
2. Fill form
3. Upload any file
4. Check "Accept Policy" checkbox
5. Click Submit

**Verify**:
- [ ] Form saves
- [ ] Admin sees submission

---

### 7. ADMIN APPROVES ONBOARDING (2 min)
**Login as**: admin@onboardhub.local

**Steps**:
1. Go to Employees > John Engineer
2. See onboarding submission
3. Approve with comment
4. Submit

**Verify**:
- [ ] Status changes
- [ ] Email sent
- [ ] Progress visible on dashboard

---

### 8. CREATE & ASSIGN ORIENTATION (5 min)
**Login as**: admin@onboardhub.local

**Steps**:
1. Go to Live Sessions (main menu)
2. Click "Create Session"
3. Fill:
   - Title: Company Orientation
   - Date: 2026-06-25
   - Time: 10:00 AM
   - Duration: 2 hours
   - Enable Zoom: Yes
4. Click Create

**Then Assign**:
1. Go to Employees > John Engineer > Orientation (in profile)
2. Click "Assign Session"
3. Select the session created above
4. Click "Assign"

**Verify**:
- [ ] Session created
- [ ] Zoom link generates
- [ ] Email sent to John with Zoom link
- [ ] Session shows in employee dashboard

---

### 9. CREATE & ASSIGN TRAINING (5 min)
**Login as**: admin@onboardhub.local

**Steps**:
1. Go to Learning > Learning Paths
2. Click "Create Path"
3. Fill:
   - Title: Onboarding Training
   - Add 1-2 modules (can be text)
4. Click Save

**Then Assign**:
1. Go to Learning > Assignments
2. Click "Assign Training"
3. Select all 3 employees
4. Select the training path
5. Click "Assign"

**Verify**:
- [ ] Path created
- [ ] All 3 employees assigned
- [ ] Emails sent to all
- [ ] Shows in "My Learning" for employees

---

### 10. CHECK DASHBOARDS (5 min)

**Admin Dashboard**:
- Login as admin@onboardhub.local
- Verify all metrics accurate
- Try clicking tiles to filter

**HRBP Dashboard**:
- Login as hrbp@test.com
- Verify only sees Engineering dept
- Check analytics

**Employee Dashboard**:
- Login as john.eng@test.com
- Check progress %
- See upcoming orientation
- See assigned training

---

## FULL TESTING WORKFLOW (60-90 mins)

For comprehensive testing, follow **E2E_TEST_PLAN.md** which includes:
- All 23 test cases
- Edge cases
- Email verification
- Zoom integration
- 30/60/90 plans
- Medical workflows
- All role-based views

---

## COMMON ISSUES & SOLUTIONS

### Issue: "Login failed"
**Solution**: 
- Verify password: `testpass123`
- Check email spelling
- Use exact email from list above

### Issue: "File upload fails"
**Solution**:
- Use small file (< 5MB)
- Supported: PDF, DOC, DOCX, PPTX, JPG, PNG, MP4, etc.
- Check file extension

### Issue: "Email not sending"
**Solution**:
- Go to `/admin/settings/email/`
- Configure SMTP sender
- Or check email logs: `/admin/settings/email-logs/`

### Issue: "Zoom link not generating"
**Solution**:
- Go to Setup > Zoom Integration
- Click "Test Connection"
- If fails, Zoom credentials not valid
- Continue without Zoom (feature still works)

### Issue: "HRBP can't see employees"
**Solution**:
- HRBP only sees Engineering dept
- Employees must be in Engineering to show
- John should be assigned to Engineering ✓

---

## VERIFY ALL FEATURES

### Email Templates with Rich Text
- [ ] Go to Admin > Setup > Email Templates
- [ ] Click any template
- [ ] Email Body has toolbar (bold, italic, lists, colors)
- [ ] Try formatting some text
- [ ] Save and verify in sent emails

### File Upload Expansion
- [ ] Try uploading PPTX (PowerPoint)
- [ ] Try uploading MP4 (Video)
- [ ] Try uploading DOCX (Word doc)
- [ ] Should all work

### Approval Workflow
- [ ] Go to employee profile
- [ ] See "Current Stage" section
- [ ] If awaiting review, see approval buttons
- [ ] Test Approve/Reject

### Dashboards
- [ ] Admin Dashboard: Tiles clickable, filter works
- [ ] Analytics: Charts load, filters work
- [ ] HRBP Dashboard: Filtered by dept
- [ ] Medical Approver: Medical queue visible

### Zoom Integration
- [ ] Setup > Zoom Integration page loads ✓
- [ ] Form visible ✓
- [ ] Instructions clear ✓
- [ ] (Optional: Test with real Zoom creds)

### Orientation & Training
- [ ] Can create sessions ✓
- [ ] Can assign to employees ✓
- [ ] Employees see in dashboard ✓
- [ ] Zoom links in emails ✓
- [ ] Can create training paths ✓
- [ ] Can assign training ✓

---

## QUICK METRICS TO CHECK

After completing workflow, verify:

```
Dashboard Metrics:
- Total Employees: 3 ✓
- In Progress: 3 ✓  
- Learning Paths: 1+ ✓
- Active Enrollments: 3+ ✓
- Joining in 10 Days: 3 ✓

Email Stats:
- Emails sent: 10+ ✓
- No errors in logs ✓
- Rich formatting visible ✓

User Access:
- Super Admin: All features ✓
- Admin: Can create/manage ✓
- HRBP: Dept-filtered view ✓
- Medical Approver: Medical only ✓
- Employees: Their own data ✓
```

---

## TEST RESULT SUMMARY

After testing, document:

```markdown
## E2E Test Results - 2026-06-20

### Features Tested
- [x] Employee creation & onboarding
- [x] Medical submission & approval
- [x] Pre-onboarding forms
- [x] Onboarding forms
- [x] Post-onboarding forms
- [x] Orientation sessions & Zoom
- [x] Training paths & assignments
- [x] Dashboards & metrics
- [x] Email notifications
- [x] Role-based access

### Issues Found
(List any bugs/issues)

### Performance
- Dashboard load time: ___ ms
- Form submission: ___ seconds
- Email delivery: ___ seconds

### UI/UX Notes
(Any feedback on design/usability)

### Status
✅ READY FOR PRODUCTION
```

---

## CLEANUP AFTER TESTING

**To remove test data**:
```bash
python manage.py shell
```

```python
from core.models import User, OrgUnit

# Delete test employees
User.objects.filter(email__endswith='@test.com').delete()

# Delete test departments
OrgUnit.objects.filter(code__in=['ENG', 'HR', 'SAL']).delete()

# Delete test locations
OrgUnit.objects.filter(code__in=['US-NY', 'UK-LON', 'UAE-DXB']).delete()
```

---

## HELPFUL URLS

```
Dashboard:          http://127.0.0.1:8000/admin/dashboard/
Analytics:          http://127.0.0.1:8000/admin/analytics/
Employees:          http://127.0.0.1:8000/admin/employees/
Medical Review:     http://127.0.0.1:8000/admin/medical/review/
Email Logs:         http://127.0.0.1:8000/admin/settings/email-logs/
Email Templates:    http://127.0.0.1:8000/admin/settings/email-templates/
Zoom Settings:      http://127.0.0.1:8000/admin/settings/zoom/
Live Sessions:      http://127.0.0.1:8000/sessions/
Learning Paths:     http://127.0.0.1:8000/admin/training/paths/
Training Assign:    http://127.0.0.1:8000/admin/training/assignments/
```

---

## SUCCESS!

If all tests pass, the OnboardHub platform is:
✅ Fully functional
✅ Role-based access working
✅ Email system operational
✅ Zoom integration ready
✅ Rich text editors working
✅ File uploads expanded
✅ Dashboards accurate
✅ Production ready

**Estimated completion**: 60-90 minutes  
**Last update**: 2026-06-20  
**Ready to begin**: YES ✅

