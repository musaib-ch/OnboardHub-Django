"""
Assessment/Quiz service - JSON-based (no new tables).

Handles: course lessons, assessments, quiz attempts, grading, progress.
Data stored in: Content.meta['lessons'] + Engagement.data['progress']
"""
from django.utils import timezone
from datetime import timedelta
import json

from ..models import Content, Engagement, User


def get_course_lessons(course):
    """
    Extract lessons from Content.meta.

    Returns: list of lesson dicts with assessment data
    """
    if course.kind != 'training':
        return []

    lessons = course.meta.get('lessons', [])
    return lessons


def get_lesson(course, lesson_slug):
    """Get a specific lesson by slug."""
    lessons = get_course_lessons(course)
    for lesson in lessons:
        if lesson.get('id') == lesson_slug:
            return lesson
    return None


def get_assessment(lesson):
    """Extract assessment from lesson."""
    if not lesson:
        return None
    return lesson.get('assessment')


def get_or_create_progress(student, course):
    """
    Get or create course enrollment progress.

    Returns: Engagement record with progress data
    """
    progress, created = Engagement.objects.get_or_create(
        kind='enrollment',
        user=student,
        content=course,
        defaults={
            'title': f'Enrolled in {course.title}',
            'status': 'active',
            'data': {
                'progress': {
                    'status': 'enrolled',
                    'enrolled_at': timezone.now().isoformat(),
                    'completion_percentage': 0,
                    'lessons_completed': 0,
                    'total_lessons': len(get_course_lessons(course)),
                    'quiz_attempts': [],
                    'certificate': None,
                }
            }
        }
    )

    if created:
        progress.save()

    return progress


def submit_quiz(student, course, lesson, assessment, answers_dict):
    """
    Submit quiz answers and grade.

    Args:
        student: User object
        course: Content object
        lesson: lesson dict
        assessment: assessment dict
        answers_dict: {question_id: answer_text}

    Returns: {score_percentage, passed, earned_points, total_points}
    """
    # Grade the quiz
    total_points = 0
    earned_points = 0
    question_results = {}

    for question in assessment.get('questions', []):
        q_id = str(question.get('id'))
        total_points += question.get('points', 1)

        user_answer = answers_dict.get(q_id, '').strip()
        is_correct = False

        if question.get('type') == 'multiple_choice':
            for opt in question.get('options', []):
                if opt.get('is_correct') and opt.get('text') == user_answer:
                    is_correct = True
                    break
        elif question.get('type') == 'true_false':
            is_correct = user_answer == question.get('correct_answer')

        if is_correct:
            earned_points += question.get('points', 1)

        question_results[q_id] = {
            'answer': user_answer,
            'is_correct': is_correct,
        }

    score_percentage = int((earned_points / total_points * 100)) if total_points > 0 else 0
    passed = score_percentage >= assessment.get('passing_score', 70)

    # Store attempt in Engagement.data
    progress = get_or_create_progress(student, course)
    progress_data = progress.data.get('progress', {})

    # Find latest attempt number
    attempts = progress_data.get('quiz_attempts', [])
    latest_attempt_num = max([a.get('attempt_number', 0) for a in attempts] + [0])

    attempt = {
        'lesson_id': lesson.get('id'),
        'assessment_id': assessment.get('id'),
        'attempt_number': latest_attempt_num + 1,
        'status': 'graded',
        'started_at': timezone.now().isoformat(),
        'submitted_at': timezone.now().isoformat(),
        'score_percentage': score_percentage,
        'earned_points': earned_points,
        'total_points': total_points,
        'passed': passed,
        'answers': question_results,
    }

    attempts.append(attempt)
    progress_data['quiz_attempts'] = attempts

    # Update completion if passed
    if passed:
        progress_data['lessons_completed'] = progress_data.get('lessons_completed', 0) + 1

    # Calculate completion percentage
    total_lessons = progress_data.get('total_lessons', 1)
    progress_data['completion_percentage'] = int(
        (progress_data.get('lessons_completed', 0) / total_lessons * 100)
    ) if total_lessons > 0 else 0

    # Check if course complete
    if progress_data['lessons_completed'] >= total_lessons:
        progress_data['status'] = 'completed'
        # Generate certificate
        progress_data['certificate'] = {
            'issued_at': timezone.now().isoformat(),
            'certificate_id': f'cert-{student.id}-{course.id}',
        }

    progress.data['progress'] = progress_data
    progress.save()

    return {
        'score_percentage': score_percentage,
        'passed': passed,
        'earned_points': earned_points,
        'total_points': total_points,
        'attempt_number': attempt.get('attempt_number'),
    }


def get_progress(student, course):
    """Get student's course progress."""
    try:
        progress = Engagement.objects.get(
            kind='enrollment',
            user=student,
            content=course,
        )
        return progress.data.get('progress', {})
    except Engagement.DoesNotExist:
        return None


def can_retry_quiz(student, course, lesson, assessment):
    """Check if student can retry assessment."""
    progress_data = get_progress(student, course)
    if not progress_data:
        return True

    attempts = progress_data.get('quiz_attempts', [])
    lesson_attempts = [a for a in attempts if a.get('lesson_id') == lesson.get('id')]

    if len(lesson_attempts) >= assessment.get('max_attempts', 3):
        return False

    if not lesson_attempts:
        return True

    # Check cooldown
    latest = lesson_attempts[-1]
    cooldown_hours = assessment.get('retry_cooldown_hours', 24)
    if cooldown_hours > 0:
        last_attempt = timezone.make_aware(timezone.datetime.fromisoformat(latest.get('submitted_at')))
        cooldown_until = last_attempt + timedelta(hours=cooldown_hours)
        if timezone.now() < cooldown_until:
            return False

    return True


def save_video_position(student, course, lesson_id, position_seconds):
    """Save how far into a video the student has watched (resume support)."""
    progress = get_or_create_progress(student, course)
    video_positions = progress.data.get('video_positions', {})
    video_positions[lesson_id] = {
        'position_seconds': int(position_seconds),
        'saved_at': timezone.now().isoformat(),
    }
    progress.data['video_positions'] = video_positions
    progress.save()


def get_video_position(student, course, lesson_id):
    """Get saved video resume position in seconds (0 if none)."""
    try:
        progress = Engagement.objects.get(kind='enrollment', user=student, content=course)
        return progress.data.get('video_positions', {}).get(lesson_id, {}).get('position_seconds', 0)
    except Engagement.DoesNotExist:
        return 0


def get_certificate_data(student, course):
    """Get certificate info if course completed."""
    progress_data = get_progress(student, course)
    if not progress_data:
        return None

    cert = progress_data.get('certificate')
    if cert and progress_data.get('status') == 'completed':
        return {
            'student_name': student.full_name,
            'course_title': course.title,
            'issued_at': cert.get('issued_at'),
            'certificate_id': cert.get('certificate_id'),
        }

    return None


def filter_content_for_user(user, content_list=None):
    """
    Filter content based on user's role, location, department, division.

    Returns: list of available Content objects
    """
    if content_list is None:
        content_list = Content.objects.filter(is_active=True)

    filtered = []

    for content in content_list:
        # Check role filtering
        target_roles = content.target_roles or []
        if target_roles and user.role not in target_roles:
            continue

        # Check location filtering
        target_locations = content.target_locations or []
        if target_locations:
            user_location_id = getattr(user, 'location_id', None)
            if not user_location_id or user_location_id not in target_locations:
                continue

        # Check department filtering
        target_depts = content.target_departments or []
        if target_depts:
            user_dept_id = getattr(user, 'department_id', None)
            if not user_dept_id or user_dept_id not in target_depts:
                continue

        # Check division filtering
        target_divs = content.target_divisions or []
        if target_divs:
            user_div_id = getattr(user, 'division_id', None)
            if not user_div_id or user_div_id not in target_divs:
                continue

        # Check prerequisites
        if content.prerequisite_content:
            prereq_progress = get_progress(user, content.prerequisite_content)
            if not prereq_progress or prereq_progress.get('status') != 'completed':
                continue

        filtered.append(content)

    # Sort by sequence_order
    filtered.sort(key=lambda c: c.sequence_order)

    return filtered
