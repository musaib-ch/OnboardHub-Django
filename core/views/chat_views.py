"""
Real-time chat and messaging views.

Supports direct messaging, conversations list, and @mentions.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib import messages as django_messages

from ..models import User
from ..services.chat_service import (
    send_message,
    get_conversation,
    get_conversations_list,
    mark_as_read,
    search_conversations,
    get_mentions_in_message,
    get_users_by_names,
    send_notification_for_mention,
)
from ..services import log_activity


@login_required
def messages_list(request):
    """View all conversations (inbox)."""
    user = request.user
    search_query = request.GET.get('q', '').strip()

    if search_query:
        conversations = search_conversations(user, search_query)
    else:
        conversations = get_conversations_list(user)

    ctx = {
        'conversations': conversations,
        'search_query': search_query,
        'unread_count': sum(c['unread_count'] for c in conversations),
    }

    return render(request, 'chat/messages_list.html', ctx)


@login_required
def chat_with_user(request, user_id):
    """Open chat with a specific user."""
    sender = request.user
    recipient = get_object_or_404(User, id=user_id)

    # Can't chat with self
    if sender.id == recipient.id:
        return redirect('messages_list')

    # Handle message posting
    if request.method == 'POST':
        message_text = request.POST.get('message', '').strip()

        if not message_text:
            django_messages.error(request, 'Message cannot be empty.')
            return redirect('chat_with_user', user_id=recipient.id)

        try:
            # Extract mentions
            mentioned_names = get_mentions_in_message(message_text)
            mentioned_users = get_users_by_names(mentioned_names) if mentioned_names else []
            mention_ids = [u.id for u in mentioned_users]

            # Send message
            msg = send_message(sender, recipient, message_text, mentions=mention_ids)

            # Send mention notifications
            for mentioned_user in mentioned_users:
                if mentioned_user.id != recipient.id:  # Recipient already gets notification
                    try:
                        send_notification_for_mention(mentioned_user, sender, message_text)
                    except:
                        pass

            log_activity(request, action='send_message', entity_type='chat',
                        description=f'Sent message to {recipient.full_name}')

            django_messages.success(request, 'Message sent!')

        except ValueError as e:
            django_messages.error(request, str(e))

        return redirect('chat_with_user', user_id=recipient.id)

    # GET: Load conversation
    conversation = get_conversation(sender, recipient)

    # Mark as read
    mark_as_read(sender, recipient)

    ctx = {
        'recipient': recipient,
        'conversation': conversation,
        'sender': sender,
    }

    return render(request, 'chat/chat_with_user.html', ctx)


@login_required
@require_http_methods(['POST'])
def send_message_ajax(request, user_id):
    """Send message via AJAX (for real-time chat)."""
    sender = request.user
    recipient = get_object_or_404(User, id=user_id)

    message_text = request.POST.get('message', '').strip()

    if not message_text:
        return JsonResponse({'success': False, 'error': 'Message cannot be empty'}, status=400)

    try:
        # Extract mentions
        mentioned_names = get_mentions_in_message(message_text)
        mentioned_users = get_users_by_names(mentioned_names) if mentioned_names else []
        mention_ids = [u.id for u in mentioned_users]

        # Send message
        msg = send_message(sender, recipient, message_text, mentions=mention_ids)

        # Send mention notifications
        for mentioned_user in mentioned_users:
            if mentioned_user.id != recipient.id:
                try:
                    send_notification_for_mention(mentioned_user, sender, message_text)
                except:
                    pass

        return JsonResponse({
            'success': True,
            'message': {
                'id': msg['id'],
                'sender_name': msg['sender_name'],
                'message': msg['message'],
                'sent_at': msg['sent_at'],
                'mentions': msg.get('mentions', []),
            }
        })

    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(['POST'])
def mark_conversation_read(request, user_id):
    """Mark a conversation as read."""
    user = request.user
    other_user = get_object_or_404(User, id=user_id)

    mark_as_read(user, other_user)

    return JsonResponse({'success': True})


@login_required
def search_users(request):
    """Search for users to start a chat with."""
    query = request.GET.get('q', '').strip()

    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    users = User.objects.filter(
        is_active=True,
        full_name__icontains=query
    ).exclude(id=request.user.id).values('id', 'full_name', 'email', 'role')[:10]

    return JsonResponse({
        'results': list(users)
    })


@login_required
def get_unread_count(request):
    """Get total unread message count."""
    user = request.user
    conversations = get_conversations_list(user)
    unread = sum(c['unread_count'] for c in conversations)

    return JsonResponse({'unread_count': unread})
