# OnboardHub - Complete Role-Based Feature Matrix
## All Features & Role Access Control

**Last Updated**: 2026-06-20  
**Status**: Production Ready  
**Total Features**: 50+  
**Total Roles**: 6

---

## Quick Legend
- ✅ = Full Access
- 📖 = Read-Only
- 🔒 = Own Records Only
- ❌ = No Access
- 👥 = Team/Department Only (for HRBP/Manager)

---

## FEATURE MATRIX TABLE

| Feature | Super Admin | Admin | HRBP | Medical Approver | Manager | Employee |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|
| **DASHBOARD & HOME** |
| Admin Dashboard (KPIs) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Analytics Dashboard | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Employee Home | 📖 | 📖 | 📖 | 📖 | 📖 | ✅ |
| **EMPLOYEE MANAGEMENT** |
| View All Employees | ✅ | ✅ | 👥 | 📖 | 👥 | ❌ |
| Employee Profile | ✅ | ✅ | 👥 | 📖 | 👥 | 🔒 |
| Edit Employee Details | ✅ | ✅ | 👥 | ❌ | 👥 | 🔒 |
| Approve/Reject Submissions | ✅ | ✅ | 👥 | ❌ | 👥 | ❌ |
| Upload Documents on Behalf | ✅ | ✅ | 👥 | ❌ | 👥 | ❌ |
| Bypass Stages/Complete | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| **EMPLOYEE ONBOARDING JOURNEY** |
| Medical (Upload, Track) | ✅ | 📖 | 👥 | 👥 | 👥 | ✅ |
| Pre-Onboarding (Forms) | ✅ | ✅ | 👥 | 📖 | 👥 | ✅ |
| Orientation (Sessions) | ✅ | ✅ | ✅ | 📖 | 👥 | ✅ |
| Onboarding (Forms, Chat) | ✅ | ✅ | 👥 | 📖 | 👥 | ✅ |
| Post-Onboarding (Forms) | ✅ | ✅ | 👥 | 📖 | 👥 | ✅ |
| 30/60/90 Plans | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| **FORMS & ASSESSMENTS** |
| Form Builder (CRUD) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create/Edit Forms | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create Quizzes | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create Surveys | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| View Form Responses | ✅ | ✅ | 👥 | ❌ | 👥 | 🔒 |
| Export Form Data | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Fill Forms (Employee) | ✅ | 📖 | 📖 | 📖 | 📖 | ✅ |
| Take Quiz | ✅ | 📖 | 📖 | 📖 | 📖 | ✅ |
| View Quiz Results | ✅ | ✅ | 👥 | ❌ | 👥 | ✅ |
| **MEDICAL MANAGEMENT** |
| View Medical Requirements | ✅ | 📖 | 📖 | ✅ | 📖 | ✅ |
| Manage Medical Reqs | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Medical Review Queue | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Review Medical Documents | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Approve Medical | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Request Resubmission | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Request Medical Info | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Export Medical Data | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| **TRAINING & LEARNING** |
| Learning Paths (CRUD) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create Learning Path | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Edit Learning Path | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Assign Training | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| Bulk Assign Training | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| View Training Assignments | ✅ | ✅ | ✅ | 📖 | ✅ | ✅ |
| My Learning (Employee) | ✅ | 📖 | 📖 | 📖 | 📖 | ✅ |
| Take Course | ✅ | 📖 | 📖 | 📖 | 📖 | ✅ |
| View Certificates | ✅ | ✅ | ✅ | 📖 | ✅ | ✅ |
| **LIVE SESSIONS & ZOOM** |
| Sessions Dashboard | ✅ | ✅ | ✅ | 📖 | ✅ | ✅ |
| Create Session | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| Schedule with Zoom | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| Register for Session | ✅ | 📖 | 📖 | 📖 | 📖 | ✅ |
| Mark Attendance | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| View Session Details | ✅ | ✅ | ✅ | 📖 | ✅ | ✅ |
| **ZOOM & INTEGRATIONS** |
| Zoom Settings | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Configure Zoom OAuth | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Test Zoom Connection | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **CONTENT & KNOWLEDGE** |
| Knowledge Hub (CRUD) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Training Modules | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Orientation Content | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Presentations | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Browse Content | ✅ | ✅ | ✅ | 📖 | ✅ | ✅ |
| **COMMUNICATIONS** |
| Email Templates | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Email Settings | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Email Logs | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Email Statistics | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **SYSTEM CONFIGURATION** |
| Organization Settings | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Department Management | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Branding & Appearance | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Landing Page (CMS) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **ROLES & PERMISSIONS** |
| Users & Roles | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create User | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Edit User Details | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Edit User Role | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Edit Permissions | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Delete User | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Roles & Permissions UI | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **AUTOMATION & RULES** |
| Automation Rules (CRUD) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create Auto-Advance Rule | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create Notification Rule | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **IMPORT/EXPORT** |
| Import Employees | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Export Employees | ✅ | ✅ | 👥 | ❌ | 👥 | ❌ |
| Export Users | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Export Form Responses | ✅ | ✅ | 👥 | ❌ | 👥 | ❌ |
| **PERSONAL** |
| My Profile | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Change Password | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Notifications | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Messages & Chat | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Notification Preferences | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Role Descriptions

### Super Admin (👑)
**Purpose**: Full system control and configuration  
**Scope**: Organization-wide  
**Key Capabilities**:
- Manage all users and permissions
- Configure Zoom, Email, Organization settings
- Create forms, training, content
- View all employees and data
- Set up automation rules
- Export all data
- Override and bypass stages

**Who Gets This**: Owner, CTO, System Administrator

---

### Admin (⚙️)
**Purpose**: Platform management, user & content creation  
**Scope**: Organization-wide  
**Key Capabilities**:
- Create and manage users (except super admin)
- Build forms, quizzes, surveys
- Create training paths and content
- Manage organization structure
- Configure email and branding
- Create automation rules
- View analytics and metrics
- Manage landing page

**Who Gets This**: HR Manager, Operations Manager, Learning & Development Manager

---

### HRBP (👥)
**Purpose**: HR Business Partner for team management  
**Scope**: Department-scoped (sees own department only)  
**Key Capabilities**:
- View own team members
- Assign training and courses
- Create and manage sessions
- Track 30/60/90 plans
- Approve pre-onboarding submissions
- Assign orientation
- Schedule Zoom sessions
- View team analytics
- Export team data

**Who Gets This**: HR Business Partner, Department Manager, HR Coordinator

---

### Medical Approver (🏥)
**Purpose**: Review and approve medical requirements  
**Scope**: Location-scoped  
**Key Capabilities**:
- Review medical documents
- Approve or request resubmission
- Request additional medical info
- Set up medical requirements
- Bypass medical stage
- View medical analytics
- Export medical data

**Who Gets This**: Medical Compliance Officer, Health & Safety Manager, Occupational Health Professional

---

### Manager (👔)
**Purpose**: Direct team oversight (NOTE: Not in current system - would be custom role)  
**Scope**: Department-scoped  
**Key Capabilities**:
- View team members and progress
- Manage 30/60/90 day plans
- Approve/reject onboarding submissions
- Assign training to team
- Mark attendance
- Upload documents on behalf
- View team analytics

**Who Gets This**: Team Lead, Department Head, Project Manager

**Note**: Manager role is NOT currently configured. If needed, can be created as a custom role by Super Admin.

---

### Employee (👨‍💼)
**Purpose**: Complete personal onboarding journey  
**Scope**: Personal records only  
**Key Capabilities**:
- View own profile
- Complete medical forms
- Complete pre-onboarding forms
- Register for orientation sessions
- Complete onboarding forms
- Complete post-onboarding forms
- Complete 30/60/90 plans
- View assigned training
- Take courses and quizzes
- View certificates
- Send/receive messages
- Set notification preferences

**Who Gets This**: All employees

---

## Permission Categories

### People & Users (2 permissions)
- **view_employees** - Can search and view employee list
- **manage_users** - Can create, edit, delete staff users

### Stages & Actions (3 permissions)
- **bypass_stages** - Can mark stage complete on behalf
- **on_behalf_documents** - Can sign documents on behalf
- **manage_onboarding_plans** - Can create 30/60/90 plans

### Medical (5 permissions)
- **medical_review** - Can view medical documents
- **approve_medical** - Can approve medical
- **request_medical_resubmission** - Can request medical resubmission
- **request_medical_info** - Can request medical info
- **manage_medical_requirements** - Can manage medical setup

### Training & Learning (3 permissions)
- **manage_training** - Can create training paths
- **assign_training** - Can assign training to employees
- **view_training** - Can view training details

### Programs & Content (2 permissions)
- **view_programs** - Can view programs/content
- **manage_landing_page** - Can edit landing page

### Forms & Documents (3 permissions)
- **manage_forms** - Can create/edit forms
- **manage_documents** - Can manage documents
- **export_data** - Can export data

### Configuration (3 permissions)
- **manage_automation_rules** - Can create automation rules
- **manage_organization** - Can edit org settings
- **manage_appearance** - Can edit branding

---

## Access Control Notes

### Super Admin
- Has ALL permissions automatically
- Cannot be restricted
- Always has access to all pages
- Use sparingly!

### Department-Scoped Roles (HRBP, Manager)
- Can only see employees in their department(s)
- Bulk actions only work on their department
- Cannot manage users outside their scope

### Medical Approver
- Location-scoped (sees all locations assigned to them)
- Cannot view employee training or forms
- Focused only on medical requirements

### Role Editing
- Super Admin can edit any role
- Admin can edit all roles except Super Admin
- Cannot change own role

---

## Feature Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| Dashboard | ✅ Complete | KPIs, analytics, employee tiles |
| Employee Management | ✅ Complete | Search, filter, profile, edit |
| Onboarding Journey | ✅ Complete | 6 unified stages with activities |
| Forms & Quizzes | ✅ Complete | Form builder, quiz engine |
| Medical Management | ✅ Complete | Review queue, approvals |
| Training & Learning | ✅ Complete | Paths, assignments, certificates |
| Live Sessions | ✅ Complete | Registration, attendance tracking |
| Zoom Integration | ✅ Complete | OAuth, auto-link generation |
| Email Templates | ✅ Complete | WYSIWYG editor with formatting |
| Organization Setup | ✅ Complete | Org units, branding, landing page |
| User Management | ✅ Complete | Create, edit, delete users |
| Roles & Permissions | ✅ Complete | 20 core permissions |
| Automation Rules | ✅ Complete | Conditional workflows |
| Reporting & Export | ✅ Complete | CSV export, analytics |

---

## Quick Start by Role

### I'm a Super Admin
1. Go to **Admin > Users & Roles** → Create other users
2. Go to **Admin > Branding** → Set up colors/logo
3. Go to **Admin > Email Settings** → Configure sender
4. Go to **Admin > Organization** → Set up departments
5. Go to **Admin > Forms** → Create pre-onboarding form

### I'm an Admin
1. Go to **Admin > Users** → Create HRBP users
2. Go to **Admin > Forms** → Build forms
3. Go to **Admin > Training Paths** → Create courses
4. Go to **Admin > Email Templates** → Customize emails
5. Go to **Admin > Automation** → Set up rules

### I'm an HRBP
1. Go to **Dashboard** → See team metrics
2. Go to **People** → Find team members
3. Go to **Training** → Assign courses to team
4. Go to **Sessions** → Create orientation session
5. Go to **Employee Profile** → Approve pre-onboarding

### I'm a Medical Approver
1. Go to **Medical Review** → See pending queue
2. Review documents
3. Click Approve/Reject
4. Go to **Medical Requirements** → Set up requirements

### I'm an Employee
1. Go to **Employee Home** → See onboarding journey
2. Go to **Medical** → Upload medical documents
3. Go to **Pre-Onboarding** → Fill forms
4. Go to **Orientation** → Register for sessions
5. Go to **My Learning** → Take courses

---

## Common Questions

**Q: Can HRBP see all employees?**  
A: No, only their department. If you need cross-department access, make them Admin.

**Q: Can Medical Approver approve pre-onboarding forms?**  
A: No, only medical documents. HRBP or Admin must approve forms.

**Q: Can Employee edit their role?**  
A: No, only Super Admin can change roles.

**Q: How do I add Manager role?**  
A: Super Admin > Roles > Create Custom Role "Manager" with specific permissions

**Q: Can I restrict Super Admin?**  
A: No, Super Admin always has full access.

**Q: How do I give HRBP Zoom access?**  
A: HRBPs automatically can create sessions (Zoom credential set by Admin).

---

## Support & Next Steps

- ✅ All core features implemented
- ✅ All role-based access working
- ✅ Rich text editors added
- ✅ File uploads expanded
- ⏳ HRBP dashboard UI enhancements (planned)
- ⏳ Manager role template (available on request)

To create Manager role: Ask Super Admin to create custom role with these permissions:
- view_employees
- manage_onboarding_plans
- assign_training
- (optional) manage_training

---

**Document Version**: 1.0  
**Last Updated**: 2026-06-20  
**Status**: Production Ready ✅

