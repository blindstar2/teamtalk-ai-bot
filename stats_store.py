#!/usr/bin/env python3
"""
stats_store.py - persistent statistics for the TeamTalk AI Bot.
Saves everything to stats.json next to the bot, so stats survive restarts.
Also tracks AI Q&A answers and errors.
"""

import json
import os
import threading
from datetime import datetime

STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stats.json')
SAVE_EVERY = 20  # save every N updates

DEFAULT_DATA = {
    'general': {
        'messages_total': 0,
        'ai_responses_total': 0,
        'commands_total': 0,
        'welcome_msgs_total': 0,
        'errors_total': 0,
        'warnings_total': 0,
        'first_seen': None,
        'last_message': None,
    },
    'users': {},      # key -> {name, messages, ai_answers, commands, errors, first_seen, last_seen}
    'daily': {},      # 'YYYY-MM-DD' -> {messages: n, ai_responses: n, commands: n}
}


class StatsStore:
    def __init__(self, path=STATS_FILE):
        self.path = path
        self._lock = threading.Lock()
        self._unsaved = 0
        self.data = self._load()

    # ---------------- disk ----------------

    def _load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # merge in any missing keys (forward compatibility)
            for section, defaults in DEFAULT_DATA.items():
                if section not in data:
                    data[section] = json.loads(json.dumps(defaults))
                elif isinstance(defaults, dict):
                    for k, v in defaults.items():
                        data[section].setdefault(k, v)
            return data
        except FileNotFoundError:
            return json.loads(json.dumps(DEFAULT_DATA))
        except Exception as e:
            print('  -> Stats load error (starting fresh): ' + str(e))
            return json.loads(json.dumps(DEFAULT_DATA))

    def save(self):
        try:
            with self._lock:
                tmp = self.path + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, self.path)
                self._unsaved = 0
        except Exception as e:
            print('  -> Stats save error: ' + str(e))

    def _tick(self):
        """Call after each mutation; saves to disk every SAVE_EVERY updates."""
        self._unsaved += 1
        if self._unsaved >= SAVE_EVERY:
            self.save()

    # ---------------- users ----------------

    def user_key(self, user_id):
        return str(user_id)

    def _user(self, user_id, name):
        key = self.user_key(user_id)
        users = self.data['users']
        if key not in users:
            users[key] = {
                'name': name,
                'messages': 0,
                'ai_answers': 0,
                'commands': 0,
                'errors': 0,
                'first_seen': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'last_seen': None,
            }
        if name and name != 'Unknown':
            users[key]['name'] = name
        return users[key]

    def count_message(self, user_id, name):
        u = self._user(user_id, name)
        u['messages'] += 1
        u['last_seen'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        g = self.data['general']
        g['messages_total'] += 1
        g['last_message'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        if g['first_seen'] is None:
            g['first_seen'] = g['last_message']
        day = datetime.now().strftime('%Y-%m-%d')
        d = self.data['daily'].setdefault(day, {'messages': 0, 'ai_responses': 0, 'commands': 0})
        d['messages'] += 1
        self._tick()

    def count_ai_response(self, user_id):
        u = self._user(user_id, '')
        u['ai_answers'] += 1
        self.data['general']['ai_responses_total'] += 1
        day = datetime.now().strftime('%Y-%m-%d')
        self.data['daily'].setdefault(day, {'messages': 0, 'ai_responses': 0, 'commands': 0})
        self.data['daily'][day]['ai_responses'] += 1
        self._tick()

    def count_command(self, user_id, name):
        u = self._user(user_id, name)
        u['commands'] += 1
        self.data['general']['commands_total'] += 1
        day = datetime.now().strftime('%Y-%m-%d')
        self.data['daily'].setdefault(day, {'messages': 0, 'ai_responses': 0, 'commands': 0})
        self.data['daily'][day]['commands'] += 1
        self._tick()

    def count_error(self):
        self.data['general']['errors_total'] += 1
        self._tick()

    def count_warning(self):
        self.data['general']['warnings_total'] += 1
        self._tick()

    def count_welcome(self):
        self.data['general']['welcome_msgs_total'] += 1
        self._tick()

    # ---------------- views ----------------

    def top_users(self, limit=5):
        """Top users by message count: [(name, messages, ai_answers, commands), ...]"""
        ranked = sorted(
            self.data['users'].items(),
            key=lambda kv: kv[1].get('messages', 0),
            reverse=True,
        )
        out = []
        for _key, u in ranked[:limit]:
            out.append((u.get('name', '?'), u.get('messages', 0), u.get('ai_answers', 0), u.get('commands', 0)))
        return out

    def summary_line(self, session_stats):
        """One-line summary combining persistent totals and this session."""
        g = self.data['general']
        days = self.data['daily']
        today = datetime.now().strftime('%Y-%m-%d')
        today_d = days.get(today, {})
        return (
            '📊 All-time: ' + str(g.get('messages_total', 0)) + ' msgs | '
            + str(g.get('ai_responses_total', 0)) + ' AI answers | '
            + str(g.get('commands_total', 0)) + ' commands | '
            + str(g.get('errors_total', 0)) + ' errors | '
            + str(g.get('warnings_total', 0)) + ' warnings\n'
            '📅 Today: ' + str(today_d.get('messages', 0)) + ' msgs | '
            + str(today_d.get('ai_responses', 0)) + ' AI | '
            + str(today_d.get('commands', 0)) + ' cmds\n'
            '🔄 This session: ' + str(session_stats.get('messages_received', 0)) + ' msgs | '
            + str(session_stats.get('ai_responses', 0)) + ' AI | '
            + str(session_stats.get('welcome_msgs', 0)) + ' welcomes | '
            + 'up ' + str(session_stats.get('uptime_min', 0)) + 'min'
        )


# Shared store instance (stats.json next to the bot)
store = StatsStore()
