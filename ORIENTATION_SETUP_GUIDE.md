# How to Set Up & Assign Orientation Sessions

## Overview
Orientation sessions are the "Orientation" stage in the onboarding process. They can include training videos, initial meetings, setup sessions, etc., and support Zoom integration.

---

## Step 1: Create Orientation Content

### Option A: Create Individual Sessions
1. Go to **Admin > Learning** (or **Live Sessions** if available)
2. Click **"Create New Session"**
3. Fill in:
   - **Title**: "Team Orientation Meeting" or similar
   - **Description**: What the session covers
   - **Session Type**: Select "Orientation"
   - **Scheduled Date**: When employees should attend
   - **Duration**: How long it takes (in minutes)
   - **Zoom**: If Zoom is enabled, meeting link auto-generates
   - **Notes**: Any preparation needed

4. Click **"Create Session"**

### Option B: Create Learning Path with Multiple Sessions
1. Go to **Admin > Training > Learning Paths**
2. Click **"Create Learning Path"**
3. Set as "Orientation" type
4. Add multiple sessions/lessons
5. Employees will go through in order

---

## Step 2: Assign Orientation to Employees

### Method 1: Bulk Assign by Department
1. Go to **Admin > Onboarding** 
2. Click **"Assign Orientation"**
3. Select department
4. Select employees to receive orientation
5. Select session/path
6. Click **"Assign to Selected"**

### Method 2: Assign from Employee Profile
1. Go to **Admin > Employees**
2. Click on employee name
3. Go to **"Orientation"** section
4. Click **"Assign Session"**
5. Select orientation session
6. Click **"Assign"**

### Method 3: Auto-Assign on Status Change
1. Go to **Admin > Automation**
2. Create rule: When status = "onboarding", assign orientation
3. Select which session to auto-assign
4. Enable rule
5. All future employees in that status get assigned

---

## Step 3: Employee Completes Orientation

### From Employee Side:
1. Employee logs in
2. Goes to **"Onboarding"** or **"Learning"**
3. Sees **"Orientation Sessions"**
4. Clicks **"Register"** or **"Join"**
5. Receives Zoom link via email
6. Attends session
7. Gets marked as "Attended" (manual or auto)

### From Admin Side (Mark Attendance):
1. Go to **Admin > Sessions > [Session Name]**
2. See list of registered employees
3. Click **"Mark Attended"** next to their name after session
4. Employee's orientation status updates

---

## Step 4: Track Orientation Completion

### Employee Profile View
1. Go to **Admin > Employees > [Employee]**
2. Look for **"Orientation Stage"**
3. See:
   - Number of sessions assigned
   - Number completed
   - Completion percentage
   - List of individual sessions with status

### Dashboard
1. Go to **Admin > Dashboard**
2. See "Orientation" section in unified stages
3. Click for breakdown by employee

### Analytics
1. Go to **Admin > Analytics**
2. Filter by "Orientation"
3. See completion rates by department
4. Export data to CSV

---

## Zoom Integration for Orientation

### Setting Up Zoom
1. Go to **Admin > Settings > Zoom Integration**
2. Enter your Zoom OAuth credentials:
   - Client ID
   - Client Secret
   - Account ID
   - Host Email
3. Click **"Test Connection"** to verify
4. When enabled, Zoom links auto-generate for all sessions

### Zoom Meeting Details Sent to Employees
When session is assigned, email includes:
- Meeting title
- Date & time
- Zoom link (if Zoom enabled)
- Join instructions
- Session description

### After Orientation
- Zoom recording available in Zoom account
- Employee can review recording
- Mark as "completed" in system

---

## Common Scenarios

### Scenario 1: Single Orientation Session for All New Hires
1. Create one "Company Orientation" session
2. Schedule monthly or on-demand
3. Auto-assign to all employees entering "onboarding" stage
4. Mark attendance after session

### Scenario 2: Department-Specific Orientation
1. Create separate sessions per department:
   - Engineering Orientation
   - Sales Orientation
   - HR Orientation
2. Set up automation rule per department
3. Auto-assign based on department
4. Each department's sessions show in their employee profiles

### Scenario 3: Multi-Day Orientation Program
1. Create learning path: "Orientation Program"
2. Add multiple sessions to the path:
   - Day 1: Welcome & Company Overview
   - Day 2: Department Overview
   - Day 3: Tools & Systems
   - Day 4: Team Meetings
   - Day 5: Final Q&A
3. Assign entire path at once
4. Employees progress through sequentially

### Scenario 4: Optional vs. Required Orientation
1. Required: Auto-assign on hire
2. Optional: Make available but not assigned
3. Track in analytics which employees completed optional sessions

---

## Troubleshooting

### Problem: "Session not showing up for employee"
- Check if employee is in right stage (should be in "onboarding" or similar stage)
- Verify session is enabled and not archived
- Check employee department matches session scope (if filtered)
- Clear browser cache

### Problem: "Zoom link not generating"
- Go to **Admin > Settings > Zoom**
- Check Zoom is enabled (green status)
- Click "Test Connection"
- Verify OAuth credentials are correct
- Create NEW session (old ones won't get Zoom links retroactively)

### Problem: "Employee didn't receive email"
- Check email settings: **Admin > Settings > Email**
- Verify sender email is configured
- Check employee email is correct in profile
- Check email logs for errors: **Admin > Settings > Email > Logs**

### Problem: "Can't mark attendance"
- Only admins/managers can mark attendance
- Go to session detail page (not employee profile)
- Look for "Attendees" section
- Click "Mark Attended"

---

## Best Practices

✅ **Schedule orientation during onboarding stage** (not after)
✅ **Test Zoom connection before assigning to employees**
✅ **Send reminder email 24 hours before session**
✅ **Record session for employees who miss it**
✅ **Include clear join instructions in email**
✅ **Mark attendance day-of or day-after session**
✅ **Follow up with non-attendees**
✅ **Update orientation content annually**

---

## Navigation Tips

- **Quick Access**: Admin > Onboarding > [Employee] > Orientation tab
- **Bulk Edit**: Admin > Onboarding > Select Multiple > Assign Orientation
- **Analytics**: Admin > Analytics > Filter "Orientation" stage
- **Settings**: Admin > Settings > Zoom, Email
- **Scheduling**: Live Sessions > Calendar view

---

## Quick Reference

| Task | Where to Go |
|------|-------------|
| Create session | Admin > Learning / Live Sessions > Create |
| Assign to employee | Admin > Employees > [Name] > Orientation > Assign |
| Bulk assign | Admin > Onboarding > Select Multiple > Assign |
| Auto-assign | Admin > Automation > Create Rule |
| Mark attendance | Admin > Sessions > [Session] > Mark Attended |
| View completion | Admin > Analytics > Filter "Orientation" |
| Configure Zoom | Admin > Settings > Zoom Integration |
| View email logs | Admin > Settings > Email > Logs |
| Edit orientation | Admin > Learning > [Session] > Edit |

---

## Need Help?

- **Zoom help**: Click question mark on Zoom Settings page
- **Email issues**: Check Admin > Settings > Email > Logs
- **Employee not getting emails**: Check email is enabled in their notification preferences
- **Technical issues**: Check Django logs or contact support
