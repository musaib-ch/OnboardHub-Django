"""
Assessment and quiz views (Phase 3 - JSON consolidated).

Handles: course enrollment, lessons, quizzes, grading, progress.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages

from ..models import Content, Engagement, User
from ..services import assessment_service
from ..services.email_triggers import send_quiz_results, send_course_completion
from ..services.notification_service import should_send_email


@login_required
def course_lessons(request, course_id):
    """View all lessons in a course with progress."""
    course = get_object_or_404(Content, id=course_id, kind='training')

    # Check if user can access
    if not assessment_service.filter_content_for_user(request.user, [course]):
        return render(request, '403.html', status=403)

    # Get or create progress
    progress_obj = assessment_service.get_or_create_progress(request.user, course)
    progress_data = progress_obj.data.get('progress', {})

    lessons = assessment_service.get_course_lessons(course)

    # Add completion status to each lesson
    lesson_list = []
    for lesson in lessons:
        completed = any(
            a.get('lesson_id') == lesson.get('id') and a.get('passed')
            for a in progress_data.get('quiz_attempts', [])
        )
        lesson_list.append({
            'lesson': lesson,
            'completed': completed,
        })

    ctx = {
        'course': course,
        'progress': progress_data,
        'lessons': lesson_list,
        'completion_percentage': progress_data.get('completion_percentage', 0),
    }

    return render(request, 'assessments/course_lessons.html', ctx)


@login_required
def lesson_detail(request, course_id, lesson_id):
    """View lesson content."""
    course = get_object_or_404(Content, id=course_id, kind='training')

    # Check access
    if not assessment_service.filter_content_for_user(request.user, [course]):
        return render(request, '403.html', status=403)

    # Get lesson
    lessons = assessment_service.get_course_lessons(course)
    lesson = next((l for l in lessons if l.get('id') == lesson_id), None)

    if not lesson:
        messages.error(request, 'Lesson not found.')
        return redirect('course_lessons', course_id=course_id)

    # Get progress
    progress_data = assessment_service.get_progress(request.user, course)
    if not progress_data:
        progress_data = {'lessons_completed': 0, 'quiz_attempts': []}

    # Check prerequisite
    if course.prerequisite_content:
        prereq_progress = assessment_service.get_progress(request.user, course.prerequisite_content)
        if not prereq_progress or prereq_progress.get('status') != 'completed':
            messages.error(request, f'You must complete {course.prerequisite_content.title} first.')
            return redirect('course_lessons', course_id=course_id)

    # Mark as viewed (optional tracking)
    if request.method == 'POST' and request.POST.get('action') == 'mark_complete':
        # Lesson viewed - progress will update on assessment completion
        pass

    assessment = assessment_service.get_assessment(lesson)
    can_take_assessment = assessment and lesson.get('has_assessment')

    # Check if already passed
    already_passed = any(
        a.get('lesson_id') == lesson_id and a.get('passed')
        for a in progress_data.get('quiz_attempts', [])
    )

    # Video resume position
    video_resume_seconds = assessment_service.get_video_position(request.user, course, lesson_id)

    ctx = {
        'course': course,
        'lesson': lesson,
        'progress': progress_data,
        'assessment': assessment,
        'can_take_assessment': can_take_assessment,
        'already_passed': already_passed,
        'video_resume_seconds': video_resume_seconds,
    }

    return render(request, 'assessments/lesson_detail.html', ctx)


@login_required
def take_quiz(request, course_id, lesson_id):
    """Quiz player interface."""
    course = get_object_or_404(Content, id=course_id, kind='training')

    if not assessment_service.filter_content_for_user(request.user, [course]):
        return render(request, '403.html', status=403)

    lessons = assessment_service.get_course_lessons(course)
    lesson = next((l for l in lessons if l.get('id') == lesson_id), None)

    if not lesson:
        messages.error(request, 'Lesson not found.')
        return redirect('course_lessons', course_id=course_id)

    assessment = assessment_service.get_assessment(lesson)
    if not assessment:
        messages.error(request, 'No assessment available.')
        return redirect('lesson_detail', course_id=course_id, lesson_id=lesson_id)

    # Check if can retry
    can_retry = assessment_service.can_retry_quiz(request.user, course, lesson, assessment)
    if not can_retry:
        messages.error(request, 'You have exceeded the maximum attempts for this quiz.')
        return redirect('lesson_detail', course_id=course_id, lesson_id=lesson_id)

    # Get progress for attempt info
    progress_data = assessment_service.get_progress(request.user, course) or {}
    attempts = [a for a in progress_data.get('quiz_attempts', []) if a.get('lesson_id') == lesson_id]
    attempt_number = len(attempts) + 1

    ctx = {
        'course': course,
        'lesson': lesson,
        'assessment': assessment,
        'attempt_number': attempt_number,
        'max_attempts': assessment.get('max_attempts', 3),
        'questions': assessment.get('questions', []),
    }

    return render(request, 'assessments/take_quiz.html', ctx)


@login_required
@require_http_methods(['POST'])
def submit_quiz(request, course_id, lesson_id):
    """Submit quiz answers (AJAX)."""
    course = get_object_or_404(Content, id=course_id, kind='training')

    if not assessment_service.filter_content_for_user(request.user, [course]):
        return JsonResponse({'error': 'Access denied'}, status=403)

    lessons = assessment_service.get_course_lessons(course)
    lesson = next((l for l in lessons if l.get('id') == lesson_id), None)

    if not lesson:
        return JsonResponse({'error': 'Lesson not found'}, status=404)

    assessment = assessment_service.get_assessment(lesson)
    if not assessment:
        return JsonResponse({'error': 'No assessment'}, status=404)

    # Get answers from POST
    answers_dict = {k: v for k, v in request.POST.items() if k != 'csrfmiddlewaretoken'}

    if not answers_dict:
        return JsonResponse({'error': 'No answers provided'}, status=400)

    # Submit and grade
    result = assessment_service.submit_quiz(
        request.user,
        course,
        lesson,
        assessment,
        answers_dict
    )

    # Send quiz results email if enabled
    if should_send_email(request.user, 'quiz_results'):
        passing_score = assessment.get('passing_score', 80)
        feedback = assessment.get('feedback_on_completion', '')
        send_quiz_results(
            employee=request.user,
            quiz_title=lesson.get('title', 'Quiz'),
            score=result.get('score', 0),
            passing_score=passing_score,
            feedback=feedback
        )

    return JsonResponse(result)


@login_required
def quiz_results(request, course_id, lesson_id):
    """View quiz results."""
    course = get_object_or_404(Content, id=course_id, kind='training')

    if not assessment_service.filter_content_for_user(request.user, [course]):
        return render(request, '403.html', status=403)

    lessons = assessment_service.get_course_lessons(course)
    lesson = next((l for l in lessons if l.get('id') == lesson_id), None)

    if not lesson:
        messages.error(request, 'Lesson not found.')
        return redirect('course_lessons', course_id=course_id)

    assessment = assessment_service.get_assessment(lesson)

    # Get latest attempt
    progress_data = assessment_service.get_progress(request.user, course) or {}
    attempts = [a for a in progress_data.get('quiz_attempts', []) if a.get('lesson_id') == lesson_id]

    if not attempts:
        messages.error(request, 'No quiz attempts found.')
        return redirect('lesson_detail', course_id=course_id, lesson_id=lesson_id)

    latest_attempt = attempts[-1]

    # Build question results
    question_results = []
    for question in assessment.get('questions', []):
        q_id = str(question.get('id'))
        answer_data = latest_attempt.get('answers', {}).get(q_id, {})

        question_results.append({
            'question': question,
            'user_answer': answer_data.get('answer', ''),
            'is_correct': answer_data.get('is_correct', False),
            'points_earned': question.get('points', 1) if answer_data.get('is_correct') else 0,
            'total_points': question.get('points', 1),
        })

    can_retry = assessment_service.can_retry_quiz(request.user, course, lesson, assessment)

    ctx = {
        'course': course,
        'lesson': lesson,
        'assessment': assessment,
        'attempt': latest_attempt,
        'question_results': question_results,
        'can_retry': can_retry,
        'show_answers': assessment.get('show_answers_on_completion', True),
    }

    return render(request, 'assessments/quiz_results.html', ctx)


@login_required
@require_http_methods(['POST'])
def save_video_position(request, course_id, lesson_id):
    """AJAX: save how far into a video the user has watched."""
    course = get_object_or_404(Content, id=course_id, kind='training')
    try:
        position = int(request.POST.get('position', 0))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid position'}, status=400)

    assessment_service.save_video_position(request.user, course, lesson_id, position)
    return JsonResponse({'saved': True})


@login_required
def course_progress(request, course_id):
    """Detailed progress dashboard for course."""
    course = get_object_or_404(Content, id=course_id, kind='training')

    if not assessment_service.filter_content_for_user(request.user, [course]):
        return render(request, '403.html', status=403)

    progress_data = assessment_service.get_progress(request.user, course) or {}
    lessons = assessment_service.get_course_lessons(course)

    # Build lesson progress
    lesson_progress = []
    for lesson in lessons:
        attempts = [a for a in progress_data.get('quiz_attempts', []) if a.get('lesson_id') == lesson.get('id')]
        best_score = max([a.get('score_percentage', 0) for a in attempts], default=None)
        completed = any(a.get('passed') for a in attempts)

        lesson_progress.append({
            'lesson': lesson,
            'completed': completed,
            'attempts': len(attempts),
            'best_score': best_score,
            'all_attempts': attempts,
        })

    certificate = assessment_service.get_certificate_data(request.user, course)

    # Send completion email if course is fully completed
    completion_pct = progress_data.get('completion_percentage', 0)
    if completion_pct >= 100 and should_send_email(request.user, 'course_completions'):
        # Mark as email sent to avoid duplicate sends
        if not progress_data.get('completion_email_sent'):
            final_score = int(progress_data.get('final_score', 0))
            cert_link = f'/learn/path/{course.id}/certificate/' if certificate else ''
            send_course_completion(
                employee=request.user,
                course_title=course.title,
                final_score=final_score,
                certificate_link=cert_link
            )
            # Mark as sent
            progress_obj = assessment_service.get_or_create_progress(request.user, course)
            progress_obj.data.setdefault('progress', {})['completion_email_sent'] = True
            progress_obj.save()

    ctx = {
        'course': course,
        'progress': progress_data,
        'lesson_progress': lesson_progress,
        'certificate': certificate,
        'completion_percentage': completion_pct,
    }

    return render(request, 'assessments/course_progress.html', ctx)
