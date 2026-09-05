"""
Quiz module — admin builder + employee quiz experience.

Zero new tables.  Everything uses the existing schema:
  • Form(form_kind="quiz")      — the quiz definition
      schema = {
          "quiz_meta": {
              "passing_score": 80,   # percent
              "max_attempts": 3,
              "time_limit_minutes": 0   # 0 = no limit
          },
          "sections": [
              { "title": "...",
                "fields": [
                  {
                    "id": "q1",
                    "field_name": "q_1",
                    "label": "What is X?",
                    "field_type": "radio",         # radio|checkbox|text|textarea
                    "is_required": true,
                    "options": ["A","B","C"],
                    "correct_answer": "A",         # for radio/yesno/dropdown
                    "correct_answers": ["A","C"],  # for checkbox (multi-correct)
                    "points": 1,
                    "explanation": "..."           # shown after submission
                  }
                ]
              }
          ]
      }
  • FormResponse(form=quiz, employee=user, is_draft=False)
      score     = float  (percentage, 0–100)
      answers   = {"q_1": "A", "q_2": ["A","C"], ...}
      files     = {"passed": true/false, "attempt_number": N,
                   "correct_count": N, "total_count": N}
"""
import json

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..decorators import login_required, permission_required
from ..models import Form, FormResponse, User
from ..services import log_activity, notify


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _quiz_meta(form):
    """Return the quiz_meta or settings dict from form.schema (with safe defaults)."""
    meta = (form.schema or {}).get("quiz_meta") or {}
    settings = (form.schema or {}).get("settings") or {}
    combined = dict(settings)
    combined.update(meta)
    return combined


def _passing_score(form):
    return int(_quiz_meta(form).get("passing_score") or 80)


def _max_attempts(form):
    val = _quiz_meta(form).get("max_attempts") or 0
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _time_limit(form):
    val = _quiz_meta(form).get("time_limit_minutes") or 0
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _all_questions(form):
    """Flatten all fields across all sections into one list."""
    questions = []
    for sec in (form.schema or {}).get("sections", []):
        for f in sec.get("fields", []):
            questions.append(f)
    return questions


def _attempt_count(form, user):
    return FormResponse.objects.filter(form=form, employee=user, is_draft=False).count()


def _can_attempt(form, user):
    max_att = _max_attempts(form)
    if max_att == 0:
        return True
    return _attempt_count(form, user) < max_att


def _best_response(form, user):
    """Return the FormResponse with the highest score for this user, or None."""
    responses = FormResponse.objects.filter(
        form=form, employee=user, is_draft=False
    ).order_by("-score")
    return responses.first()


def _latest_response(form, user):
    return FormResponse.objects.filter(
        form=form, employee=user, is_draft=False
    ).order_by("-submitted_at").first()


def _score_answers(form, answers):
    """
    Grade submitted answers against the form schema.
    Returns (score_pct, correct_count, total_count).
    """
    questions = _all_questions(form)
    total = len(questions)
    if total == 0:
        return 100.0, 0, 0

    correct = 0
    for q in questions:
        fname = q.get("field_name") or q.get("id", "")
        qtype = q.get("field_type", "text")
        submitted = answers.get(fname)

        if qtype in ("radio", "dropdown", "yesno"):
            correct_ans = (q.get("correct_answer") or "").strip()
            if correct_ans and str(submitted or "").strip() == correct_ans:
                correct += 1

        elif qtype == "checkbox":
            correct_list = sorted(
                str(v).strip() for v in (q.get("correct_answers") or []) if v
            )
            submitted_list = sorted(
                str(v).strip() for v in (submitted if isinstance(submitted, list) else []) if v
            )
            if correct_list and submitted_list == correct_list:
                correct += 1

        elif qtype in ("text", "textarea"):
            # Text questions are "always correct" (subjective); count them if answered
            if str(submitted or "").strip():
                correct += 1

    score_pct = round((correct / total) * 100, 1)
    return score_pct, correct, total


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN VIEWS
# ─────────────────────────────────────────────────────────────────────────────


@permission_required("manage_forms")
def quiz_responses(request, quiz_id):
    """Admin: view all employee responses for a quiz."""
    quiz = get_object_or_404(Form, id=quiz_id, form_kind="quiz")
    responses = (
        FormResponse.objects.filter(form=quiz, is_draft=False)
        .select_related("employee")
        .order_by("-submitted_at")
    )
    passing = _passing_score(quiz)
    questions = _all_questions(quiz)

    response_data = []
    for r in responses:
        meta = r.files or {}
        response_data.append({
            "response": r,
            "employee": r.employee,
            "score": r.score,
            "passed": r.score is not None and r.score >= passing,
            "attempt_number": meta.get("attempt_number", "—"),
            "correct_count": meta.get("correct_count", "—"),
            "total_count": meta.get("total_count", len(questions)),
        })

    return render(request, "admin/quiz/quiz_responses.html", {
        "quiz": quiz,
        "response_data": response_data,
        "passing_score": passing,
        "questions": questions,
    })


@permission_required("manage_forms")
def quiz_preview(request, quiz_id):
    """Admin: preview quiz as employee."""
    quiz = get_object_or_404(Form, id=quiz_id, form_kind="quiz")
    questions = _all_questions(quiz)
    return render(request, "admin/quiz/quiz_preview.html", {
        "quiz": quiz,
        "questions": questions,
        "quiz_meta": _quiz_meta(quiz),
        "is_preview": True,
    })


# ─────────────────────────────────────────────────────────────────────────────
# EMPLOYEE VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def my_quizzes(request):
    """Employee: list all assigned/available quizzes."""
    all_quizzes = Form.objects.filter(form_kind="quiz", is_active=True)
    quizzes = []
    
    # Security: Only show quizzes explicitly assigned to the user's role
    for q in all_quizzes:
        roles = _quiz_meta(q).get("assigned_roles", [])
        if request.user.role in roles or request.user.role == "super_admin":
            quizzes.append(q)

    if not quizzes:
        messages.warning(request, "No quizzes have been assigned to you yet.")
        return redirect("employee_home")

    quiz_cards = []
    for q in quizzes:
        attempts = _attempt_count(q, request.user)
        max_att = _max_attempts(q)
        best = _best_response(q, request.user)
        passing = _passing_score(q)
        passed = best is not None and best.score is not None and best.score >= passing
        can_try = _can_attempt(q, request.user)
        quiz_cards.append({
            "quiz": q,
            "attempts": attempts,
            "max_attempts": max_att,
            "best_score": best.score if best else None,
            "passed": passed,
            "can_attempt": can_try,
            "passing_score": passing,
            "questions": len(_all_questions(q)),
            "time_limit": _time_limit(q),
        })
    return render(request, "quiz/my_quizzes.html", {"quiz_cards": quiz_cards})


@login_required
@require_http_methods(["GET", "POST"])
def take_quiz(request, quiz_id):
    """Employee: take a quiz."""
    quiz = get_object_or_404(Form, id=quiz_id, form_kind="quiz", is_active=True)

    # Security: Ensure quiz is assigned to user's role
    roles = _quiz_meta(quiz).get("assigned_roles", [])
    if request.user.role not in roles and request.user.role != "super_admin":
        messages.error(request, "This quiz has not been assigned to you.")
        return redirect("my_quizzes")

    if not _can_attempt(quiz, request.user):
        max_att = _max_attempts(quiz)
        messages.warning(
            request,
            f"You have reached the maximum number of attempts ({max_att}) for this quiz."
        )
        return redirect("my_quizzes")

    questions = _all_questions(quiz)
    quiz_meta = _quiz_meta(quiz)

    if request.method == "POST":
        answers = {}
        for q in questions:
            fname = q.get("field_name") or q.get("id", "")
            qtype = q.get("field_type", "text")
            if qtype == "checkbox":
                answers[fname] = request.POST.getlist(f"q_{fname}")
            else:
                answers[fname] = (request.POST.get(f"q_{fname}") or "").strip()

        score_pct, correct, total = _score_answers(quiz, answers)
        attempt_number = _attempt_count(quiz, request.user) + 1
        passed = score_pct >= _passing_score(quiz)

        response = FormResponse.objects.create(
            form=quiz,
            employee=request.user,
            answers=answers,
            score=score_pct,
            is_draft=False,
            submitted_at=timezone.now(),
            files={
                "passed": passed,
                "attempt_number": attempt_number,
                "correct_count": correct,
                "total_count": total,
            },
        )

        log_activity(
            request, action="quiz_submitted", entity_type="form", entity_id=quiz.id,
            description=f"Quiz '{quiz.name}' — score {score_pct}% (attempt {attempt_number})"
        )

        if passed:
            notify(
                request.user,
                f"🎉 Passed: {quiz.name}",
                f"You scored {score_pct}% and passed. Well done!",
                link=f"/quiz/{quiz.id}/result/{response.id}/",
                category="success",
            )
        else:
            can_retry = _can_attempt(quiz, request.user)
            msg = (
                f"You scored {score_pct}%. You need {_passing_score(quiz)}% to pass."
                + (" You may try again." if can_retry else " No retries remaining.")
            )
            notify(
                request.user,
                f"Quiz result: {quiz.name}",
                msg,
                link=f"/quiz/{quiz.id}/result/{response.id}/",
                category="warning",
            )

        return redirect("quiz_result", quiz_id=quiz.id, response_id=response.id)

    # GET: show quiz
    attempt_number = _attempt_count(quiz, request.user) + 1
    attempts_used = attempt_number - 1

    return render(request, "quiz/take_quiz.html", {
        "quiz": quiz,
        "questions": questions,
        "quiz_meta": quiz_meta,
        "passing_score": _passing_score(quiz),
        "time_limit": _time_limit(quiz),
        "attempt_number": attempt_number,
        "attempts_used": attempts_used,
        "max_attempts": _max_attempts(quiz),
    })


@login_required
def quiz_result(request, quiz_id, response_id):
    """Employee: view result of a specific quiz attempt."""
    quiz = get_object_or_404(Form, id=quiz_id, form_kind="quiz")
    response = get_object_or_404(FormResponse, id=response_id, form=quiz)

    # Only the employee themselves (or admin/staff) can see it
    if request.user.role == "employee" and response.employee_id != request.user.id:
        messages.error(request, "You can only view your own quiz results.")
        return redirect("my_quizzes")

    questions = _all_questions(quiz)
    passing = _passing_score(quiz)
    passed = response.score is not None and response.score >= passing
    meta = response.files or {}
    attempts_used = _attempt_count(quiz, response.employee)
    can_retry = _can_attempt(quiz, response.employee)

    # Build per-question breakdown
    answers = response.answers or {}
    question_results = []
    for q in questions:
        fname = q.get("field_name") or q.get("id", "")
        qtype = q.get("field_type", "text")
        submitted = answers.get(fname)
        correct_ans = q.get("correct_answer", "")
        correct_list = q.get("correct_answers", [])

        if qtype in ("radio", "dropdown", "yesno"):
            is_correct = str(submitted or "").strip() == str(correct_ans or "").strip()
        elif qtype == "checkbox":
            cl = sorted(str(v).strip() for v in correct_list if v)
            sl = sorted(str(v).strip() for v in (submitted if isinstance(submitted, list) else []) if v)
            is_correct = bool(cl) and sl == cl
        else:
            is_correct = bool(str(submitted or "").strip())

        question_results.append({
            "question": q,
            "submitted": submitted,
            "correct_answer": correct_ans or correct_list,
            "is_correct": is_correct,
            "explanation": q.get("explanation", ""),
        })

    return render(request, "quiz/quiz_result.html", {
        "quiz": quiz,
        "response": response,
        "passed": passed,
        "score": response.score,
        "passing_score": passing,
        "correct_count": meta.get("correct_count", 0),
        "total_count": meta.get("total_count", len(questions)),
        "attempt_number": meta.get("attempt_number", attempts_used),
        "attempts_used": attempts_used,
        "max_attempts": _max_attempts(quiz),
        "can_retry": can_retry,
        "question_results": question_results,
        "show_answers": True,
    })
