# Phase 3: Complete LMS + Zoom Integration Specification

## Requirements Summary

### 1. Key Working Features ✅
- Sequential stages (pre-board → day 1 → week 1 → 30/60/90)
- Role-based content paths (Sales ≠ Eng content)
- Completion tracking (%)
- Nudge notifications (reminders)
- Video + quizzes (proof of understanding)
- Manager approval (compliance)
- Time tracking (per module)
- Certificates (on completion)

### 2. Core LMS Features ✅
- Prerequisites & branching
- Assessments (multiple choice, T/F, essay) with min scores + retries
- Certificates (auto-generated PDF)
- Progress tracking (time, completion %, scores)
- Content variants by: role, location, division, department

### 3. Zoom Integration Dashboard ✅
- Create live sessions (orientation, 30/60/90 day reviews)
- Auto-create Zoom meetings
- Send calendar invites
- Dashboard showing all sessions
- Permissions:
  - Employee: can create (needs HRBP approval), view all
  - Manager: can create (no approval), view team + all, FYI on all
  - HRBP: can create (no approval), view all, FYI on all
- Auto-record sessions → store in Content library

### 4. Presentation Pattern (SCORM-like) ✅
- PPTX files → convert to SCORM package
- Tracking: completion, time-on-task, interactions
- Apply to: orientations, trainings, 30/60/90 reviews
- PPTX + SCORM formats supported

### 5. Assessment + Filtering ✅
- Quizzes with min criteria (e.g., 80% to pass)
- Multiple attempts (1-3 retries with cooldown)
- Filtering by: role, location, division, department
- Role-based content paths
- Location-based variants
- Department/Division segregation

---

## Database Models to Create/Modify

### New Models
1. `CourseLesson` - Granular lesson structure
2. `Assessment` - Quiz/assessment definition
3. `AssessmentQuestion` - Q&A pair
4. `StudentCourseProgress` - Track enrollment + progress
5. `QuizAttempt` - Track each quiz attempt
6. `LiveSession` - Zoom session scheduling
7. `LiveSessionAttendee` - Who attended/registered
8. `ContentVariant` - Role/location/dept-specific content
9. `CourseCertificate` - Certificate template per course
10. `Prerequisite` - Course dependencies

### Modified Models
- `Content`: add assessment_required, min_score, role, location, division, department
- `LearningPath`: add prerequisites, branching logic
- `User`: track preferred_location, preferred_division

---

## Implementation Phases

### Phase 3.1: Assessment + Progress Foundation (3 days)
- Create Assessment + AssessmentQuestion models
- Create StudentCourseProgress + QuizAttempt models
- Build assessment grading engine (min scores, retries)
- Create quiz attempt tracking

### Phase 3.2: Content Variants + Filtering (2 days)
- Add role/location/dept fields to Content model
- Create filtering logic in views
- Build filter UI on content library
- Create role-based content path builder

### Phase 3.3: Zoom Integration + Dashboard (3 days)
- Create LiveSession + LiveSessionAttendee models
- Integrate Zoom API (create meeting, get join URL)
- Build session calendar/dashboard
- Add calendar invite sending (Outlook/Google)
- Build approval workflow (employee → HRBP)
- Auto-record session storage

### Phase 3.4: Presentation Package + SCORM (2 days)
- Create PPTX → SCORM converter
- Build presentation player
- Track: completion, time, slide interactions
- Auto-certificate on completion

### Phase 3.5: Certificates + Final Polish (2 days)
- Certificate template creation
- PDF generation on course completion
- Email certificates
- Display in employee record

---

## Start Implementation?

**Estimated total: 12 days, can be parallelized to 5-6 days**

Shall we begin with **3.1 (Assessment foundation)** — most critical for rest of system?
