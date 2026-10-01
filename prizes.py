#!/usr/bin/env python3
"""
prizes.py - daily prize & loyalty system for the TeamTalk AI Bot.

Ladder (configurable):
  Day 1: Registered user account (user picks username+password via PM)
  Day 2: Own permanent channel, named after the user
  Day 3: Moderator-lite powers on their account (move users + kick from
         channel + channel operator enable) - NEVER admin
  Day 7+: Loyal streak - bot auto-ops them in their channel

Activity bonus: users who chat a lot and claim regularly get channel-op
automatically (one time per channel).

Everything persists to prizes.json. Passwords are NEVER stored.
The system is hard-coded so it can never grant USERTYPE_ADMIN.
"""

import json
import os
import re
import threading
from datetime import datetime, timedelta

# Rights given to prize "moderator-lite" accounts. Deliberately excludes
# anything admin-only (ban users, server properties, etc.).
MOD_LITE_RIGHTS = [
    'USERRIGHT_OPERATOR_ENABLE',     # can hold channel operator status
    'USERRIGHT_MOVE_USERS',          # can move users between channels
    'USERRIGHT_KICK_USERS',          # can kick from channels (server kick stays admin-only)
    'USERRIGHT_VIEW_ALL_USERS',      # can see users in all channels
]

BASIC_RIGHTS = [
    'USERRIGHT_OPERATOR_ENABLE',
    'USERRIGHT_TEXTMESSAGE_USER',
    'USERRIGHT_TEXTMESSAGE_CHANNEL',
    'USERRIGHT_TRANSMIT_VOICE',
]

DEFAULTS = {
    'enabled': True,
    'ladder': {'1': 'account', '2': 'channel', '3': 'modpowers'},
    'loyal_day': 7,             # streak day that grants the loyal auto-op perk
    'activity_messages': 300,   # all-time messages for the activity bonus
    'activity_min_claims': 3,   # dailies claimed for the activity bonus
}

USERNAME_RE = re.compile(r'^[A-Za-z0-9_\.]{3,20}$')


class Prizes:
    def __init__(self, config=None, path=None):
        cfg = dict(DEFAULTS)
        if config:
            cfg.update(config)
        self.enabled = bool(cfg.get('enabled', True))
        self.ladder = {int(k): str(v) for k, v in cfg.get('ladder', DEFAULTS['ladder']).items()}
        self.loyal_day = int(cfg.get('loyal_day', 7))
        self.activity_messages = int(cfg.get('activity_messages', 300))
        self.activity_min_claims = int(cfg.get('activity_min_claims', 3))

        self.path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prizes.json')
        self._lock = threading.Lock()
        self.data = self._load()

    # ---------------- disk ----------------

    def _load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data.get('users'), dict):
                data['users'] = {}
            return data
        except FileNotFoundError:
            return {'users': {}}
        except Exception as e:
            print('  -> Prizes load error (starting fresh): ' + str(e))
            return {'users': {}}

    def save(self):
        try:
            with self._lock:
                tmp = self.path + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, self.path)
        except Exception as e:
            print('  -> Prizes save error: ' + str(e))

    # ---------------- user records ----------------

    @staticmethod
    def _key(nick):
        return str(nick).strip().lower()

    def _user(self, nick):
        key = self._key(nick)
        users = self.data['users']
        if key not in users:
            users[key] = {
                'name': str(nick),
                'streak': 0,
                'best_streak': 0,
                'last_claim': None,      # 'YYYY-MM-DD'
                'total_claims': 0,
                'accounts': [],          # [{username, date}] - passwords never stored
                'channels': [],          # [{name, channel_id, date}]
                'modpowers': False,      # moderator-lite rights granted
                'modpowers_pending': False,  # won day-3 prize, awaiting !modacc
                'loyal': False,          # loyal streak perk granted
                'activity_ops': [],      # channel ids where activity-op was given
                'pending_account': False,# waiting for !claimacc
            }
        if users[key].get('name') in (key, None) and str(nick) != key:
            users[key]['name'] = str(nick)
        return users[key]

    # ---------------- claim logic ----------------

    def today_str(self):
        return datetime.now().strftime('%Y-%m-%d')

    def claim_status(self, nick, today=None):
        """Returns (can_claim, streak_if_claimed, prize_type_or_None, message)."""
        today = today or self.today_str()
        u = self._user(nick)
        last = u.get('last_claim')

        if last == today:
            return False, u['streak'], None, 'already claimed today'

        if last is None:
            streak = 1
        else:
            try:
                yesterday = (datetime.strptime(today, '%Y-%m-%d')
                             - timedelta(days=1)).strftime('%Y-%m-%d')
                streak = u['streak'] + 1 if last == yesterday else 1
            except ValueError:
                streak = 1

        prize = self.ladder.get(streak)
        return True, streak, prize, ''

    def do_claim(self, nick, today=None):
        """Record a claim. Returns (streak, prize_type, first_time_flags)."""
        ok, streak, prize, msg = self.claim_status(nick, today)
        if not ok:
            return None, None, {}
        u = self._user(nick)
        u['streak'] = streak
        u['best_streak'] = max(u.get('best_streak', 0), streak)
        u['last_claim'] = today or self.today_str()
        u['total_claims'] += 1
        flags = {}
        if prize == 'modpowers' and not u.get('modpowers'):
            flags['modpowers_first'] = True
        if streak >= self.loyal_day and not u.get('loyal'):
            flags['loyal_first'] = True
        self.save()
        return streak, prize, flags

    def pending_account(self, nick, pending):
        u = self._user(nick)
        u['pending_account'] = bool(pending)
        self.save()

    def record_account(self, nick, username):
        u = self._user(nick)
        u['accounts'].append({'username': username, 'date': self.today_str()})
        u['pending_account'] = False
        self.save()

    def record_channel(self, nick, name, channel_id):
        u = self._user(nick)
        u['channels'].append({'name': name, 'channel_id': channel_id, 'date': self.today_str()})
        self.save()

    def record_modpowers_pending(self, nick):
        u = self._user(nick)
        u['modpowers_pending'] = True
        self.save()

    def record_modpowers(self, nick, username=None):
        u = self._user(nick)
        u['modpowers'] = True
        if username:
            u['modpowers_account'] = username
        self.save()

    def record_loyal(self, nick):
        u = self._user(nick)
        u['loyal'] = True
        self.save()

    def record_activity_op(self, nick, channel_id):
        u = self._user(nick)
        if channel_id not in u['activity_ops']:
            u['activity_ops'].append(channel_id)
            self.save()
            return True
        return False

    def should_activity_promote(self, nick, all_time_messages):
        """True if the user earned the activity channel-op bonus and not yet given here."""
        u = self._user(nick)
        if not self.enabled:
            return False
        if u.get('activity_ops'):
            return False
        return (all_time_messages >= self.activity_messages
                and u.get('total_claims', 0) >= self.activity_min_claims)

    # ---------------- views ----------------

    def ladder_text(self, nick):
        labels = {
            'account': '🎫 Registered user account (pick username + password)',
            'channel': '📺 Your own permanent channel',
            'modpowers': '🛡️ Moderator-lite powers (move users + channel kick, never admin)',
            'op': '⭐ Channel operator in your channel',
        }
        u = self._user(nick)
        lines = ['🎁 DAILY PRIZE LADDER:']
        days = sorted(set(list(self.ladder.keys()) + [self.loyal_day]))
        for day in days:
            if day in self.ladder:
                lines.append('  Day ' + str(day) + ': ' + labels.get(self.ladder[day], self.ladder[day]))
            if day == self.loyal_day:
                lines.append('  Day ' + str(day) + '+: 🔥 Loyal streak - auto channel-op + VIP title')
        lines.append('')
        lines.append('🔥 Your streak: ' + str(u['streak']) + ' day(s) | Best: ' + str(u['best_streak'])
                     + ' | Total claims: ' + str(u['total_claims']))
        if u.get('last_claim') == self.today_str():
            lines.append('✅ Claimed today - come back tomorrow!')
        else:
            nxt = (u['streak'] + 1) if u.get('last_claim') else 1
            nxt_prize = self.ladder.get(nxt)
            if u.get('last_claim'):
                gap_ok = self.claim_status(nick)[0]
                if not gap_ok:
                    nxt = u['streak']
                    nxt_prize = None
            if nxt_prize:
                lines.append('⏭ Next claim (day ' + str(nxt) + '): ' + labels.get(nxt_prize, nxt_prize))
            elif nxt >= self.loyal_day:
                lines.append('⏭ Next claim: loyal perks keep coming')
            else:
                lines.append('⏭ Next claim: keep the streak going!')
        return '\n'.join(lines)

    def mystuff_text(self, nick):
        u = self._user(nick)
        lines = ['🎒 ' + u['name'] + "'s prizes:"]
        if u['accounts']:
            for a in u['accounts']:
                lines.append('🎫 Account: ' + a['username'] + ' (created ' + a['date'] + ')')
        if u['channels']:
            for c in u['channels']:
                lines.append('📺 Channel: ' + c['name'] + ' (#' + str(c['channel_id']) + ')')
        if u.get('modpowers'):
            lines.append('🛡️ Moderator-lite powers: move users + channel kick')
        if u.get('loyal'):
            lines.append('🔥 Loyal member (day ' + str(self.loyal_day) + '+ streak)')
        if u.get('activity_ops'):
            lines.append('⭐ Activity channel-op in ' + str(len(u['activity_ops'])) + ' channel(s)')
        if len(lines) == 1:
            lines.append('(nothing yet - claim with !daily every day!)')
        return '\n'.join(lines)

    def top_streaks(self, limit=5):
        ranked = sorted(
            self.data['users'].items(),
            key=lambda kv: (kv[1].get('best_streak', 0), kv[1].get('total_claims', 0)),
            reverse=True,
        )
        return [(u.get('name', k), u.get('best_streak', 0), u.get('total_claims', 0))
                for k, u in ranked[:limit] if u.get('total_claims', 0) > 0]
