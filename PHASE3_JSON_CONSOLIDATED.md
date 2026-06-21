# Phase 3: JSON-Consolidated Design (Zero New Tables)

## Architecture: Consolidate into 13 Existing Tables

### 1. **Assessment/Quiz Data** → Store in `Content.meta`

When `Content.kind = 'training'`:
```json
{
  "lessons": [
    {
      "id": "lesson-slug",
      "title": "Lesson 1: Intro",
      "order": 1,
      "duration_minutes": 15,
      "content_html": "<p>Lesson content...</p>",
      "video_url": "https://youtube.com/...",
      
      "has_assessment": true,
      "assessment": {
        "id": "assess-1",
        "passing_score": 80,
        "max_attempts": 3,
        "retry_cooldown_hours": 24,
        "randomize_questions": false,
        "show_answers_on_completion": true,
        "questions": [
          {
            "id": "q1",
            "type": "multiple_choice",
            "text": "What is X?",
            "points": 1,
            "options": [
              {"text": "Option A", "is_correct": true},
              {"text": "Option B", "is_correct": false}
            ],
            "explanation": "Option A is correct because..."
          },
          {
            "id": "q2",
            "type": "true_false",
            "text": "True or False: X is Y?",
            "correct_answer": "true",
            "points": 1
          }
        ]
      }
    }
  ]
}
```

### 2. **Student Progress/Quiz Attempts** → Store in `Engagement.data`

When `Engagement.kind = 'enrollment'`:
```json
{
  "progress": {
    "status": "in_progress",
    "enrolled_at": "2026-06-19T10:00:00Z",
    "started_at": "2026-06-19T10:30:00Z",
    "completion_percentage": 50,
    "lessons_completed": 2,
    "total_lessons": 4,
    "time_spent_minutes": 45,
    "final_score": null,
    
    "quiz_attempts": [
      {
        "lesson_id": "lesson-1",
        "assessment_id": "assess-1",
        "attempt_number": 1,
        "status": "graded",
        "started_at": "2026-06-19T10:45:00Z",
        "submitted_at": "2026-06-19T10:55:00Z",
        "time_spent_seconds": 600,
        "score_percentage": 85,
        "earned_points": 17,
        "total_points": 20,
        "passed": true,
        "answers": {
          "q1": {"answer": "Option A", "is_correct": true},
          "q2": {"answer": "true", "is_correct": true}
        }
      },
      {
        "lesson_id": "lesson-1",
        "assessment_id": "assess-1",
        "attempt_number": 2,
        "status": "graded",
        "started_at": "2026-06-20T14:00:00Z",
        "submitted_at": "2026-06-20T14:08:00Z",
        "score_percentage": 95,
        "earned_points": 19,
        "total_points": 20,
        "passed": true
      }
    ],
    
    "certificate": {
      "issued_at": "2026-06-20T15:00:00Z",
      "certificate_id": "cert-emp-6-training-1",
      "file_url": "/certificates/..."
    }
  }
}
```

### 3. **Zoom Configuration** → Store in `AppSetting`

```
key: "zoom_oauth"
value: {
  "account_id": "ABC123",
  "client_id": "zoom_client_id",
  "client_secret": "zoom_secret",
  "access_token": "access_token_xyz",
  "refresh_token": "refresh_token_xyz",
  "token_expires_at": "2026-06-20T10:00:00Z",
  "is_configured": true,
  "default_duration_minutes": 60,
  "enable_waiting_room": true,
  "enable_recording": true,
  "auto_record_type": "cloud",
  "last_sync_at": "2026-06-19T20:00:00Z",
  "last_error": null
}
```

### 4. **Live Sessions** → Store in `Content` (new kind) + Attendance in `Engagement`

When `Content.kind = 'live_session'`:
```json
{
  "session_type": "orientation",  // orientation, 30_day_review, 60_day_review, 90_day_review, training
  "scheduled_date": "2026-06-20T10:00:00Z",
  "duration_minutes": 60,
  "timezone": "UTC",
  
  "status": "approved",  // draft, pending_approval, approved, scheduled, in_progress, completed
  "created_by": 2,  // user_id
  "approved_by": 3,  // user_id (HRBP/Admin)
  "approved_at": "2026-06-19T15:00:00Z",
  
  "zoom": {
    "meeting_id": "123456789",
    "join_url": "https://zoom.us/j/123456789",
    "start_url": "https://zoom.us/s/...",
    "recording_url": "https://zoom.us/rec/...",
    "is_recorded": true,
    "recording_file_id": "rec-12345"
  },
  
  "permissions": {
    "employee_can_create": true,
    "employee_needs_approval": true,
    "manager_can_approve_attendees": true
  },
  
  "attendee_count": 15,
  "attendee_approved_count": 12
}
```

When `Engagement.kind = 'session'` (attendee tracking):
```json
{
  "attendees": [
    {
      "user_id": 6,
      "status": "approved",  // invited, pending_approval, approved, declined, attended, no_show
      "approved_by": 3,
      "approved_at": "2026-06-19T16:00:00Z",
      
      "joined_at": "2026-06-20T10:05:00Z",
      "left_at": "2026-06-20T11:05:00Z",
      "duration_minutes": 60,
      
      "engagement": {
        "raised_hand": 2,
        "asked_questions": 1,
        "shared_screen": false
      },
      
      "feedback": "Great orientation!",
      "rating": 5
    },
    {
      "user_id": 7,
      "status": "no_show"
    }
  ]
}
```

### 5. **Content Filtering** → Add to `Content` model

Add fields (NOT new table):
- `target_roles` - JSON array: ["admin", "hrbp", "manager", "employee"]
- `target_locations` - JSON array: [1, 3, 5] (OrgUnit IDs)
- `target_departments` - JSON array: [2, 4] (Department OrgUnit IDs)
- `target_divisions` - JSON array: [1] (Division OrgUnit IDs)
- `prerequisite_content` - FK to Content (for sequential unlocking)
- `sequence_order` - IntegerField

This allows filtering without creating new tables.

---

## Services Layer (No DB Impact)

### `core/services/assessment_service.py`
- `get_course_lessons(course)` - Extract lessons from Content.meta
- `get_assessment(lesson)` - Get quiz from lesson
- `submit_quiz(student, assessment, answers)` - Grade and store in Engagement.data
- `get_progress(student, course)` - Read from Engagement.data
- `generate_certificate(student, course)` - Create PDF and store in Engagement.data

### `core/services/zoom_service.py`
- `get_zoom_config()` - Read from AppSetting["zoom_oauth"]
- `create_meeting()` - Call Zoom API, store meeting_id in Content.meta
- `refresh_token()` - Get new access token, update AppSetting
- `get_recordings()` - Fetch from Zoom API

### `core/services/session_service.py`
- `create_session()` - Create Content with kind='live_session'
- `register_attendee()` - Add to Engagement.data attendees
- `approve_attendee()` - Update attendee status in Engagement.data
- `mark_attended()` - Track attendance in Engagement.data

---

## Views (Same Logic, Different Data Source)

Views read from JSON instead of ORM:
- Assessment views query `Content.meta['lessons']`
- Progress views query `Engagement.data['progress']`
- Session views query `Content.meta['zoom']` and `Engagement.data['attendees']`

---

## Benefits

✅ **Zero new tables** (stays at 13)  
✅ **Flexible JSON structure** (easy to add fields)  
✅ **Query-friendly** (Content and Engagement still queryable)  
✅ **Scales easily** (add assessments/sessions without schema changes)  
✅ **Maintains existing patterns** (uses Content/Engagement/AppSetting)

---

## Migration Path

Just add 6 fields to existing Content model:
```python
target_roles = JSONField(default=list)
target_locations = JSONField(default=list)
target_departments = JSONField(default=list)
target_divisions = JSONField(default=list)
prerequisite_content = ForeignKey(Content, ...)
sequence_order = IntegerField(default=0)
```

**One small migration, zero new tables.**

---

## Next: Build Views & Services
1. Create assessment_service.py (JSON-based quiz grading)
2. Create zoom_service.py (OAuth + API integration)
3. Create session_service.py (session management)
4. Create views that use these services
5. Add navigation links

**All using existing 13 tables.**
