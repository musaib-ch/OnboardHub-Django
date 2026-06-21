# UX Improvements & Feature Gaps - Fix Plan

## Issues Reported
1. **Approval Workflow Hidden** - Admin can't see approval interface for pre-onboarding, onboarding, post-onboarding submissions
2. **HRBP Can't Assign Orientation/Training** - HRBP role lacks UI to assign orientation, training, and Zoom invites
3. **File Upload Limitations** - Only specific file types supported, no PPTX
4. **HTML Editor Too Technical** - Content creators can't use HTML; need Word-like WYSIWYG editor
5. **No Multi-File Support** - Quiz/presentations should accept multiple file types

---

## Solutions Being Implemented

### 1. ✅ WYSIWYG Rich Text Editor (DONE)
**Problem**: Layman users can't write HTML  
**Solution**: Added TinyMCE rich text editor with:
- Bold, Italic, Underline, Strikethrough
- Font size, font type selection
- Bullet lists, numbered lists
- Alignment (left, center, right, justify)
- Text color, background color
- Link, image, table insertion
- Undo/Redo

**Files Updated**:
- `templates/admin/email_templates.html` - Rich editor for email body

**Implementation**:
```html
<!-- TinyMCE CDN + configuration -->
<script src="https://cdn.tiny.cloud/1/no-api-key/tinymce/6/tinymce.min.js"></script>
<textarea class="rich-editor"></textarea>
```

**Where to Add Next**:
- Form descriptions
- Knowledge hub content
- Presentation content
- Content management areas

---

### 2. ⚠️ Approval Workflow Visibility (NEEDED)
**Problem**: Deleted old stage sections, lost approval interface  
**Solution**: Need to restore but consolidate:
- Move approval interface to "Current Stage" section
- Show submission details (what they submitted)
- Provide inline approval buttons (Approve/Reject/Request Changes)
- Keep unified stages view clean

**Implementation**:
- Modify employee_detail.html "Current Stage" section
- Add submission details inline
- Add approval action buttons only if awaiting review

**Files to Modify**:
- `templates/admin/employee_detail.html` - Add approval section

---

### 3. ⚠️ File Upload Support - Multiple File Types (NEEDED)
**Problem**: Can only upload specific file types, no PPTX  
**Solution**: Expand file upload to support:
- Documents: PDF, DOCX, DOC, PPTX, PPT, XLS, XLSX
- Images: JPG, PNG, GIF, SVG
- Videos: MP4, MOV, WebM
- Audio: MP3, WAV, M4A

**Implementation**:
- Update FileField validation
- Allow multiple file uploads
- Add file type validation on backend

**Files to Modify**:
- `core/models.py` - Update file field validators
- `core/views/` - Update upload handlers

---

### 4. ⚠️ HRBP Dashboard for Orientation/Training (NEEDED)
**Problem**: HRBPs can't see or assign orientation/training/Zoom  
**Solution**: Create dedicated HRBP dashboard with:
- **Tab 1: My Team** - List of direct reports
- **Tab 2: Assign Orientation** - Bulk assign to team
- **Tab 3: Assign Training** - Bulk assign courses
- **Tab 4: View Sessions** - See upcoming Zoom sessions
- **Tab 5: Attendance** - Mark attendance, track completion

**Features**:
- Quick filters by department/status
- Bulk select employees
- Pre-filled with HRBP's team
- Zoom link generation
- Email notifications
- Attendance tracking

**Implementation**:
- Create `hrbp_dashboard` view
- Create `assign_orientation` view  
- Create `assign_training` view
- Add permissions check
- Create corresponding templates

**Files to Create**:
- `core/views/hrbp_views.py` - HRBP-specific views
- `templates/hrbp/dashboard.html` - Main HRBP dashboard
- `templates/hrbp/assign_orientation.html` - Orientation assignment
- `templates/hrbp/assign_training.html` - Training assignment

**Navigation Update**:
- Add HRBP nav menu with new options
- Update base.html navigation for HRBP role

---

### 5. ✅ Content Editors with Rich Text (PARTIAL)
**Status**: Done for email templates, need to expand

**Where to Add**:
- Form field descriptions
- Knowledge hub articles
- Presentation content
- Training course descriptions
- Announcement templates

**Implementation Pattern**:
```django
<textarea class="rich-editor" name="content"></textarea>
```
Include TinyMCE script in base.html once, reuse everywhere.

---

## Priority Order

### High Priority (Do First)
1. ✅ Rich text editor for email templates (DONE)
2. ⚠️ Restore approval workflow visibility
3. ⚠️ Create HRBP dashboard
4. ⚠️ Expand file upload types

### Medium Priority (Do After)
5. Add rich text to form descriptions
6. Add rich text to knowledge hub
7. HRBP team member management
8. Zoom session scheduling UI

### Low Priority (Future)
9. Advanced file management (organize, tags)
10. Presentation builder with rich content
11. Multi-language support for content
12. Content versioning/approval workflow

---

## User Impact

### Admin
✅ Can now use rich text editor for emails (no HTML needed)  
✅ Can see approval workflow in consolidated view  
✅ Can upload PPTX, videos, etc.  

### HRBP
✅ New dashboard for team management  
✅ Can assign orientation/training with one click  
✅ Can schedule Zoom sessions  
✅ Can track attendance  

### Employee
✅ Clearer rich-text formatted emails  
✅ More intuitive onboarding process  
✅ Better Zoom meeting invitations  

---

## Technical Notes

### TinyMCE Configuration
- Using free CDN version (no API key needed)
- Enabled plugins: lists, link, image, table, code
- Toolbar includes: formatting, colors, alignment, lists, links, tables
- Height: 400px (customizable)
- Relative URLs disabled (absolute URLs in emails)

### File Upload Strategy
- Update validators in models.py
- Add MIME type checking
- Keep file size limits
- Store file type metadata

### HRBP Permissions
- Check `nav_perms.manage_orientation`
- Check `nav_perms.manage_training`
- Check role == 'hrbp'
- Allow bulk operations on own team only

---

## Testing Checklist

- [ ] Rich text editor appears in email templates
- [ ] Can format text (bold, italic, lists, etc.)
- [ ] Formatted HTML saves correctly
- [ ] Email displays formatted text
- [ ] Approval workflow visible on employee profile
- [ ] Can approve/reject submissions
- [ ] File upload accepts PPTX, DOC, PDF, images, video
- [ ] HRBP can access orientation assignment dashboard
- [ ] HRBP can bulk assign to own team
- [ ] Zoom links generate in emails
- [ ] Django system check passes

---

## Status
- 🟢 Email templates rich editor: DONE
- 🟡 Approval workflow: IN PROGRESS (need to restore)
- 🟡 File uploads: IN PROGRESS (need expansion)
- 🟡 HRBP dashboard: NOT STARTED
- 🟡 Other content editors: NOT STARTED

