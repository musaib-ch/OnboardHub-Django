"""
Chat views — direct messaging with role restrictions, approval flow, attachments.
"""
import os
import uuid

from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from ..models import AppSetting, Engagement, User
from ..services import log_activity
from ..services.chat_service import (
    accept_chat,
    can_delete_chat,
    can_send_message,
    delete_chat,
    get_attachment_retention_days,
    get_conversation,
    get_conversations_list,
    get_mentions_in_message,
    get_or_create_chat,
    get_pending_requests,
    get_unread_count,
    get_users_by_names,
    mark_as_read,
    reject_chat,
    search_conversations,
    send_chat_request_notification,
    send_message,
    send_notification_for_mention,
)

ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".pdf",
    ".doc", ".docx", ".xls", ".xlsx", ".txt", ".zip",
}
MAX_ATTACHMENT_MB = 10


def _save_attachment(uploaded_file):
    """Save uploaded file to media/chat_attachments/. Returns (path, name) or (None, None)."""
    if not uploaded_file:
        return None, None

    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise ValueError(f"File type '{ext}' not allowed.")

    if uploaded_file.size > MAX_ATTACHMENT_MB * 1024 * 1024:
        raise ValueError(f"File too large. Maximum size is {MAX_ATTACHMENT_MB}MB.")

    from django.conf import settings
    folder = os.path.join(settings.MEDIA_ROOT, "chat_attachments")
    os.makedirs(folder, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    full_path = os.path.join(folder, filename)
    with open(full_path, "wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    return f"chat_attachments/{filename}", uploaded_file.name


@login_required
def messages_list(request):
    """Inbox — all active conversations."""
    user = request.user
    query = request.GET.get("q", "").strip()

    conversations = search_conversations(user, query) if query else get_conversations_list(user)
    pending = get_pending_requests(user)

    return render(request, "chat/messages_list.html", {
        "conversations": conversations,
        "pending_requests": pending,
        "search_query": query,
        "unread_count": sum(c["unread_count"] for c in conversations),
        "pending_count": len(pending),
        "can_delete": can_delete_chat(user),
        "attachment_retention_days": get_attachment_retention_days(),
    })


@login_required
def chat_with_user(request, user_id):
    """Open / send in a conversation with a specific user."""
    sender = request.user
    recipient = get_object_or_404(User, id=user_id)

    if sender.id == recipient.id:
        return redirect("messages_list")

    allowed, reason = can_send_message(sender, recipient)
    if not allowed and request.method == "POST":
        django_messages.error(request, reason)
        return redirect("messages_list")

    if request.method == "POST":
        message_text = request.POST.get("message", "").strip()
        uploaded_file = request.FILES.get("attachment")

        attachment_path, attachment_name = None, None
        if uploaded_file:
            try:
                attachment_path, attachment_name = _save_attachment(uploaded_file)
            except ValueError as e:
                django_messages.error(request, str(e))
                return redirect("chat_with_user", user_id=recipient.id)

        if not message_text and not attachment_path:
            django_messages.error(request, "Please enter a message or attach a file.")
            return redirect("chat_with_user", user_id=recipient.id)

        try:
            # Check if this is the very first message (new chat request)
            from ..services.chat_service import _get_chat
            existing = _get_chat(sender, recipient)
            is_first = existing is None

            mentioned_names = get_mentions_in_message(message_text) if message_text else []
            mentioned_users = get_users_by_names(mentioned_names)
            mention_ids = [u.id for u in mentioned_users]

            msg = send_message(
                sender, recipient, message_text,
                mentions=mention_ids,
                attachment_path=attachment_path,
                attachment_name=attachment_name,
            )

            # If first message, send approval request notification
            if is_first:
                chat = _get_chat(sender, recipient)
                send_chat_request_notification(recipient, sender, chat.id)
                django_messages.info(request, f"Message sent to {recipient.full_name}. Waiting for them to accept.")
            else:
                # Mention notifications
                for mu in mentioned_users:
                    if mu.id != recipient.id:
                        try:
                            send_notification_for_mention(mu, sender, message_text)
                        except Exception:
                            pass

            log_activity(request, action="send_message", entity_type="chat",
                         description=f"Sent message to {recipient.full_name}")

        except ValueError as e:
            django_messages.error(request, str(e))

        return redirect("chat_with_user", user_id=recipient.id)

    # GET: load conversation
    from ..services.chat_service import _get_chat
    chat = _get_chat(sender, recipient)
    conversation = chat.data.get("messages", []) if chat else []
    chat_status = chat.status if chat else None

    # If pending and current user is the recipient, show accept/reject UI
    pending_approval = (chat_status == "pending" and chat and chat.counterparty == sender)

    if chat and chat_status == "active":
        mark_as_read(sender, recipient)

    # Check role restriction for UI
    can_send, send_blocked_reason = can_send_message(sender, recipient)

    return render(request, "chat/chat_with_user.html", {
        "recipient": recipient,
        "conversation": conversation,
        "sender": sender,
        "chat": chat,
        "chat_status": chat_status,
        "pending_approval": pending_approval,
        "can_send": can_send,
        "send_blocked_reason": send_blocked_reason,
        "can_delete": can_delete_chat(sender),
        "allowed_extensions": ", ".join(ALLOWED_ATTACHMENT_EXTENSIONS),
        "max_attachment_mb": MAX_ATTACHMENT_MB,
    })


@login_required
@require_http_methods(["POST"])
def accept_chat_request(request, chat_id):
    """Recipient accepts a pending chat request."""
    if accept_chat(chat_id, request.user):
        django_messages.success(request, "Chat request accepted.")
        chat = Engagement.objects.get(id=chat_id)
        return redirect("chat_with_user", user_id=chat.user.id)
    django_messages.error(request, "Could not accept this chat request.")
    return redirect("messages_list")


@login_required
@require_http_methods(["POST"])
def reject_chat_request(request, chat_id):
    """Recipient declines a pending chat request."""
    if reject_chat(chat_id, request.user):
        django_messages.info(request, "Chat request declined.")
    else:
        django_messages.error(request, "Could not decline this chat request.")
    return redirect("messages_list")


@login_required
@require_http_methods(["POST"])
def delete_chat_view(request, chat_id):
    """Admin/super_admin only — delete entire conversation."""
    success, message = delete_chat(chat_id, request.user)
    if success:
        django_messages.success(request, message)
        log_activity(request, action="delete_chat", entity_type="chat",
                     description=f"Deleted chat {chat_id}")
    else:
        django_messages.error(request, message)
    return redirect("messages_list")


@login_required
@require_http_methods(["POST"])
def mark_conversation_read(request, user_id):
    other_user = get_object_or_404(User, id=user_id)
    mark_as_read(request.user, other_user)
    return JsonResponse({"success": True})


@login_required
def search_users_for_chat(request):
    """Search users the current user is allowed to message, including suggestions when the field is empty."""
    query = request.GET.get("q", "").strip()
    user = request.user

    # Employees can only search admin/hrbp/super_admin; other staff can message anyone active.
    if user.role == "employee":
        qs = User.objects.filter(
            is_active=True,
            role__in=["admin", "super_admin", "hrbp"],
        ).exclude(id=user.id)
    else:
        qs = User.objects.filter(
            is_active=True,
        ).exclude(id=user.id)

    if query:
        qs = qs.filter(full_name__icontains=query)

    qs = qs.order_by("full_name").values("id", "full_name", "email", "role")[:10]

    return JsonResponse({"results": list(qs)})


@login_required
def get_unread_count_view(request):
    return JsonResponse({"unread_count": get_unread_count(request.user)})


@login_required
@require_http_methods(["GET", "POST"])
def chat_settings(request):
    """Admin-only: configure chat attachment retention days."""
    if request.user.role not in ("super_admin", "admin"):
        django_messages.error(request, "Permission denied.")
        return redirect("messages_list")

    if request.method == "POST":
        days = request.POST.get("retention_days", "30")
        try:
            days = max(1, int(days))
            AppSetting.set("chat_attachment_retention_days", str(days), user=request.user)
            django_messages.success(request, f"Attachment retention set to {days} days.")
            log_activity(request, action="update_chat_settings", entity_type="chat",
                         description=f"Set attachment retention to {days} days")
        except ValueError:
            django_messages.error(request, "Invalid value.")
        return redirect("chat_settings")

    return render(request, "chat/chat_settings.html", {
        "retention_days": get_attachment_retention_days(),
    })
