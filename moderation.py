#!/usr/bin/env python3
"""
moderation.py - anti-spam detection and warning system for the TeamTalk AI Bot.

Features:
  * Detects repeated identical messages and flooding (too many messages too fast)
  * Issues automatic warnings to spammers before they can exhaust the AI API
  * Manual warnings via !warn [nick] [reason]
  * Auto-mute (bot ignores the user) after reaching max_warnings
  * Warnings and mutes persist to warnings.json (keyed by nickname, so they
    survive bot restarts even though TeamTalk user IDs change every session)
"""

import json
import os
import time
import threading
from datetime import datetime

DEFAULTS = {
    'enabled': True,
    'repeat_count': 3,      # same message N times in a row -> warn
    'repeat_window': 60,    # ...within this many seconds
    'flood_count': 5,       # more than N messages...
    'flood_seconds': 10,    # ...within this many seconds -> warn
    'warn_cooldown': 5,     # seconds between two auto-warnings for the same user
    'max_warnings': 3,      # warnings before auto-mute
    'auto_mute': True,      # mute when max_warnings reached
}


class Moderation:
    def __init__(self, config=None, path=None):
        cfg = dict(DEFAULTS)
        if config:
            cfg.update(config)
        self.enabled = bool(cfg.get('enabled', True))
        self.repeat_count = int(cfg.get('repeat_count', 3))
        self.repeat_window = int(cfg.get('repeat_window', 60))
        self.flood_count = int(cfg.get('flood_count', 5))
        self.flood_seconds = int(cfg.get('flood_seconds', 10))
        self.warn_cooldown = int(cfg.get('warn_cooldown', 5))
        self.max_warnings = int(cfg.get('max_warnings', 3))
        self.auto_mute = bool(cfg.get('auto_mute', True))

        self.path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'warnings.json')
        self._lock = threading.Lock()
        self.data = self._load()

        # In-memory per-session spam trackers: user_id -> {...}
        self._trackers = {}

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
            print('  -> Warnings load error (starting fresh): ' + str(e))
            return {'users': {}}

    def save(self):
        try:
            with self._lock:
                tmp = self.path + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, self.path)
        except Exception as e:
            print('  -> Warnings save error: ' + str(e))

    # ---------------- user records ----------------

    @staticmethod
    def _key(nick):
        return str(nick).strip().lower()

    def _user(self, nick):
        key = self._key(nick)
        users = self.data['users']
        if key not in users:
            users[key] = {'name': str(nick), 'warnings': [], 'muted': False, 'muted_reason': '', 'total_ever': 0}
        # Keep the display name stable; only replace it with a differently-cased
        # spelling if we previously stored the plain key as a placeholder.
        if users[key].get('name', key) == key and str(nick) != key:
            users[key]['name'] = str(nick)
        return users[key]

    # ---------------- warnings ----------------

    def add_warning(self, nick, reason, by):
        """Add a warning. Returns (active_count, max_warnings)."""
        u = self._user(nick)
        u['warnings'].append({
            'reason': str(reason)[:200],
            'by': str(by),
            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        })
        u['total_ever'] = u.get('total_ever', 0) + 1
        self.save()
        return len(u['warnings']), self.max_warnings

    def get_warnings(self, nick):
        return self._user(nick).get('warnings', [])

    def clear_warnings(self, nick):
        """Remove all warnings. Returns how many were removed."""
        u = self._user(nick)
        n = len(u.get('warnings', []))
        u['warnings'] = []
        self.save()
        return n

    # ---------------- mutes ----------------

    def is_muted(self, nick):
        return bool(self._user(nick).get('muted', False))

    def set_muted(self, nick, muted, reason='', by=''):
        u = self._user(nick)
        u['muted'] = bool(muted)
        u['muted_reason'] = str(reason) if muted else ''
        u['muted_by'] = str(by)
        self.save()

    def muted_list(self):
        """[(nick, reason), ...] for all currently muted users."""
        return [(u.get('name', k), u.get('muted_reason', ''))
                for k, u in self.data['users'].items() if u.get('muted')]

    # ---------------- spam detection ----------------

    def check_spam(self, user_id, text):
        """
        Track a message and decide if it is spam.

        This check intentionally applies the same repeat and flood protection to
        private and channel messages.  Private messages are an AI request path,
        so exempting them from flood detection would allow a user to consume the
        provider API quota without ever triggering anti-spam.
        Returns:
          None        - message is fine
          'COOLDOWN'  - spam continues but we just warned: ignore silently
          str reason  - spam detected, issue a warning with this reason
        """
        now = time.time()
        t = self._trackers.setdefault(user_id, {
            'times': [], 'last_text': None, 'streak': 0, 'streak_start': 0, 'last_warn': 0,
        })

        # Flood check: messages inside the window
        t['times'] = [x for x in t['times'] if now - x < self.flood_seconds]
        t['times'].append(now)

        # Repeat check: identical text streak
        if text == t['last_text']:
            t['streak'] += 1
        else:
            t['last_text'] = text
            t['streak'] = 1
            t['streak_start'] = now

        reason = None
        if t['streak'] >= self.repeat_count and now - t['streak_start'] <= self.repeat_window:
            reason = 'repeated the same message ' + str(t['streak']) + ' times'
        elif len(t['times']) > self.flood_count:
            reason = 'sent too many messages too fast (' + str(self.flood_count) + '+ in ' + str(self.flood_seconds) + 's)'

        if reason:
            if now - t['last_warn'] < self.warn_cooldown:
                return 'COOLDOWN'
            t['last_warn'] = now
            return reason
        return None
