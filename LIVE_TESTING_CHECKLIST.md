# LIVE E2E TESTING - Real-Time Checklist
## Follow Along Step-by-Step

**Start Time**: Now  
**Server**: http://127.0.0.1:8000 (RUNNING ✅)  
**Test Mode**: Live with AI assistance

---

## PHASE 1: INITIAL LOGIN & VERIFICATION (5 min)

### Step 1: Dashboard Overview
```
🌐 Go to: http://127.0.0.1:8000/admin/dashboard/
👤 Login: admin@onboardhub.local
🔒 (Use your admin password)
```

**Checklist**:
- [ ] Page loads without errors
- [ ] See dashboard with KPI tiles
- [ ] "Total Employees" shows: 3
- [ ] "Joining in 10 Days" shows: 3
- [ ] Recent employees table shows all 3
- [ ] Navigation menus visible (all highlighted)
- [ ] Live Sessions in main menu

**Report back**: 
- Does dashboard load?
- What do you see in the tiles?

---

## PHASE 2: EMPLOYEE MEDICAL SUBMISSION (8 min)

### Step 2A: Employee Submits Medical
```
🌐 Go to: http://127.0.0.1:8000/login/
👤 Login: john.eng@test.com
🔒 Password: testpass123
```

**Expected Screen**: Employee home with onboarding stages

**Next**:
1. Click "Medical" in left sidebar
2. **Upload a file** (any PDF or image file from your computer)
3. Click "Submit"

**Checklist**:
- [ ] Medical page loads
- [ ] File upload works
- [ ] Submit button clickable
- [ ] Sees success message or redirect

**Report back**: 
- Did medical submission succeed?
- Any error messages?

---

### Step 2B: Check Medical Email Sent
```
🌐 Go to: http://127.0.0.1:8000/admin/settings/email-logs/
👤 Login: admin@onboardhub.local (if logged out)
```

**Checklist**:
- [ ] Email logs page loads
- [ ] See recent email with "medical" in subject
- [ ] To: medical@test.com
- [ ] Status: "sent" or "delivered"
- [ ] Time: Just now (within last 1 min)

**Report back**:
- Is there an email notification?
- What's the subject?

---

## PHASE 3: MEDICAL APPROVER REVIEW & APPROVAL (8 min)

### Step 3A: Medical Approver Logs In
```
🌐 Go to: http://127.0.0.1:8000/login/
👤 Login: medical@test.com
🔒 Password: testpass123
```

**Expected**: Medical approver dashboard

**Navigate to Medical Review**:
1. Look for "Medical Review" in navigation
2. OR go directly to: `/admin/medical/review/`
3. Should see John Engineer's submission in queue

**Checklist**:
- [ ] Medical review page loads
- [ ] John Engineer listed with "pending" status
- [ ] Can click to view details

**Report back**:
- Do you see John's submission?
- Can you click to view documents?

---

### Step 3B: Approve Medical Submission
```
1. Click on John Engineer's submission
2. View the medical document you uploaded
3. Add a note/comment: "Medical check passed"
4. Click "Approve Medical" button
```

**Checklist**:
- [ ] Document displays correctly
- [ ] Comment field appears
- [ ] Approve button visible and clickable
- [ ] After clicking: See success message
- [ ] Status changes to "approved"
- [ ] John appears in "Completed" list

**Report back**:
- Does approval succeed?
- Does status change?

---

### Step 3C: Verify John Received Email
```
🌐 Go to: http://127.0.0.1:8000/admin/settings/email-logs/
```

**Checklist**:
- [ ] See new email to john.eng@test.com
- [ ] Subject mentions "approved" or "medical"
- [ ] Sent within last 2 minutes

**Report back**:
- Does John get an approval email?

---

## PHASE 4: PRE-ONBOARDING SUBMISSION (8 min)

### Step 4A: John Submits Pre-Onboarding
```
🌐 Go to: http://127.0.0.1:8000/login/
👤 Login: john.eng@test.com
🔒 Password: testpass123
```

**Navigate to Pre-Onboarding**:
1. Click "Pre-Onboarding" in left menu
2. Fill the form with:
   - Emergency Contact: Jane Engineer
   - Phone: +1-555-0001
3. **Upload a file** (PDF or image)
4. Click "Submit"

**Checklist**:
- [ ] Pre-onboarding form loads
- [ ] Text fields accept input
- [ ] File upload works
- [ ] Form validates (no empty required fields)
- [ ] Submit succeeds
- [ ] Sees confirmation message

**Report back**:
- Does form submission work?
- Any validation errors?

---

### Step 4B: Check Email to HRBP
```
🌐 Go to: http://127.0.0.1:8000/admin/settings/email-logs/
```

**Checklist**:
- [ ] See email to hrbp@test.com
- [ ] Subject: "Pre-Onboarding Submitted" or similar
- [ ] Sent within last 2 minutes

**Report back**:
- Does HRBP get notified?

---

## PHASE 5: HRBP APPROVES PRE-ONBOARDING (5 min)

### Step 5A: HRBP Reviews & Approves
```
🌐 Go to: http://127.0.0.1:8000/login/
👤 Login: hrbp@test.com
🔒 Password: testpass123
```

**Navigate to Employee Profile**:
1. Click "People" > "Employees"
2. You should see **only Engineering employees** (just John)
3. Click on John Engineer
4. Scroll down to "**Current Stage**" section
5. Should see "Awaiting Your Review" alert box

**In the approval section**:
1. Add comment: "Documents look good"
2. Click "Approve" button
3. You should see success message
4. John's status should change

**Checklist**:
- [ ] HRBP sees filtered view (only Engineering)
- [ ] John's profile loads
- [ ] "Awaiting Your Review" visible
- [ ] Approval form appears
- [ ] Comment saves
- [ ] Approval succeeds
- [ ] Status changes

**Report back**:
- Can you see John's profile?
- Is approval interface visible?
- Does approval work?

---

### Step 5B: John Gets Approval Email
```
🌐 Go to: http://127.0.0.1:8000/admin/settings/email-logs/
```

**Checklist**:
- [ ] Email to john.eng@test.com
- [ ] Subject mentions "approved"
- [ ] Sent within last 2 minutes

---

## PHASE 6: ONBOARDING SUBMISSION (5 min)

### Step 6A: John Submits Onboarding
```
🌐 Go to: http://127.0.0.1:8000/login/
👤 Login: john.eng@test.com
🔒 Password: testpass123
```

**Navigate to Onboarding**:
1. Click "Onboarding" in left menu
2. Fill form:
   - Any required text fields
   - **Upload a file**
   - Check "Accept Policy" checkbox
3. Click "Submit"

**Checklist**:
- [ ] Form loads and displays all fields
- [ ] File upload works
- [ ] Checkbox toggles
- [ ] Submit succeeds
- [ ] Confirmation message appears

**Report back**:
- Form submission success?

---

## PHASE 7: DASHBOARD VERIFICATION (5 min)

### Step 7A: Admin Dashboard Metrics
```
🌐 Go to: http://127.0.0.1:8000/admin/dashboard/
👤 Login: admin@onboardhub.local
```

**Verify Metrics**:
- [ ] Total Employees: 3
- [ ] In Progress: 3 (or less if some completed)
- [ ] Recent employees table shows all 3
- [ ] **Click "In Progress" tile** → Should filter table to show in-progress only

**Test Tile Filtering**:
1. Click "In Progress" tile
2. Recent employees table should update
3. Should show only in-progress employees
4. Click "All" tile to reset

**Checklist**:
- [ ] Tiles show correct counts
- [ ] Click to filter works
- [ ] Table updates dynamically
- [ ] No JavaScript errors in browser console

**Report back**:
- Are metrics accurate?
- Do filters work?

---

### Step 7B: Analytics Dashboard
```
🌐 Go to: http://127.0.0.1:8000/admin/analytics/
```

**Checklist**:
- [ ] Page loads
- [ ] Charts/graphs visible
- [ ] Shows completion rates
- [ ] Stage distribution visible
- [ ] Can filter by department (should see Engineering)

**Report back**:
- Do analytics load?
- Any charts visible?

---

## PHASE 8: ORIENTATION & ZOOM (10 min)

### Step 8A: Create Orientation Session
```
🌐 Go to: http://127.0.0.1:8000/sessions/
👤 Login: admin@onboardhub.local
```

**Steps**:
1. Click "Create Session" button
2. Fill:
   - **Title**: Company Orientation
   - **Date**: 2026-06-25
   - **Time**: 10:00 AM
   - **Duration**: 2 hours
   - **Description**: Welcome to company
   - **Enable Zoom**: Check YES
3. Click "Create"

**Checklist**:
- [ ] Sessions page loads
- [ ] Form has all fields
- [ ] Date picker works
- [ ] Zoom checkbox available
- [ ] Session creates successfully
- [ ] Redirects to session detail
- [ ] **Zoom link generated automatically** (should see zoom link in details)

**Report back**:
- Did session create?
- Is Zoom link visible?

---

### Step 8B: Assign Orientation to Employee
```
🌐 Go to: http://127.0.0.1:8000/admin/employees/
```

**Steps**:
1. Click on John Engineer
2. Scroll to "Orientation" section (in unified stages)
3. Click "Assign Session"
4. Select the session you just created
5. Click "Assign"

**Checklist**:
- [ ] Employee profile loads
- [ ] Orientation section visible
- [ ] "Assign Session" button appears
- [ ] Can select session from dropdown
- [ ] Assignment succeeds
- [ ] Session shows in profile

**Report back**:
- Can you assign orientation?
- Does it appear in profile?

---

### Step 8C: Check Email with Zoom Link
```
🌐 Go to: http://127.0.0.1:8000/admin/settings/email-logs/
```

**Checklist**:
- [ ] Email sent to john.eng@test.com
- [ ] Subject: "Orientation" or "Session Invitation"
- [ ] **Email body contains**:
  - Session title
  - Date and time
  - **Zoom meeting link** (zoom.us/j/...)
  - Join instructions

**Report back**:
- Did John get email?
- Is Zoom link in email?
- Does link look valid?

---

## PHASE 9: TRAINING PATH & ASSIGNMENT (10 min)

### Step 9A: Create Training Path
```
🌐 Go to: http://127.0.0.1:8000/admin/training/paths/
👤 Login: admin@onboardhub.local
```

**Steps**:
1. Click "Create Path" button
2. Fill:
   - **Title**: Onboarding Training
   - **Description**: Training for new employees
3. Click "Create"

**Checklist**:
- [ ] Learning Paths page loads
- [ ] Create button visible
- [ ] Form appears with title & description fields
- [ ] Path creates successfully
- [ ] Redirects to path detail/edit

**Report back**:
- Did training path create?

---

### Step 9B: Assign Training to Employees
```
🌐 Go to: http://127.0.0.1:8000/admin/training/assignments/
```

**Steps**:
1. Click "Assign Training" button
2. **Select employees**: Check all 3:
   - John Engineer
   - Sarah HR
   - Mike Sales
3. **Select training path**: Onboarding Training
4. Click "Assign"

**Checklist**:
- [ ] Assignments page loads
- [ ] Can select multiple employees (checkbox works)
- [ ] Can select training path from dropdown
- [ ] Assignment succeeds
- [ ] Confirmation message appears
- [ ] All 3 employees assigned

**Report back**:
- Did bulk assignment work?
- All 3 employees assigned?

---

### Step 9C: Employees See Training Assigned
```
🌐 Go to: http://127.0.0.1:8000/login/
👤 Login: john.eng@test.com
🔒 Password: testpass123
```

**Navigate to My Learning**:
1. Click "My Learning" in left menu
2. Should see "Onboarding Training" listed

**Checklist**:
- [ ] My Learning page loads
- [ ] Onboarding Training appears
- [ ] Can click to view course details
- [ ] Progress shows 0%

**Report back**:
- Does John see training assigned?

---

## PHASE 10: EMAIL FEATURES (5 min)

### Step 10A: Rich Text Email Editor
```
🌐 Go to: http://127.0.0.1:8000/admin/settings/email-templates/
👤 Login: admin@onboardhub.local
```

**Steps**:
1. Click any template (e.g., "Welcome")
2. Scroll to "Email Body" field
3. **Check for toolbar** with:
   - Bold button
   - Italic button
   - Lists button
   - Color picker
   - Alignment buttons

**Checklist**:
- [ ] Email Templates page loads
- [ ] Multiple templates listed
- [ ] Email Body has **formatting toolbar**
- [ ] Can click Bold/Italic/etc.
- [ ] Try formatting some text:
  - Make text **bold**
  - Make text *italic*
  - Create a bullet list
4. Click "Save Changes"
5. Verify formatting saved

**Report back**:
- Is rich text editor visible?
- Can you format text?
- Does it save?

---

### Step 10B: Email Logs Verification
```
🌐 Go to: http://127.0.0.1:8000/admin/settings/email-logs/
```

**Checklist**:
- [ ] Email logs page loads
- [ ] See 10+ emails sent (from all the tests above)
- [ ] Emails have:
  - To address
  - Subject line
  - Timestamp
  - Status (sent/delivered)

**Verify Rich Formatting in Emails**:
- Look at an email body
- Should see **bold**, *italic*, or lists if template had them

**Report back**:
- How many emails sent?
- Any formatting visible?

---

## PHASE 11: ROLE-BASED VIEWS (5 min)

### Step 11A: Super Admin View (FULL Access)
```
👤 Login: admin@onboardhub.local
```

**Check Menus**:
- [ ] Dashboard ✅
- [ ] Analytics ✅
- [ ] People (Employees & Users) ✅
- [ ] Onboarding (Forms, Documents, Medical, Orientation) ✅
- [ ] Learning (Paths, Assignments) ✅
- [ ] Live Sessions ✅
- [ ] Setup (ALL options including Zoom Integration) ✅
- [ ] Medical Review ✅

**Report back**:
- Can you see all menus?
- Can you access Zoom settings?

---

### Step 11B: HRBP View (Filtered)
```
🌐 Go to: http://127.0.0.1:8000/login/
👤 Login: hrbp@test.com
🔒 Password: testpass123
```

**Check Dashboard**:
1. Go to Dashboard
2. Should see **only employees from HRBP's department**
3. Can create sessions
4. Can assign training

**Verify Filters**:
- [ ] People list shows only Engineering employees
- [ ] Analytics filtered to Engineering
- [ ] Cannot see Setup menu (no gear icon)
- [ ] CAN see Training and Sessions

**Report back**:
- Do you see filtered view (only your dept)?
- Can you assign training/sessions?

---

### Step 11C: Medical Approver View
```
🌐 Go to: http://127.0.0.1:8000/login/
👤 Login: medical@test.com
🔒 Password: testpass123
```

**Check Access**:
1. Navigate menus
2. Should see:
   - [ ] Medical Review ✅
   - [ ] Cannot see People ✅
   - [ ] Cannot see Setup ✅
   - [ ] Cannot see Learning ✅
3. Go to Medical Review
4. Should see medical queue

**Report back**:
- Can you only see Medical?
- Is access restricted correctly?

---

### Step 11D: Employee View
```
🌐 Go to: http://127.0.0.1:8000/login/
👤 Login: john.eng@test.com
🔒 Password: testpass123
```

**Check Access**:
- [ ] Home/Dashboard shows onboarding progress
- [ ] Medical stage visible
- [ ] Pre-Onboarding visible
- [ ] Onboarding visible
- [ ] Post-Onboarding visible
- [ ] My Learning shows assigned training
- [ ] Cannot see Admin menu

**Report back**:
- Does employee view work?
- Can you see your onboarding journey?

---

## FINAL VERIFICATION CHECKLIST

**Overall System**:
- [ ] No console errors (open browser dev tools)
- [ ] All pages load quickly
- [ ] Navigation works
- [ ] Forms validate properly
- [ ] Email system working
- [ ] Database updates accurately

**Critical Features**:
- [ ] Medical submit & approve ✅
- [ ] Pre-onboarding submit & approve ✅
- [ ] Onboarding submit ✅
- [ ] Orientation session creation ✅
- [ ] Training assignment ✅
- [ ] Dashboard metrics accurate ✅
- [ ] Email notifications sent ✅
- [ ] Zoom link generation ✅
- [ ] Role-based access enforced ✅
- [ ] Rich text formatting ✅

---

## TEST RESULTS SUMMARY

**Date**: 2026-06-20  
**Tester**: [Your name]  
**Duration**: _____ minutes  

### Overall Status
- [ ] ✅ ALL TESTS PASSED
- [ ] ⚠️ SOME ISSUES FOUND (list below)
- [ ] ❌ CRITICAL ERRORS (list below)

### Issues Found
```
(List any bugs, errors, or unexpected behavior)

1. Issue: _______________
   Expected: _______________
   Actual: _______________
   Severity: High/Medium/Low

```

### Performance Notes
```
- Dashboard load time: _____ ms
- Form submission: _____ seconds
- Email delivery: _____ seconds
```

### Feedback
```
Positive:
- 

Improvements:
- 

```

### Signature
Tested by: ________________  
Date: ________________  
Status: ✅ PRODUCTION READY

---

## HELP & TROUBLESHOOTING

**If page doesn't load**:
- Refresh: F5
- Check console errors: F12 (Developer Tools)
- Try different endpoint
- Check server still running

**If form won't submit**:
- Fill all required fields (marked with *)
- Check file size < 5MB
- Try different file format
- Look for error message in red

**If email doesn't arrive**:
- Check email logs: /admin/settings/email-logs/
- Look for status "error"
- Verify sender configured: /admin/settings/email/
- Check console for SMTP errors

**If Zoom link doesn't generate**:
- Check Zoom credentials: /admin/settings/zoom/
- Click "Test Connection"
- Create NEW session (old ones won't regenerate)

**Questions?**:
- Ask now and I'll help troubleshoot!

---

**Ready? Let's begin! Start with Step 1 and report back as you go.** ✅

