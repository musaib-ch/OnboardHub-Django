"""
Chat service — direct messaging between staff and employees.

Rules:
- Employees can only message Admin, Super Admin, or HRBP
- Staff can message anyone
- First message requires recipient approval (pending → active)
- Max 100 messages stored; older ones are trimmed automatically
- Attachments auto-deleted after configurable retention period
- Chats deletable by admin/super_admin only
- Two-sided: conversation stored once, visible to both participants
"""
import os
import uuid
from datetime import timedelta
from typing import Dict, List, Optional

from django.db.models import Q
from django.utils import timezone

from ..models import AppSetting, Engagement, User

MAX_MESSAGES = 100
STAFF_ROLES = {"super_admin", "admin", "hrbp"}
EMPLOYEE_ALLOWED_RECIPIENT_ROLES = {"super_admin", "admin", "hrbp"}


# ─── Permission helpers ────────────────────────────────────────────────────────

def can_send_message(sender: User, recipient: User) -> tuple:
    """
    Returns (allowed: bool, reason: str).
    Employees may only message admin/super_admin/hrbp.
    Staff may message anyone.
    """
    if sender.id == recipient.id:
        return False, "You cannot message yourself."

    if sender.role == "employee":
        if recipient.role not in EMPLOYEE_ALLOWED_RECIPIENT_ROLES:
            return False, "Employees can only message Admins or HR."

    if not recipient.is_active:
        return False, "That user is no longer active."

    return True, ""


def can_delete_chat(user: User) -> bool:
    return user.role in ("super_admin", "admin")


# ─── Conversation storage (single record, both-sided lookup) ──────────────────

def _get_chat(user1: User, user2: User) -> Optional[Engagement]:
    """Fetch the single shared Engagement for this pair (regardless of who initiated)."""
    return Engagement.objects.filter(
        kind="chat_dm"
    ).filter(
        Q(user=user1, counterparty=user2) | Q(user=user2, counterparty=user1)
    ).first()


def get_or_create_chat(sender: User, recipient: User) -> Engagement:
    """Get or create the shared conversation record."""
    chat = _get_chat(sender, recipient)
    if chat:
        return chat

    # New conversation starts as 'pending' — recipient must accept
    chat = Engagement.objects.create(
        user=sender,
        counterparty=recipient,
        kind="chat_dm",
        status="pending",
        data={
            "participant_ids": [sender.id, recipient.id],
            "participant_names": {
                str(sender.id): sender.full_name,
                str(recipient.id): recipient.full_name,
            },
            "messages": [],
            "unread_count": {str(sender.id): 0, str(recipient.id): 0},
            "created_at": timezone.now().isoformat(),
            "last_message_at": None,
        },
    )
    return chat


# ─── Sending messages ─────────────────────────────────────────────────────────

def send_message(sender: User, recipient: User, message: str,
                 mentions: List[int] = None, attachment_path: str = None,
                 attachment_name: str = None) -> Dict:
    """
    Send a direct message. Raises ValueError on permission/status errors.
    Returns the message dict on success.
    """
    allowed, reason = can_send_message(sender, recipient)
    if not allowed:
        raise ValueError(reason)

    if not message.strip() and not attachment_path:
        raise ValueError("Message cannot be empty.")

    chat = get_or_create_chat(sender, recipient)

    # If conversation was rejected, block
    if chat.status == "rejected":
        raise ValueError("This conversation was declined by the recipient.")

    # Build message object
    msg_obj = {
        "id": str(uuid.uuid4())[:8],
        "sender_id": sender.id,
        "sender_name": sender.full_name,
        "message": message.strip(),
        "mentions": mentions or [],
        "sent_at": timezone.now().isoformat(),
        "read": False,
        "read_at": None,
        "attachment_path": attachment_path,
        "attachment_name": attachment_name,
        "attachment_uploaded_at": timezone.now().isoformat() if attachment_path else None,
    }

    messages = chat.data.get("messages", [])
    messages.append(msg_obj)

    # Enforce 100-message limit — trim oldest
    if len(messages) > MAX_MESSAGES:
        removed = messages[:-MAX_MESSAGES]
        messages = messages[-MAX_MESSAGES:]
        # Delete attachment files for trimmed messages
        for old_msg in removed:
            _delete_attachment_file(old_msg.get("attachment_path"))

    chat.data["messages"] = messages
    chat.data["last_message_at"] = msg_obj["sent_at"]
    chat.data["unread_count"][str(recipient.id)] = (
        chat.data.get("unread_count", {}).get(str(recipient.id), 0) + 1
    )

    # First message → stays pending, notify recipient for approval
    # Subsequent messages on active chat → just save
    chat.save()

    return msg_obj


# ─── Approval system ──────────────────────────────────────────────────────────

def accept_chat(chat_id: int, user: User) -> bool:
    """Recipient accepts the chat request."""
    try:
        chat = Engagement.objects.get(id=chat_id, kind="chat_dm", counterparty=user, status="pending")
        chat.status = "active"
        chat.save(update_fields=["status"])
        return True
    except Engagement.DoesNotExist:
        return False


def reject_chat(chat_id: int, user: User) -> bool:
    """Recipient declines the chat request."""
    try:
        chat = Engagement.objects.get(id=chat_id, kind="chat_dm", counterparty=user, status="pending")
        chat.status = "rejected"
        chat.save(update_fields=["status"])
        return True
    except Engagement.DoesNotExist:
        return False


def get_pending_requests(user: User) -> List[Dict]:
    """Get pending chat requests where user is the recipient."""
    chats = Engagement.objects.filter(kind="chat_dm", counterparty=user, status="pending")
    result = []
    for chat in chats:
        msgs = chat.data.get("messages", [])
        first_msg = msgs[0] if msgs else None
        result.append({
            "chat_id": chat.id,
            "from_user_id": chat.user.id,
            "from_user_name": chat.user.full_name,
            "from_user_role": chat.user.role,
            "first_message": first_msg.get("message", "") if first_msg else "",
            "sent_at": first_msg.get("sent_at", "") if first_msg else "",
        })
    return result


# ─── Reading conversations ─────────────────────────────────────────────────────

def get_conversation(user: User, other_user: User) -> List[Dict]:
    """Get all messages in a conversation (both directions)."""
    chat = _get_chat(user, other_user)
    if not chat:
        return []
    return chat.data.get("messages", [])


def get_conversations_list(user: User) -> List[Dict]:
    """
    Get all conversations for a user, including pending and active chats.
    Two-sided: shows both sent and received conversations.
    """
    chats = Engagement.objects.filter(
        kind="chat_dm",
        status__in=["pending", "active"],
    ).filter(
        Q(user=user) | Q(counterparty=user)
    )

    result = []
    for chat in chats:
        other = chat.counterparty if chat.user == user else chat.user
        msgs = chat.data.get("messages", [])
        last_msg = msgs[-1] if msgs else None
        result.append({
            "chat_id": chat.id,
            "user_id": other.id,
            "user_name": other.full_name,
            "user_email": other.email,
            "user_role": other.role,
            "last_message": (last_msg.get("message") or "📎 Attachment")[:80] if last_msg else "",
            "last_message_at": last_msg.get("sent_at") if last_msg else None,
            "last_sender_name": last_msg.get("sender_name", "") if last_msg else "",
            "unread_count": chat.data.get("unread_count", {}).get(str(user.id), 0),
            "message_count": len(msgs),
        })

    result.sort(key=lambda x: x["last_message_at"] or "", reverse=True)
    return result


def mark_as_read(user: User, other_user: User) -> None:
    """Mark all messages from other_user as read."""
    chat = _get_chat(user, other_user)
    if not chat:
        return
    chat.data["unread_count"][str(user.id)] = 0
    for msg in chat.data.get("messages", []):
        if msg.get("sender_id") != user.id and not msg.get("read"):
            msg["read"] = True
            msg["read_at"] = timezone.now().isoformat()
    chat.save()


def search_conversations(user: User, query: str) -> List[Dict]:
    """Search through active conversations."""
    return [
        c for c in get_conversations_list(user)
        if query.lower() in c["user_name"].lower()
        or query.lower() in c["user_email"].lower()
        or query.lower() in c["last_message"].lower()
    ]


# ─── Deletion ─────────────────────────────────────────────────────────────────

def delete_chat(chat_id: int, requesting_user: User) -> tuple:
    """Delete a chat. Only admin/super_admin allowed."""
    if not can_delete_chat(requesting_user):
        return False, "Only admins can delete chats."
    try:
        chat = Engagement.objects.get(id=chat_id, kind="chat_dm")
        # Delete all attachment files
        for msg in chat.data.get("messages", []):
            _delete_attachment_file(msg.get("attachment_path"))
        chat.delete()
        return True, "Chat deleted."
    except Engagement.DoesNotExist:
        return False, "Chat not found."


# ─── Attachments ──────────────────────────────────────────────────────────────

def get_attachment_retention_days() -> int:
    val = AppSetting.get("chat_attachment_retention_days", "30")
    try:
        return max(1, int(val))
    except (ValueError, TypeError):
        return 30


def _delete_attachment_file(path: str) -> None:
    if not path:
        return
    try:
        from django.conf import settings
        full_path = os.path.join(settings.MEDIA_ROOT, path)
        if os.path.exists(full_path):
            os.remove(full_path)
    except Exception:
        pass


def purge_expired_attachments() -> int:
    """Delete attachment files older than retention period. Returns count deleted."""
    retention_days = get_attachment_retention_days()
    cutoff = timezone.now() - timedelta(days=retention_days)
    count = 0

    chats = Engagement.objects.filter(kind="chat_dm")
    for chat in chats:
        changed = False
        for msg in chat.data.get("messages", []):
            if not msg.get("attachment_path"):
                continue
            uploaded_at_str = msg.get("attachment_uploaded_at")
            if not uploaded_at_str:
                continue
            try:
                from django.utils.dateparse import parse_datetime
                uploaded_at = parse_datetime(uploaded_at_str)
                if uploaded_at and uploaded_at < cutoff:
                    _delete_attachment_file(msg["attachment_path"])
                    msg["attachment_path"] = None
                    msg["attachment_name"] = None
                    msg["message"] = msg.get("message") or "[Attachment expired]"
                    changed = True
                    count += 1
            except Exception:
                pass
        if changed:
            chat.save()

    return count


# ─── Mentions ─────────────────────────────────────────────────────────────────

def get_mentions_in_message(message: str) -> List[str]:
    import re
    return list(set(re.findall(r"@(\w+)", message)))


def get_users_by_names(names: List[str]) -> List[User]:
    users = []
    for name in names:
        try:
            users.append(User.objects.get(full_name__icontains=name))
        except User.DoesNotExist:
            pass
    return users


def send_notification_for_mention(mentioned_user: User, sender: User, message: str) -> None:
    from .email_service import EmailService
    EmailService.send_email(
        to_email=mentioned_user.email,
        template_key="chat_mention",
        context={
            "employee_name": mentioned_user.full_name,
            "sender_name": sender.full_name,
            "message_preview": message[:100],
            "chat_link": "/messages/",
        },
        user=mentioned_user,
        log_event=True,
    )


def send_chat_request_notification(recipient: User, sender: User, chat_id: int) -> None:
    """Notify recipient of a new chat request."""
    from .email_service import EmailService
    try:
        EmailService.send_email(
            to_email=recipient.email,
            template_key="chat_request",
            context={
                "employee_name": recipient.full_name,
                "sender_name": sender.full_name,
                "chat_link": f"/messages/requests/",
            },
            user=recipient,
            log_event=False,
        )
    except Exception:
        pass


def get_unread_count(user: User) -> int:
    chats = Engagement.objects.filter(
        kind="chat_dm", status="active"
    ).filter(Q(user=user) | Q(counterparty=user))
    return sum(
        c.data.get("unread_count", {}).get(str(user.id), 0)
        for c in chats
    )
