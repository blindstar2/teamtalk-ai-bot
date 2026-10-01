#!/usr/bin/env python3
"""
TeamTalk 5 AI Chat Bot
Works with teamtalk.py library
NOTE: In teamtalk.py, message.reply() is a SYNC method (returns None).
Do NOT use `await message.reply(...)` - that causes:
TypeError: 'NoneType' object can't be awaited
"""

import json
import os
import re
import sys
import time
import threading
import asyncio
import logging
from datetime import datetime

try:
    import teamtalk
    from teamtalk.message import DirectMessage
    from teamtalk.enums import UserStatusMode
except ImportError:
    print('=' * 50)
    print('teamtalk.py is not installed!')
    print('Run: python -m pip install teamtalk.py')
    print('=' * 50)
    sys.exit(1)

# Suppress noisy audio block events (event 570)
logging.getLogger('teamtalk').setLevel(logging.ERROR)

from teamtalk.implementation.TeamTalkPy import TeamTalk5 as sdk

from ai_engine import AIEngine
from yt_helper import search_youtube, get_video_info
from stats_store import store
from moderation import Moderation
from prizes import Prizes, MOD_LITE_RIGHTS, BASIC_RIGHTS

# Users the bot currently ignores (nickname lower-case -> reason)
muted_users = {}


# ============================================================
#  MODERATION HELPERS
# ============================================================

def apply_mute(tt, nick, reason, by):
    """Mute a user in memory + persist + TeamTalk subscriptions."""
    nick_key = str(nick).lower()
    muted_users[nick_key] = reason
    moderation.set_muted(nick, True, reason, by)
    try:
        target = find_user_by_name(tt, nick)
        if target is not None:
            uid = int(getattr(target, 'nUserID', 0) or 0)
            tt.subscribe(tt.get_user(uid), sdk.Subscription.SUBSCRIBE_NONE)
    except Exception:
        pass


def apply_unmute(tt, nick, by=''):
    """Remove a mute in memory + persist + TeamTalk subscriptions."""
    nick_key = str(nick).lower()
    muted_users.pop(nick_key, None)
    moderation.set_muted(nick, False)
    try:
        target = find_user_by_name(tt, nick)
        if target is not None:
            uid = int(getattr(target, 'nUserID', 0) or 0)
            for sub in (sdk.Subscription.SUBSCRIBE_USER_MSG,
                        sdk.Subscription.SUBSCRIBE_VOICE,
                        sdk.Subscription.SUBSCRIBE_CHANNEL_MSG):
                tt.subscribe(tt.get_user(uid), sub)
    except Exception:
        pass


# ============================================================
#  PRIZE GRANT HELPERS  (never grant admin - hard rule)
# ============================================================

def _build_account(usertype, rights_names):
    acc = sdk.UserAccount()
    acc.uUserType = usertype
    rights = 0
    for name in rights_names:
        rights |= int(getattr(sdk.UserRight, name, 0) or 0)
    acc.uUserRights = rights
    return acc


def grant_account_prize(nick, username, password):
    """Create a normal (never admin) user account on the server."""
    tt = bot.teamtalks[0]
    acc = _build_account(sdk.UserType.USERTYPE_DEFAULT, BASIC_RIGHTS)
    acc.szUsername = sdk.ttstr(username)
    acc.szPassword = sdk.ttstr(password)
    result = sdk._DoNewUserAccount(tt._tt, acc)
    if result == -1:
        raise ValueError('Server rejected the account (maybe already exists)')
    return True


def grant_modpowers_account(username, password):
    """Create/upgrade an account with moderator-lite rights (never admin)."""
    tt = bot.teamtalks[0]
    acc = _build_account(sdk.UserType.USERTYPE_DEFAULT, MOD_LITE_RIGHTS)
    acc.szUsername = sdk.ttstr(username)
    acc.szPassword = sdk.ttstr(password)
    result = sdk._DoNewUserAccount(tt._tt, acc)
    if result == -1:
        raise ValueError('Server rejected the account (maybe already exists)')
    return True


def grant_channel_prize(nick):
    """Create a permanent channel named after the user; bot keeps op rights."""
    tt = bot.teamtalks[0]
    base = tt.super.getMyChannelID()
    safe = re.sub(r'[^\w\- ]', '', str(nick)).strip()[:30] or ('Home of ' + str(nick))[:30]
    name = safe
    n = 2
    existing = set()
    try:
        for c in tt.super.getServerChannels():
            existing.add(str(getattr(c, 'szName', '') or '').lower())
    except Exception:
        pass
    while name.lower() in existing and n < 20:
        name = safe + ' ' + str(n)
        n += 1
    tt.create_channel(name, base, topic='Prize channel of ' + str(nick))
    chan_id = None
    try:
        for c in tt.super.getServerChannels():
            if str(getattr(c, 'szName', '') or '').lower() == name.lower():
                chan_id = int(getattr(c, 'nChannelID', 0) or 0)
                break
    except Exception:
    	
        pass
    prizes.record_channel(nick, name, chan_id)
    return name, chan_id


def grant_channel_op(nick, channel_id, by='prize system'):
    tt = bot.teamtalks[0]
    target = find_user_by_name(tt, nick)
    if target is None:
        return False, 'not online'
    uid = int(getattr(target, 'nUserID', 0) or 0)
    tt.make_channel_operator(tt.get_user(uid), channel_id)
    return True, 'ok'


def handle_prize_command(cmd, args, message, sender, user_id):
    prefix = config['commands']['prefix']

    if cmd == 'daily':
        ok, streak, prize, _msg = prizes.claim_status(sender)
        if not ok:
            send_reply(message, '📅 You already claimed today, ' + sender + '! Streak: ' + str(streak)
                       + ' day(s). Come back tomorrow!')
            return
        streak, prize, flags = prizes.do_claim(sender)
        store.count_message(user_id, sender)
        msg = '🎉 Day ' + str(streak) + ' claimed!'
        # Activity bonus: very active + regular claimers get channel-op once
        try:
            total_msgs = store.data['users'].get(store.user_key(user_id), {}).get('messages', 0)
            if prizes.should_activity_promote(sender, total_msgs):
                tt0 = bot.teamtalks[0]
                target = find_user_by_name(tt0, sender)
                if target is not None:
                    chan_now = int(getattr(target, 'nChannelID', 0) or 0)
                    if chan_now and prizes.record_activity_op(sender, chan_now):
                        tt0.make_channel_operator(tt0.get_user(int(getattr(target, 'nUserID', 0) or 0)), chan_now)
                        msg += '\n⭐ ACTIVITY BONUS: you are now channel operator here! Keep being awesome.'
        except Exception:
            pass
        if prize == 'account':
            u = prizes._user(sender)
            if u.get('accounts'):
                msg += '\n🎫 You already have an account - this day adds nothing new.'
            else:
                prizes.pending_account(sender, True)
                msg += ('\n🎫 You won a REGISTERED USER ACCOUNT!\n'
                        'Pick a username + password and send:\n'
                        + prefix + 'claimacc [username] [password]\n'
                        '(PM the bot for privacy!)')
        elif prize == 'channel':
            try:
                name, chan_id = grant_channel_prize(sender)
                msg += '\n📺 Your own channel is ready: "' + name + '"'
                if chan_id:
                    ok2, why = grant_channel_op(sender, chan_id)
                    if ok2:
                        msg += '\n⭐ You are now channel operator there!'
                    else:
                        msg += '\n(Join the server, then type ' + prefix + 'opme to get operator)'
            except Exception as e:
                msg += '\n⚠️ Channel creation failed (bot needs permission): ' + str(e)
        elif prize == 'modpowers':
            if flags.get('modpowers_first'):
                prizes.record_modpowers_pending(sender)
                msg += ('\n🛡️ MODERATOR-LITE UNLOCKED! Send (in PM!):\n'
                        + prefix + 'modacc [username] [password]\n'
                        'This creates an account with: move users + kick from channels.\n'
                        'It can NEVER ban, never manage accounts, never be admin.')
            else:
                msg += '\n🛡️ You already have moderator-lite powers (repeat prize).'
        else:
            if flags.get('loyal_first'):
                prizes.record_loyal(sender)
                msg += '\n🔥 LOYAL MEMBER status unlocked!'
            msg += '\n🔥 Loyalty perks: ' + str(streak) + '-day streak. Keep it alive!'
        send_reply(message, msg)
        return

    if cmd == 'claimacc':
        parts = args.split()
        if len(parts) != 2:
            send_reply(message, 'Send it like: ' + prefix + 'claimacc [username] [password]  (best in PM)')
            return
        u = prizes._user(sender)
        if not u.get('pending_account'):
            send_reply(message, 'You have no account prize waiting. Claim ' + prefix + 'daily first!')
            return
        username, password = parts
        if not prizes.USERNAME_RE.match(username):
            send_reply(message, 'Username: 3-20 letters/numbers/_/. only. Try again.')
            return
        if len(password) < 4:
            send_reply(message, 'Password must be at least 4 characters. Try again.')
            return
        try:
            grant_account_prize(sender, username, password)
        except Exception as e:
            send_reply(message, '❌ Account creation failed: ' + str(e))
            return
        prizes.record_account(sender, username)
        send_reply(message, '✅ Account "' + username + '" created! Log in with it next time you connect.')
        return

    if cmd == 'modacc':
        parts = args.split()
        if len(parts) != 2:
            send_reply(message, 'Send it like: ' + prefix + 'modacc [username] [password]  (PM only!)')
            return
        u = prizes._user(sender)
        if not u.get('modpowers_pending'):
            reach = prizes.ladder.get(3)
            send_reply(message, 'No moderator prize waiting. Reach day 3 of the ' + prefix + 'daily ladder first!')
            return
        username, password = parts
        if not prizes.USERNAME_RE.match(username):
            send_reply(message, 'Username: 3-20 letters/numbers/_/. only. Try again.')
            return
        if len(password) < 4:
            send_reply(message, 'Password must be at least 4 characters. Try again.')
            return
        try:
            grant_modpowers_account(username, password)
        except Exception as e:
            send_reply(message, '❌ Account creation failed: ' + str(e))
            return
        prizes.record_modpowers(sender, username)
        send_reply(message, '✅ Moderator-lite account "' + username + '" is ready! Rights: move users, kick from channels, be channel op. NEVER admin.')
        return

    if cmd == 'opme':
        u = prizes._user(sender)
        chans = u.get('channels') or []
        if not chans:
            won = prizes.ladder.get(2)
            send_reply(message, 'You need to win a channel first (day 2 of the ladder: ' + str(won) + ')')
            return
        try:
            tt = bot.teamtalks[0]
            target = find_user_by_name(tt, sender)
            if target is None:
                send_reply(message, 'Join the server first, then send ' + prefix + 'opme.')
                return
            uid = int(getattr(target, 'nUserID', 0) or 0)
            my_chan = int(getattr(target, 'nChannelID', 0) or 0)
            ok = False
            for c in chans:
                if c.get('channel_id') == my_chan:
                    ok = True
                    break
            if not ok:
                send_reply(message, 'Join your own channel first, then send ' + prefix + 'opme.')
                return
            tt.make_channel_operator(tt.get_user(uid), my_chan)
            send_reply(message, '⭐ You are now operator of your channel!')
        except Exception as e:
            send_reply(message, 'Failed to make you operator: ' + str(e))
        return

    if cmd == 'prizes':
        send_reply(message, prizes.ladder_text(sender))
        return

    if cmd == 'mystuff':
        send_reply(message, prizes.mystuff_text(sender))
        return

    if cmd == 'streaks':
        rows = prizes.top_streaks(5)
        if not rows:
            send_reply(message, 'No claims yet - be the first! Type ' + prefix + 'daily!')
            return
        medals = ['🥇', '🥈', '🥉', '4.', '5.']
        lines = ['🔥 BEST STREAKS']
        for i, (name, best, total) in enumerate(rows):
            lines.append(medals[i] + ' ' + name + ' - ' + str(best) + ' day streak | ' + str(total) + ' claims')
        send_reply(message, '\n'.join(lines))
        return

    if cmd == 'giveprize':
        if not is_admin_user(user_id, sender):
            send_reply(message, '⛔ Admin only.')
            return
        parts = args.split(None, 1)
        if len(parts) < 1 or not parts[0]:
            send_reply(message, 'Usage: ' + prefix + 'giveprize [nickname] [account|channel|modpowers|loyal]')
            return
        who = parts[0]
        what = parts[1].strip().lower() if len(parts) > 1 else ''
        if what == 'account':
            prizes.pending_account(who, True)
            send_reply(message, '🎫 ' + who + ' can now create an account with ' + prefix + 'claimacc (they must be online to receive this).')
        elif what == 'channel':
            try:
                name, cid = grant_channel_prize(who)
                send_reply(message, '📺 Channel "' + name + '" created for ' + who + '.')
            except Exception as e:
                send_reply(message, 'Failed: ' + str(e))
        elif what == 'modpowers':
            prizes.record_modpowers_pending(who)
            send_reply(message, '🛡️ ' + who + ' can now create a moderator-lite account with ' + prefix + 'modacc.')
        elif what == 'loyal':
            prizes.record_loyal(who)
            send_reply(message, '🔥 ' + who + ' is now a loyal member!')
        else:
            send_reply(message, 'Unknown prize. Options: account, channel, modpowers, loyal')
        return

    if cmd == 'resetdaily':
        if not is_admin_user(user_id, sender):
            send_reply(message, '⛔ Admin only.')
            return
        who = args.strip()
        if not who:
            send_reply(message, 'Usage: ' + prefix + 'resetdaily [nickname]')
            return
        u = prizes._user(who)
        u['last_claim'] = None
        prizes.save()
        send_reply(message, '🔄 ' + who + ' can claim ' + prefix + 'daily again.')
        return


def warn_user(nick, reason, by, message=None):
    """Record a warning, notify the channel, auto-mute at the limit. Returns True if warned."""
    count, max_w = moderation.add_warning(nick, reason, by)
    store.count_warning()
    notice = ('⚠️ Warning ' + str(count) + '/' + str(max_w) + ' for ' + str(nick)
              + ': ' + str(reason) + ' (by ' + str(by) + ')')
    if count >= max_w and moderation.auto_mute:
        try:
            tt = bot.teamtalks[0]
            apply_mute(tt, nick, 'Auto-mute: ' + str(max_w) + ' warnings', by)
            notice += '\n🔇 ' + str(nick) + ' is now muted (bot ignores their voice and messages).'
            notice += '\nAn admin can unmute with: !unmute ' + str(nick)
        except Exception:
            pass
    else:
        left = max_w - count
        notice += '\n(' + str(left) + ' more warning' + ('s' if left != 1 else '') + ' before auto-mute)'
    if message is not None:
        send_reply(message, notice)
    else:
        try:
            send_channel_message(bot.teamtalks[0], notice)
        except Exception:
            pass
    return True


# Track who we've welcomed
welcomed_users = set()

# Active poll (only one at a time)
active_polls = {}


def load_config():
    for fname in ['config.txt', 'config.json']:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    print('Config file not found! Create config.txt')
    sys.exit(1)


config = load_config()
ai_config = dict(config['ai'])
# A deployment can keep the provider key out of the tracked configuration file.
# The configured environment variable takes precedence when it is set.
api_key_env = ai_config.get('api_key_env')
if api_key_env and os.environ.get(api_key_env):
    ai_config['api_key'] = os.environ[api_key_env]
mod_config = config.get('moderation', {})
moderation = Moderation(mod_config.get('anti_spam', {}))
prizes = Prizes(config.get('prizes', {}))
# Bot admins: nicknames/usernames listed in config ("admins": ["name", ...]).
# TeamTalk server admins are also trusted automatically.
admins = [str(a).lower() for a in config.get('admins', [])]

ai = AIEngine(
    provider=ai_config['provider'],
    api_key=ai_config['api_key'],
    model=ai_config['model'],
    system_prompt=ai_config['system_prompt'],
    max_tokens=ai_config.get('max_tokens', 200),
    temperature=ai_config.get('temperature', 0.7)
)

bot = teamtalk.TeamTalkBot()
stats = {'messages_received': 0, 'ai_responses': 0, 'commands_used': 0, 'welcome_msgs': 0, 'start_time': datetime.now()}
last_message_time = {}
MIN_INTERVAL = 1.0


def is_rate_limited(user_id):
    now = time.time()
    if user_id in last_message_time:
        if now - last_message_time[user_id] < MIN_INTERVAL:
            return True
    last_message_time[user_id] = now
    return False


def get_sender_name(message):
    """Resolve the sender's nickname, falling back to username, then User_<id>.

    NOTE: message.user is a TeamTalkUser wrapper. Friendly attribute names
    ('nickname', 'username') resolve through the wrapper; raw SDK names like
    'szNickname' do NOT (the wrapper's lookup re-cases them), so always use
    the friendly names here.
    """
    try:
        user = message.user
        nick = getattr(user, 'nickname', None)
        if nick:
            return str(nick)
        uname = getattr(user, 'username', None)
        if uname:
            return str(uname)
    except Exception:
        pass
    # Fallback: raw user struct straight from the SDK (works even if the
    # wrapper failed to build, e.g. the sender left the server meanwhile).
    try:
        raw = bot.teamtalks[0].super.getUser(int(message.from_id))
        nick = str(getattr(raw, 'szNickname', '') or '')
        if nick:
            return nick
        uname = str(getattr(raw, 'szUsername', '') or '')
        if uname:
            return uname
    except Exception:
        pass
    return 'User_' + str(message.from_id)


def is_pm(message):
    """Check if this is a direct/private message (PM)."""
    return isinstance(message, DirectMessage)


# ============================================================
#  ADMIN SYSTEM
# ============================================================

def is_admin_user(user_id, sender):
    """True if the sender is a bot admin (config list) or a TeamTalk server admin."""
    if sender and sender.lower() in admins:
        return True
    try:
        tt = bot.teamtalks[0]
        u = tt.super.getUser(user_id)
        return getattr(u, 'uUserType', None) == sdk.UserType.USERTYPE_ADMIN
    except Exception:
        return False


def find_user_by_name(tt, name):
    """Find a user on the server by nickname or username (exact, case-insensitive)."""
    try:
        users = tt.super.getServerUsers()
    except Exception:
        return None
    name_l = str(name).lower()
    for u in users:
        nick = str(getattr(u, 'szNickname', '') or '')
        uname = str(getattr(u, 'szUsername', '') or '')
        if nick.lower() == name_l or uname.lower() == name_l:
            return u
    return None


def user_display(u):
    try:
        return str(getattr(u, 'szNickname', '') or getattr(u, 'szUsername', '') or '?')
    except Exception:
        return '?'


def resolve_target(tt, args):
    """'name rest...' -> (raw user struct or None, rest of args)."""
    if not args:
        return None, ''
    parts = args.split(None, 1)
    rest = parts[1] if len(parts) > 1 else ''
    return find_user_by_name(tt, parts[0]), rest


def handle_admin_command(cmd, args, message, sender):
    try:
        tt = bot.teamtalks[0]
    except Exception:
        send_reply(message, 'Not connected to a server yet.')
        return

    if cmd == 'channels':
        try:
            raw = tt.super.getServerChannels()
            lines = ['📋 Channels:']
            for c in raw:
                cid = int(getattr(c, 'nChannelID', 0) or 0)
                cname = str(getattr(c, 'szName', '') or '?')
                try:
                    n_users = len(tt.get_channel(cid).get_users())
                except Exception:
                    n_users = '?'
                lines.append('#' + str(cid) + ' ' + cname + ' (' + str(n_users) + ' users)')
            send_reply(message, '\n'.join(lines) if len(lines) > 1 else 'No channels found.')
        except Exception as e:
            send_reply(message, 'Error listing channels: ' + str(e))
        return

    if cmd == 'announce':
        if not args:
            send_reply(message, 'Usage: !announce [text]')
            return
        try:
            tt.server.send_message('📢 ' + args)
        except Exception as e:
            send_reply(message, 'Announce failed (bot needs admin): ' + str(e))
        return

    if cmd == 'shutdown':
        send_reply(message, '👋 Shutting down by request of ' + sender + '. Bye!')
        store.save()
        threading.Timer(1.0, lambda: os._exit(0)).start()
        return

    target, rest = resolve_target(tt, args)
    if target is None:
        send_reply(message, 'User not found. Usage: !' + cmd + ' [nickname]')
        return

    uid = int(getattr(target, 'nUserID', 0) or 0)

    # Safety: never act against the bot itself or a TeamTalk server admin
    try:
        if uid == tt.super.getMyUserID() or getattr(target, 'uUserType', None) == sdk.UserType.USERTYPE_ADMIN:
            send_reply(message, 'Refusing: ' + user_display(target) + ' is the bot or a server admin.')
            return
    except Exception:
        pass

    if cmd in ('kick', 'kickc', 'ban'):
        chan = 0 if cmd in ('kick', 'ban') else int(getattr(target, 'nChannelID', 0) or 0)
        action = {'kick': 'kicked from the server',
                  'kickc': 'kicked from their channel',
                  'ban': 'banned from the server'}[cmd]
        try:
            if cmd == 'ban':
                tt.ban_user(uid, chan)
            else:
                tt.kick_user(uid, chan)
            send_reply(message, '🔨 ' + user_display(target) + ' ' + action + ' (by ' + sender + ').')
        except Exception as e:
            send_reply(message, 'Failed (bot needs permission): ' + str(e))
        return

    if cmd == 'mute':
        try:
            apply_mute(tt, user_display(target), 'Muted by ' + sender, sender)
            send_reply(message, '🔇 ' + user_display(target) + ' muted: the bot will ignore their voice and messages.')
        except Exception as e:
            send_reply(message, 'Failed: ' + str(e))
        return

    if cmd == 'unmute':
        try:
            apply_unmute(tt, user_display(target), sender)
            send_reply(message, '🔊 ' + user_display(target) + ' unmuted.')
        except Exception as e:
            send_reply(message, 'Failed: ' + str(e))
        return

    if cmd == 'warn':
        if not rest:
            send_reply(message, 'Usage: !warn [nickname] [reason]')
            return
        warn_user(user_display(target), rest.strip(), sender, message=message)
        return

    if cmd == 'clearwarnings':
        n = moderation.clear_warnings(user_display(target))
        send_reply(message, '🧹 Cleared ' + str(n) + ' warning(s) for ' + user_display(target) + '. (Use !unmute if they are also muted.)')
        return

    if cmd == 'move':
        if not rest:
            send_reply(message, 'Usage: !move [nickname] [channel name or id] (see !channels)')
            return
        arg = rest.strip()
        chan_id = None
        if arg.isdigit():
            chan_id = int(arg)
        else:
            try:
                for c in tt.super.getServerChannels():
                    if str(getattr(c, 'szName', '') or '').lower() == arg.lower():
                        chan_id = int(getattr(c, 'nChannelID', 0) or 0)
                        break
            except Exception:
                pass
        if chan_id is None:
            send_reply(message, 'Channel not found. Use !channels to list them.')
            return
        try:
            tt.move_user(tt.get_user(uid), chan_id)
            send_reply(message, '➡️ Moved ' + user_display(target) + ' to channel #' + str(chan_id) + '.')
        except Exception as e:
            send_reply(message, 'Failed (bot needs permission): ' + str(e))
        return


# ============================================================
#  SENDING HELPERS
#  IMPORTANT: teamtalk.py's message.reply() is SYNC. No await!
# ============================================================

def send_reply(message, content):
    """Send a reply to a message. Sync - reply() is not async in teamtalk.py."""
    try:
        if content is None:
            content = 'Sorry, I got an empty response. Please try again.'
        if len(content) > 180:
            for i in range(0, len(content), 180):
                message.reply(content[i:i + 180])
                time.sleep(0.4)
        else:
            message.reply(content)
        return True
    except Exception as e:
        print('  -> Reply error: ' + str(e))
        return False


def send_channel_message(tt, content):
    """Send a text message to the bot's current channel. Sync."""
    try:
        msg = sdk.TextMessage()
        msg.nMsgType = sdk.TextMsgType.MSGTYPE_CHANNEL
        msg.nFromUserID = tt.super.getMyUserID()
        msg.nChannelID = tt.super.getMyChannelID()
        msg.szMessage = sdk.ttstr(content)
        msg.bMore = False
        tt._send_message(msg)
        return True
    except Exception as e:
        print('  -> Channel send error: ' + str(e))
        return False


def set_bot_status(status_mode, text):
    """Update the bot's status line - acts as the typing indicator."""
    try:
        for tt in getattr(bot, 'teamtalks', []) or []:
            tt.change_status(status_mode, text)
    except Exception:
        pass


def show_typing():
    """Show the typing indicator (question mode + 'typing...' under bot name)."""
    set_bot_status(UserStatusMode.QUESTION, '\u270d\ufe0f typing...')


def hide_typing():
    """Remove the typing indicator, back to normal."""
    set_bot_status(UserStatusMode.ONLINE, 'Online - ready for questions')


# ============================================================
#  EVENTS
# ============================================================

@bot.event
async def on_ready():
    s = config['server']
    print('=' * 50)
    print('TeamTalk AI Bot is ONLINE!')
    print('=' * 50)
    print('  Server:    ' + str(s['host']) + ':' + str(s['tcp_port']))
    print('  Nickname:  ' + str(s.get('nickname', 'AI Bot')))
    print('  AI Engine: ' + ai_config['provider'].title())
    print('  Model:     ' + ai_config['model'])
    print('  Prefix:    ' + config['commands']['prefix'])
    print('  Admins:    ' + (', '.join(config.get('admins', [])) or '(TeamTalk server admins)'))
    print('  Anti-spam: ' + ('ON (warn after ' + str(moderation.repeat_count) + ' repeats / ' + str(moderation.flood_count) + '+ msgs, mute at ' + str(moderation.max_warnings) + ' warnings)' if moderation.enabled else 'OFF'))
    print('=' * 50)

    # Make sure the bot shows the configured nickname (not the login username)
    try:
        nick = s.get('nickname') or '🤖 AI Bot'
        for tt in bot.teamtalks:
            tt.change_nickname(nick)
    except Exception:
        pass

    # Re-apply persisted mutes after reconnect (subscriptions are lost on restart)
    try:
        tt = bot.teamtalks[0]
        for nick, reason in moderation.muted_list():
            apply_mute(tt, nick, reason or 'muted', 'startup-restore')
        if moderation.muted_list():
            print('  Re-applied mutes: ' + ', '.join(n for n, _ in moderation.muted_list()))
    except Exception:
        pass
    print('=' * 50)
    print('  Waiting for messages... Press Ctrl+C to stop')
    print('=' * 50)


@bot.event
async def on_user_join(user, channel):
    """Welcome message when someone joins."""
    try:
        # user is a TeamTalkUser wrapper: use friendly names ('nickname', 'id')
        name = getattr(user, 'nickname', None) or getattr(user, 'username', None) or 'Someone'
        user_id = getattr(user, 'id', None)
        print('[JOIN] ' + str(name) + ' joined')

        # Skip welcoming ourselves
        if user_id and hasattr(bot, 'teamtalks') and bot.teamtalks:
            my_id = bot.teamtalks[0].super.getMyUserID()
            if user_id == my_id:
                return

        # Don't spam welcome to the same user
        welcome_key = str(user_id) + '_join'
        if welcome_key not in welcomed_users:
            welcomed_users.add(welcome_key)
            stats['welcome_msgs'] += 1
            store.count_welcome()
            welcome = 'Welcome ' + str(name) + '! I am AI Bot. Send me a PM or type !help to see what I can do.'
            # Send to channel (sync, no await)
            try:
                tt = bot.teamtalks[0]
                send_channel_message(tt, welcome)
            except Exception:
                pass
    except Exception:
        pass


@bot.event
async def on_message(message):
    stats['messages_received'] += 1
    text = message.content.strip()
    sender = get_sender_name(message)
    user_id = message.from_id
    now_str = datetime.now().strftime('%H:%M:%S')
    msg_type = 'PM' if is_pm(message) else 'CH'
    print('[' + now_str + '] [' + msg_type + '] ' + sender + ': ' + text)

    if not text:
        return

    # Skip messages from the bot itself
    if message.is_me():
        return

    # Moderation: drop messages from muted (ignored) users entirely
    if sender.lower() in muted_users:
        return

    # Anti-spam runs before command handling or an AI request.  PMs must be
    # included: they are the normal route to the provider API.
    if moderation.enabled:
        spam = moderation.check_spam(user_id, text)
        if spam == 'COOLDOWN':
            return
        if spam:
            # Channel spam -> public notice; PM spam -> warn in PM
            warn_user(sender, 'Auto: ' + spam, 'anti-spam',
                      message=message if is_pm(message) else None)
            return

    # Track message in persistent stats (survives restarts)
    store.count_message(user_id, sender)

    prefix = config['commands']['prefix']

    # Handle commands
    if text.startswith(prefix):
        parts = text[len(prefix):].split()
        cmd = parts[0].lower() if parts else ''
        args = ' '.join(parts[1:])
        stats['commands_used'] += 1
        store.count_command(user_id, sender)

        # ---------- stats & leaderboard ----------
        if cmd == 'stats':
            session = dict(stats)
            session['uptime_min'] = int((datetime.now() - stats['start_time']).total_seconds() / 60)
            send_reply(message, store.summary_line(session))
            return
        if cmd == 'statsall':
            rows = store.top_users(20)
            if not rows:
                send_reply(message, 'No stats yet - say something first!')
                return
            lines = ['📊 ALL-TIME LEADERBOARD (top 20)']
            for i, (name, msgs, ai_n, cmds) in enumerate(rows, 1):
                lines.append(str(i) + '. ' + name + ' - ' + str(msgs) + ' msgs | AI ' + str(ai_n) + ' | cmds ' + str(cmds))
            send_reply(message, '\n'.join(lines))
            return
        if cmd == 'top':
            rows = store.top_users(5)
            if not rows:
                send_reply(message, 'No stats yet - say something first!')
                return
            medals = ['🥇', '🥈', '🥉', '4.', '5.']
            lines = ['🏆 TOP CHATTERS']
            for i, (name, msgs, ai_n, cmds) in enumerate(rows):
                lines.append(medals[i] + ' ' + name + ' - ' + str(msgs) + ' msgs | ' + str(ai_n) + ' AI answers')
            send_reply(message, '\n'.join(lines))
            return

        # ---------- prize system ----------
        if cmd in ('daily', 'claimacc', 'modacc', 'opme', 'prizes', 'mystuff', 'streaks', 'giveprize', 'resetdaily'):
            handle_prize_command(cmd, args, message, sender, user_id)
            return

        # ---------- warnings (users can check their own) ----------
        if cmd == 'warnings':
            if args:
                if not is_admin_user(user_id, sender):
                    send_reply(message, '⛔ Only admins can view other users warnings.')
                    return
                who = args.split(None, 1)[0]
            else:
                who = sender
            rows = moderation.get_warnings(who)
            if not rows:
                send_reply(message, '✅ ' + who + ' has no warnings. Keep it up!')
                return
            lines = ['⚠️ Warnings for ' + who + ': ' + str(len(rows)) + '/' + str(moderation.max_warnings)]
            for i, w in enumerate(rows, 1):
                lines.append(str(i) + '. ' + w['reason'] + ' (by ' + w['by'] + ', ' + w['time'] + ')')
            if moderation.is_muted(who):
                lines.append('🔇 Currently muted.')
            send_reply(message, '\n'.join(lines))
            return

        # ---------- admin commands ----------
        if cmd in ('kick', 'kickc', 'ban', 'mute', 'unmute', 'move', 'channels', 'announce', 'shutdown', 'warn', 'clearwarnings'):
            if not is_admin_user(user_id, sender):
                send_reply(message, '⛔ Admin only! Ask the bot owner to add your nickname to "admins" in config.txt.')
                return
            handle_admin_command(cmd, args, message, sender)
            return

        if cmd == 'help':
            send_reply(message, 'Commands: !help !daily !prizes !mystuff !streaks !opme !stats !statsall !top !about !time !ping !ask [q] !joke !translate [text] !poll [q] | [opt1] | [opt2] ... !vote [n] !yt [search] !ytinfo [link] !warnings')
            send_reply(message, 'Prizes: claim with !daily every day - day 1 account, day 2 own channel, day 3 moderator-lite powers (never admin), day 7+ loyal perks')
            send_reply(message, 'Admin: !kick !kickc !ban !mute !unmute !warn [name] [reason] !warnings [name] !clearwarnings [name] !move [name] [channel] !channels !announce [text] !giveprize [name] [prize] !resetdaily [name] !shutdown')
            return
        if cmd == 'about':
            msg = 'AI Bot v1.1 | Provider: ' + ai_config['provider'].title() + ' | Model: ' + ai_config['model']
            send_reply(message, msg)
            return
        if cmd == 'clear':
            ai.clear_history(user_id)
            active_polls.clear()
            send_reply(message, 'Chat history and active poll cleared!')
            return
        if cmd == 'time':
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            send_reply(message, 'Current time: ' + now)
            return
        if cmd in ('yt', 'youtube'):
            if not args:
                send_reply(message, 'Usage: !yt [search terms] - e.g. !yt funny cat')
                return
            send_reply(message, '🔎 Searching YouTube for: ' + args + '...')
            results = search_youtube(args, 5)
            if not results:
                send_reply(message, 'No results found for: ' + args)
                return
            lines = ['📺 TOP RESULTS for: ' + args]
            for i, v in enumerate(results, 1):
                meta = []
                if v.get('duration'):
                    meta.append(v['duration'])
                if v.get('views'):
                    meta.append(v['views'])
                suffix = ' [' + ' | '.join(meta) + ']' if meta else ''
                lines.append(str(i) + '. ' + v['title'][:80] + suffix)
                lines.append('   ' + v['url'])
            send_reply(message, '\n'.join(lines))
            return
        if cmd == 'ytinfo':
            if not args:
                send_reply(message, 'Usage: !ytinfo [youtube link]')
                return
            info = get_video_info(args)
            if not info:
                send_reply(message, 'Could not get info for that link. Make sure it is a valid YouTube link.')
                return
            parts = ['📺 ' + info['title']]
            if info.get('channel'):
                parts.append('👤 Channel: ' + info['channel'])
            if info.get('views'):
                parts.append('👁 Views: ' + info['views'])
            if info.get('duration'):
                parts.append('⏱ Duration: ' + info['duration'])
            parts.append(info['url'])
            send_reply(message, '\n'.join(parts))
            return
        if cmd == 'ping':
            uptime = datetime.now() - stats['start_time']
            mins = int(uptime.total_seconds() / 60)
            total = store.data['general'].get('messages_total', 0)
            send_reply(message, 'Pong! Uptime: ' + str(mins) + 'min | Msgs: ' + str(stats['messages_received']) + ' | All-time: ' + str(total))
            return
        if cmd == 'ask':
            if not args:
                send_reply(message, 'Usage: !ask [question]')
                return
            text = args
        elif cmd == 'joke':
            text = 'Tell me a funny short joke'
        elif cmd == 'poll':
            # !poll Question | Option1 | Option2 | Option3
            if '|' not in args:
                send_reply(message, 'Usage: !poll Question | Option1 | Option2 | ...')
                return
            parts_poll = [p.strip() for p in args.split('|') if p.strip()]
            if len(parts_poll) < 3:
                send_reply(message, 'Need at least: !poll Question | Option1 | Option2')
                return
            question = parts_poll[0]
            options = parts_poll[1:]
            active_polls['question'] = question
            active_polls['options'] = {i+1: {'text': opt, 'voters': set()} for i, opt in enumerate(options)}
            active_polls['author'] = sender
            opts_msg = ''
            for i, opt in enumerate(options, 1):
                opts_msg += '\n' + str(i) + '. ' + opt
            send_reply(message, '📊 POLL: ' + question + opts_msg + '\nType !vote [number] to vote!')
            return
        elif cmd == 'vote':
            if not active_polls.get('question'):
                send_reply(message, 'No active poll! Start one with !poll [question] | [opt1] | [opt2]')
                return
            if not args:
                send_reply(message, 'Usage: !vote [number]')
                return
            try:
                vote_num = int(args.strip())
            except ValueError:
                send_reply(message, 'Usage: !vote [number]')
                return
            if vote_num not in active_polls['options']:
                send_reply(message, 'Invalid option! Pick 1-' + str(len(active_polls['options'])))
                return
            # Remove previous vote if any
            for opt_data in active_polls['options'].values():
                opt_data['voters'].discard(sender)
            # Add new vote
            active_polls['options'][vote_num]['voters'].add(sender)
            # Build results
            results = '📊 POLL: ' + active_polls['question'] + '\n'
            for num, data in active_polls['options'].items():
                v_count = len(data['voters'])
                bar = '\u2588' * v_count if v_count > 0 else ''
                results += str(num) + '. ' + data['text'] + ' [' + str(v_count) + '] ' + bar + '\n'
            results += 'Total votes: ' + str(sum(len(d['voters']) for d in active_polls['options'].values()))
            send_reply(message, results)
            return
        elif cmd == 'translate':
            if not args:
                send_reply(message, 'Usage: !translate [text]')
                return
            text = 'Translate to English: ' + args
        elif cmd:
            text = text[len(prefix):]

        # For commands, skip the filter below and go straight to AI
        if is_rate_limited(user_id):
            return
        stats['ai_responses'] += 1
        print('  -> AI [' + cmd + ']: ' + text[:50])
        show_typing()
        try:
            response = await ai.get_response(user_id, sender, text)
            if send_reply(message, response):
                store.count_ai_response(user_id)
        except Exception as e:
            print('  -> Error: ' + str(e))
            store.count_error()
            send_reply(message, 'Error processing message.')
        finally:
            hide_typing()
        return

    # --- RESPONSE RULES ---
    # For PMs: ALWAYS respond (the user is talking directly to the bot)
    # For channel messages: only respond if bot is mentioned or has "?"
    if is_pm(message):
        should_respond = True
        # Welcome new PM users on their first message
        pm_key = str(user_id) + '_pm'
        if pm_key not in welcomed_users:
            welcomed_users.add(pm_key)
            stats['welcome_msgs'] += 1
            send_reply(message, 'Welcome ' + str(sender) + '! I am your AI assistant. Ask me anything!')
    else:
        should_respond = 'bot' in text.lower() or '?' in text

    if should_respond and config['commands']['enabled']:
        # Rate limiting
        if is_rate_limited(user_id):
            return

        stats['ai_responses'] += 1
        print('  -> AI: ' + text[:50])
        show_typing()
        try:
            response = await ai.get_response(user_id, sender, text)
            if send_reply(message, response):
                store.count_ai_response(user_id)
        except Exception as e:
            print('  -> Error: ' + str(e))
            store.count_error()
            send_reply(message, 'Error processing message.')
        finally:
            hide_typing()


def main():
    if ai_config['api_key'] == 'YOUR_API_KEY_HERE':
        print('=' * 50)
        print('API Key not configured! Edit config.txt')
        print('Free options: OpenRouter / Groq / Google Gemini')
        print('=' * 50)
        sys.exit(1)

    s = config['server']
    print('Starting TeamTalk AI Bot...')

    async def runner():
        async with bot:
            await bot.add_server({
                'host': s['host'],
                'tcp_port': s['tcp_port'],
                'udp_port': s['udp_port'],
                'username': s['username'],
                'password': s['password'],
                'nickname': s.get('nickname') or '🤖 AI Bot'
            })
            await bot._start()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        store.save()
        print('')
        print('Stopped. Msgs: ' + str(stats['messages_received']) + ' | AI: ' + str(stats['ai_responses']) + ' | Welcomes: ' + str(stats['welcome_msgs']))


if __name__ == '__main__':
    main()
