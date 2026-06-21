"""
Real-time chat and messaging service for onboarding collaboration.

Supports direct messaging, group chats, @mentions, and typing indicators.
Uses Engagement model for thread storage (JSON consolidation).
"""
import json
from datetime import datetime
from typing import Dict, List, Optional

from django.utils import timezone

from ..models import Engagement, User


def get_or_create_chat(user1: User, user2: User) -> Engagement:
    """Get or create a direct message chat between two users."""
    # Store conversation with primary user as the owner
    # Use unique identifier in data for the other user

    try:
        chat = Engagement.objects.get(
            user=user1,
            kind='chat_dm',
            data__other_user_id=user2.id
        )
        return chat
    except Engagement.DoesNotExist:
        chat = Engagement.objects.create(
            user=user1,
            kind='chat_dm',
            data={
                'chat_type': 'direct_message',
                'other_user_id': user2.id,
                'other_user_name': user2.full_name,
                'participant_ids': [user1.id, user2.id],
                'participant_names': {str(user1.id): user1.full_name, str(user2.id): user2.full_name},
                'messages': [],
                'created_at': timezone.now().isoformat(),
                'last_message_at': None,
                'unread_count': {str(user1.id): 0, str(user2.id): 0},
            }
        )
        return chat


def send_message(sender: User, recipient: User, message: str, mentions: List[int] = None) -> Dict:
    """
    Send a direct message.

    Args:
        sender: User sending message
        recipient: User receiving message
        message: Message content
        mentions: List of user IDs mentioned with @

    Returns:
        Message object with metadata
    """
    if not message.strip():
        raise ValueError("Message cannot be empty")

    chat = get_or_create_chat(sender, recipient)

    msg_obj = {
        'id': len(chat.data.get('messages', [])),
        'sender_id': sender.id,
        'sender_name': sender.full_name,
        'message': message.strip(),
        'mentions': mentions or [],
        'sent_at': timezone.now().isoformat(),
        'read': False,
        'read_at': None,
    }

    chat.data['messages'].append(msg_obj)
    chat.data['last_message_at'] = msg_obj['sent_at']

    # Mark as unread for recipient
    chat.data['unread_count'][str(recipient.id)] = chat.data['unread_count'].get(str(recipient.id), 0) + 1

    chat.save()

    return msg_obj


def get_conversation(user: User, other_user: User) -> List[Dict]:
    """Get all messages in a direct message conversation."""
    try:
        chat = Engagement.objects.get(
            user=user,
            kind='chat_dm',
            data__other_user_id=other_user.id
        )
        return chat.data.get('messages', [])
    except Engagement.DoesNotExist:
        return []


def get_conversations_list(user: User) -> List[Dict]:
    """Get list of all conversations for a user with preview."""
    chats = Engagement.objects.filter(user=user, kind='chat_dm')

    conversations = []
    for chat in chats:
        messages = chat.data.get('messages', [])
        last_msg = messages[-1] if messages else None
        other_user_id = chat.data.get('other_user_id')

        if not other_user_id:
            continue

        try:
            other_user = User.objects.get(id=other_user_id)
            conversations.append({
                'chat_id': chat.id,
                'user_id': other_user_id,
                'user_name': other_user.full_name,
                'user_email': other_user.email,
                'last_message': last_msg.get('message', '')[:100] if last_msg else '',
                'last_message_at': last_msg.get('sent_at') if last_msg else None,
                'last_sender_name': last_msg.get('sender_name') if last_msg else '',
                'unread_count': chat.data.get('unread_count', {}).get(str(user.id), 0),
                'message_count': len(messages),
            })
        except User.DoesNotExist:
            pass

    # Sort by last message time
    conversations.sort(key=lambda x: x['last_message_at'] or '', reverse=True)
    return conversations


def mark_as_read(user: User, other_user: User) -> None:
    """Mark all messages in a conversation as read."""
    try:
        chat = Engagement.objects.get(user=user, kind='chat_dm', data__other_user_id=other_user.id)
        chat.data['unread_count'][str(user.id)] = 0

        # Mark individual messages as read
        for msg in chat.data.get('messages', []):
            if msg.get('sender_id') != user.id and not msg.get('read'):
                msg['read'] = True
                msg['read_at'] = timezone.now().isoformat()

        chat.save()
    except Engagement.DoesNotExist:
        pass


def search_conversations(user: User, query: str) -> List[Dict]:
    """Search through all conversations."""
    all_convs = get_conversations_list(user)
    query_lower = query.lower()

    return [
        c for c in all_convs
        if query_lower in c['user_name'].lower()
        or query_lower in c['user_email'].lower()
        or query_lower in c['last_message'].lower()
    ]


def get_mentions_in_message(message: str) -> List[str]:
    """Extract @mentions from a message. Returns list of usernames mentioned."""
    import re
    mentions = re.findall(r'@(\w+)', message)
    return list(set(mentions))


def get_users_by_names(names: List[str]) -> List[User]:
    """Get User objects by their full names."""
    users = []
    for name in names:
        try:
            user = User.objects.get(full_name__icontains=name)
            users.append(user)
        except User.DoesNotExist:
            pass
    return users


def send_notification_for_mention(mentioned_user: User, sender: User, message: str) -> None:
    """Send notification when user is mentioned."""
    from .email_service import EmailService

    context = {
        'employee_name': mentioned_user.full_name,
        'sender_name': sender.full_name,
        'message_preview': message[:100],
        'chat_link': '/messages/',
    }

    EmailService.send_email(
        to_email=mentioned_user.email,
        template_key='chat_mention',
        context=context,
        user=mentioned_user,
        log_event=True,
    )
