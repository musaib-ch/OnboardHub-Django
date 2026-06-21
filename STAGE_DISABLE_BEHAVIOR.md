# Stage Disable/Enable Behavior - Complete Guide

**Latest Update:** 2026-06-22  
**Feature:** When a stage is disabled, it completely disappears from the entire portal

---

## 🚫 What Happens When You Disable a Stage

When you **disable** a stage in **Admin → Setup → Workflow Stages**, that stage:

| Where | Behavior |
|-------|----------|
| **Employee Creation** | ❌ Doesn't appear in custom selection checkboxes |
| **Employee Creation** | ❌ Removed from template dropdown if template includes it |
| **Employee Profile** | ❌ Doesn't show in workflow section |
| **Employee Profile** | ❌ Can't be selected in "Edit Workflow" modal |
| **Workflow Templates** | ❌ Doesn't appear when creating/editing templates |
| **Admin Workflow Pages** | ❌ Shows as "Disabled" but still visible (admin only) |
| **Employee Onboarding** | ❌ Doesn't appear in journey |
| **Any Dropdown/Menu** | ❌ Never appears |

---

## ✅ What Happens When You Enable a Stage

When you **enable** a stage:

| Where | Behavior |
|-------|----------|
| **Employee Creation** | ✅ Appears in custom selection immediately |
| **Employee Creation** | ✅ Available to add to templates |
| **Employee Profile** | ✅ Can be selected in workflow editor |
| **Workflow Templates** | ✅ Can be included when creating templates |
| **Admin Workflow Pages** | ✅ Shows as "Enabled" |
| **Employee Onboarding** | ✅ Available for workflow paths |
| **All Selections** | ✅ Appears everywhere |

---

## 🔧 How It Works Technically

### Multi-Layer Validation

**Layer 1: Employee Creation**
```python
# When creating employee with custom stages:
enabled_stages = StageDefinition.objects.filter(is_enabled=True)
# Only these stages appear in checkboxes
```

**Layer 2: Workflow Update**
```python
# When editing employee workflow:
enabled_stage_set = StageDefinition.objects.filter(is_enabled=True).values_list("stage_key", flat=True)
if invalid_stage in (new_stages - enabled_stage_set):
    # Reject the change with error message
```

**Layer 3: Employee Detail Display**
```python
# When showing employee profile:
stage_definitions = StageDefinition.objects.filter(is_enabled=True)
# Only enabled stages displayed
```

**Layer 4: Template Creation**
```python
# When creating templates:
stages = StageDefinition.objects.filter(is_enabled=True)
# Only enabled stages available
```

---

## 📋 Use Cases

### **Scenario 1: Temporarily Pause "Orientation" Stage**

1. Go to **Admin → Setup → Workflow Stages**
2. Find **"Orientation"** stage
3. Click toggle to **Disable**
4. **Immediately:**
   - Orientation doesn't appear in employee creation
   - Can't add to new templates
   - Can't select in employee workflow editor
   - Won't appear in any employee's journey

5. When ready to re-enable:
   - Click toggle to **Enable**
   - Orientation available again everywhere

### **Scenario 2: Hide Stage Temporarily (No Employees Affected)**

**Before Disabling:**
- Check current employees using that stage
- Plan migration if needed

**After Disabling:**
- New employees can't get that stage
- Existing employees keep their workflow (their path is saved)
- When re-enabling, stage available again

**Important:** Existing employees keep their saved workflows even if a stage is disabled

### **Scenario 3: Remove Stage Permanently**

1. Disable the stage
2. Wait for all employees to complete it
3. After 90 days, admin can safely delete (in database)
4. Stage completely removed from system

---

## ⚠️ Important Notes

### Existing Employee Workflows

**When you disable a stage:**
- Existing employees who already have it in their path: ✅ Keep it (workflow is locked)
- New employees: ❌ Can't get that stage
- Employees in the middle of that stage: ✅ Can complete it normally

**Example:**
```
Employee John:
  Current Path: Medical → Pre → Onboarding → Orientation → Training
  Status: Currently in "Onboarding" stage
  
Admin disables "Orientation" stage
  
Result:
  John's path: Medical → Pre → Onboarding → Orientation → Training (UNCHANGED)
  He can still complete Orientation
  New employees: Can't select Orientation
```

### Template Behavior

**When a stage in a template is disabled:**
- Template itself stays active (but missing that stage)
- New employees using that template: ❌ Won't get disabled stage
- Template shows only enabled stages

**Example:**
```
Template: "Standard Onboarding"
  Original: Medical → Pre → On → Post → Orientation → Training

Disable "Orientation"

New employees get:
  Medical → Pre → On → Post → Training (Orientation removed)
```

---

## 🎯 Best Practices

### ✅ DO:
- ✅ Disable stages when they're not currently needed
- ✅ Check employee count before disabling
- ✅ Disable during off-hours for clarity
- ✅ Document reason for disable (e.g., "Zoom not available")
- ✅ Plan re-enable date

### ❌ DON'T:
- ❌ Delete stages (disable instead, keeps audit trail)
- ❌ Disable without checking who's in that stage
- ❌ Disable during active hiring (confuses new employee setup)
- ❌ Forget to re-enable when resuming operations

---

## 📊 Disable/Enable Status Indicator

### On Stages List Page

**Enabled Stage:**
```
✓ Medical Clearance                          [7 days]  ✓ Enabled  [edit]
```

**Disabled Stage:**
```
✓ Orientation                                [7 days]  ✗ Disabled [edit]
```

**Visual Feedback:**
- Disabled stages appear with reduced opacity (faded)
- Green badge = Enabled
- Gray badge = Disabled

---

## 🔐 Validation Rules

All of these are now validated:

| Rule | What It Prevents |
|------|------------------|
| **No disabled in custom selection** | Creating employee with disabled stage |
| **No disabled in template** | Saving template with disabled stage |
| **No disabled in workflow edit** | Editing employee workflow to add disabled stage |
| **No disabled in API** | Any API call trying to use disabled stage |

---

## 🛠️ Admin Actions

### Enable/Disable a Stage

1. Go to **Admin → Setup → Workflow Stages**
2. Find the stage you want to disable/enable
3. Click the **toggle button** in the "Status" column
   - Green toggle = Click to disable
   - Gray toggle = Click to enable
4. Page updates immediately
5. Change is live across entire portal

### Effects Are Immediate

✅ Disabled stages disappear from all dropdowns/selections instantly  
✅ No page refresh needed for admins  
✅ No code changes needed  
✅ No database cleanup needed  

---

## 📈 Example Timeline

```
Day 1 - Friday 5pm
  Admin: Disable "Orientation" stage (for weekend maintenance)
  
Day 1 - Friday 5:05pm
  Result: Orientation gone from all employee creation forms
  
Day 3 - Monday 9am
  Admin: Re-enable "Orientation" stage
  
Day 3 - Monday 9:05am
  Result: Orientation back in all forms
  
Day 4 - Tuesday
  Employee: Creates new employee
  Orientation: Available to select ✅
```

---

## 🐛 Troubleshooting

### Q: I disabled a stage, but it still shows for an employee

**A:** That employee was created BEFORE you disabled it. Their workflow is saved and locked. They'll still complete that stage normally. New employees won't get it.

### Q: Why can't I delete a stage?

**A:** System allows disable but not delete to preserve audit trail. Disabled stages remain in database showing they were once used. This is intentional for compliance.

### Q: If I enable a stage, do old employees get it?

**A:** No. Only NEW employees created AFTER re-enable get the newly-enabled stage. Existing paths don't change.

### Q: Can employees see disabled stages?

**A:** No. The system filters them out completely. Employees only see enabled stages in their workflow.

---

## ✨ Summary

**The Goal:** When a stage is disabled, it's completely hidden from everyone except admins viewing the settings page.

**The Result:** 
- Clean, uncluttered UI for employees and HRs
- No confusion about which stages are available
- Easy to pause/resume stages as needed
- Existing workflows preserved
- New employees follow updated rules

**The Safety:** Multi-layer validation ensures no disabled stage can accidentally be assigned to any employee.

---

**Updated:** 2026-06-22  
**Commit:** 84c31f2
