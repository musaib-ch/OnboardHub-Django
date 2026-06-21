# Where to Find the New Configurable Workflow Features

## 🎯 Quick Navigation Guide

### **1. WORKFLOW MANAGEMENT (Setup Menu)**

As Super Admin or Admin, go to:
```
Admin Portal → Setup Menu (⚙️) → Workflow Stages
Admin Portal → Setup Menu (⚙️) → Workflow Templates
```

**What you can do:**
- ✅ View all workflow stages
- ✅ Enable/disable stages globally
- ✅ Create custom stages
- ✅ Create custom workflow templates
- ✅ Set default workflow for new employees

---

### **2. EMPLOYEE WORKFLOW CUSTOMIZATION**

When creating a new employee:
```
Admin Portal → Users → Create User
→ Scroll to "Onboarding Workflow" section
→ Choose: Default / Template / Custom
```

**What you can do:**
- ✅ Select pre-built workflow template
- ✅ Customize stages for this specific employee
- ✅ Pick which stages they go through

---

### **3. EMPLOYEE PROFILE WORKFLOW TAB**

When viewing an employee:
```
Admin Portal → Employees → [Select Employee]
→ Scroll down to "Onboarding Workflow" section
```

**What you can see:**
- ✅ Current stage path for this employee
- ✅ Whether using default or custom workflow
- ✅ Edit workflow button to modify path

**What you can do:**
- ✅ Click "Edit Workflow" to modify their stages
- ✅ Reorder stages
- ✅ Add/remove stages
- ✅ Add reason for change (audit trail)

---

## 📍 Exact URL Paths

| Feature | URL | Access |
|---------|-----|--------|
| Workflow Stages | `/admin/setup/stages/` | Super Admin, Admin |
| Create Stage | `/admin/setup/stages/create/` | Super Admin, Admin |
| Edit Stage | `/admin/setup/stages/<id>/edit/` | Super Admin, Admin |
| Workflow Templates | `/admin/setup/templates/` | Super Admin, Admin |
| Create Template | `/admin/setup/templates/create/` | Super Admin, Admin |
| Edit Template | `/admin/setup/templates/<id>/edit/` | Super Admin, Admin |

---

## 🔑 Key Features Explained

### **Default Stages Available**
1. **Medical** - Medical clearance and approval
2. **Pre-Onboarding** - Pre-boarding forms and setup
3. **Onboarding** - Main onboarding process
4. **Post-Onboarding** - Post-boarding activities
5. **Orientation** - Company orientation
6. **Training** - Training assignments
7. **30-Day Plan** - 30-day check-in
8. **60-Day Plan** - 60-day review
9. **90-Day Plan** - 90-day assessment
10. **Offer Acceptance** - Offer workflow stage

### **Pre-Built Templates**
1. **Standard Onboarding** - All stages (default)
2. **Quick Hire** - Medical + Onboarding only
3. **Contractor** - Custom contractor path
4. **Training-Heavy** - Focus on learning paths

---

## ✨ What's New - Feature Breakdown

### **Phase 1: Core Infrastructure**
- Stages now stored in database (not hardcoded)
- Configurable stage definitions with enable/disable
- Global default stage templates
- Per-employee custom stage paths

### **Phase 2: Employee Customization**
- Choose workflow at employee creation
- View current workflow in employee profile
- Edit employee workflow at any time
- Audit trail of workflow changes

### **Phase 3: Admin Management UI**
- Complete stage management interface
- Complete template management interface
- Create custom stages via UI
- No coding required!

### **Phase 4: Offer Workflow**
- New "offer_sender" role for offer management
- Dedicated offer sending permissions
- Track offer status and acceptance
- Integrated with e-signature system

---

## 🔐 Permissions Required

| Feature | Permission | Default Roles |
|---------|-----------|-----------------|
| View/Edit Stages | manage_stages | Super Admin, Admin |
| View/Edit Templates | manage_stage_templates | Super Admin, Admin |
| Customize Employee Workflow | customize_employee_workflow | Super Admin, Admin |
| Send Offers | send_offer | Super Admin, Admin, Offer Sender |
| Manage Offers | manage_offers | Super Admin, Admin |

---

## 🚀 Quick Start Tutorial

### **1. View Default Stages**
1. Login as Super Admin
2. Go to Setup → Workflow Stages
3. See all available stages (8 pre-built)
4. Toggle any stage on/off as needed

### **2. Create Custom Stage**
1. Go to Setup → Workflow Stages
2. Click "Add Custom Stage"
3. Fill in:
   - Stage Key: `custom_stage_name` (lowercase, no spaces)
   - Label: "Human Readable Name"
   - Description: Optional details
   - Default Due Days: How many days to complete
   - Stage Type: Mandatory/Optional/Conditional
4. Click "Create Stage"

### **3. Create Custom Template**
1. Go to Setup → Workflow Templates
2. Click "New Template"
3. Fill in:
   - Name: "My Custom Template"
   - Description: When to use this
   - Select Stages: Check which stages to include
4. Click "Create Template"

### **4. Create Employee with Custom Workflow**
1. Go to Users → Create User
2. Fill in employee details
3. Scroll to "Onboarding Workflow" section
4. Choose:
   - ☐ Default (uses global defaults)
   - ☐ Template (pick from list)
   - ☐ Custom (manually select stages)
5. Complete user creation
6. Employee will follow selected workflow path

### **5. Edit Employee Workflow**
1. Go to Employees → Select Employee
2. Scroll to "Onboarding Workflow" section
3. Click "Edit Workflow"
4. Modal opens with current stages
5. Uncheck to remove, add reason
6. Click "Save Changes"
7. Workflow updated, change logged

---

## 📊 Example Workflows

### **Standard Onboarding** (Default)
Medical → Pre-Onboarding → Onboarding → Post-Onboarding

### **Fast Track**
Medical → Onboarding → Post-Onboarding

### **Contractor**
Medical → Onboarding (no pre/post)

### **Offer First**
Offer Acceptance → Medical → Onboarding → Post-Onboarding

### **Training Heavy**
Medical → Pre-Onboarding → Onboarding → Training → 30-Day Plan → 60-Day Plan

---

## 🎓 Tips & Best Practices

1. **Create Templates First** - Templates save time for similar employee types
2. **Lock Completed Stages** - Once employee enters a stage, can't remove it
3. **Use Change Reasons** - Document why you changed workflows (audit trail)
4. **Test Workflows** - Create test employee with custom path to verify flow
5. **Set Defaults** - Set a default template so new employees don't need manual selection

---

## ✅ Troubleshooting

### **Can't see Workflow Stages option in Setup menu**
- Verify you're logged in as Super Admin or Admin
- Check your role has `manage_stages` permission
- Try refreshing the page

### **Stages dropdown not showing in employee creation**
- Verify JavaScript is enabled
- Check browser console for errors (F12)
- Reload the create user form

### **Workflow tab missing from employee detail**
- Verify employee has a stage_path configured
- Check if you have permission to view employee
- Try clearing browser cache

### **Changes not saving**
- Verify form is filled correctly
- Check browser console for validation errors
- Try submitting again or refresh page

---

## 🔄 System Architecture

```
Database (StageDefinition, StageTemplate, EmployeeStagePath)
           ↓
pipeline_v2.py (Database-driven stage logic)
           ↓
Admin Views (stage_config_views.py)
           ↓
Templates (setup/ pages in admin portal)
           ↓
Employee Flow (respects custom stage path)
```

---

## 📚 Related Documentation

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Production deployment
- [README.md](README.md) - System overview
- [deploy/README.md](deploy/README.md) - Cloudflare Tunnel setup

---

**All features are live and ready to use!** 🎉

If you can't see something, try:
1. ✅ Refresh the page (Ctrl+R)
2. ✅ Clear browser cache (Ctrl+Shift+Delete)
3. ✅ Log out and log back in
4. ✅ Check you're using the correct role
