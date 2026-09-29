# TeamTalk 5 AI Chat Bot — v1.0 Beta

![Version](https://img.shields.io/badge/version-1.0--beta-orange)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Android-lightgrey)
![AI](https://img.shields.io/badge/AI-Gemini%20%7C%20OpenRouter%20%7C%20Groq-orange)

A conversational AI bot for **TeamTalk 5** voice chat servers. The bot joins your server as a regular user, converses with members through **private messages**, offers chat commands, anti-spam moderation, and server admin tools — powered by free AI providers such as Google **Gemini**, OpenRouter, and Groq.

> **Status: v1.0 Beta** — feature-complete and in daily use, but still being tested. Please report any issues you find!

## How Messaging Works

> [!IMPORTANT]
> **The bot is built around private messages (PMs), not channel messages.** Members are encouraged to send the bot a direct message to start a conversation. This keeps voice channels clean while still allowing full AI conversations with per-user memory.

| Context | Behavior |
|---|---|
| **Private message (PM)** | The bot **always replies**. Each user gets an independent conversation with its own history (last 10 messages of context). |
| **Channel message** | The bot stays silent by default. It only reacts when the message **mentions "bot"** or contains a **question mark (`?`)** — so ordinary channel chatter is never interrupted. |
| **Commands (`!` prefix)** | Work in both PMs and channels. |
| **User joins** | The bot posts a short welcome message in the channel, pointing new users to PM it or type `!help`. |

Additional behavior:

- **Typing indicator** — the bot displays "✍️ typing…" in its status while generating a reply.
- **Rate limiting** — max one AI request per user per second to prevent spam.
- **Bilingual replies** — responds in Arabic when written to in Arabic, English otherwise (customizable via the system prompt).
- **Automatic model fallback** — if the primary AI model is rate-limited or unavailable, the engine transparently retries with backup models.

## Features

- 💬 **AI conversation** — natural chat over PM with per-user conversation memory
- 🧠 **Multi-provider support** — Gemini (default), OpenRouter, Groq, and OpenAI-compatible endpoints
- 🔄 **Resilience** — automatic fallback across models on rate limits and server errors
- 📊 **Persistent statistics** — messages, AI answers, commands, warnings, and errors tracked per user in `stats.json`; survives restarts
- 🏆 **Leaderboards** — top chatters by activity
- 🚨 **Anti-spam & warnings** — detects repeated messages and flooding, warns automatically, auto-mutes repeat offenders; manual `!warn` with persistent warning records
- 🛡️ **Administration** — kick, ban, mute, and move users; broadcast announcements; remote shutdown
- 📺 **YouTube integration** — search and video info without an API key
- 📊 **Polls** — create polls in chat and vote on them

## Getting Started

### Prerequisites

- Python **3.10 or newer**
- A TeamTalk 5 server the bot can log into
- A free API key from one of:
  - [Google AI Studio](https://aistudio.google.com/apikey) — Gemini (recommended, free tier)
  - [OpenRouter](https://openrouter.ai/keys)
  - [Groq](https://console.groq.com/keys)

### Installation

1. Clone or download this repository.
2. Copy `config.example.json` to **`config.txt`** (or `config.json`):

   ```
   cp config.example.json config.txt
   ```

3. Edit `config.txt`:
   - `server.host` — your TeamTalk server address
   - `server.username` / `server.password` — the bot's login
   - `ai.api_key` — your API key
   - `admins` — nicknames allowed to use admin commands

4. Install dependencies and start:

   **Windows:** double-click `setup.bat`, then `run.bat`

   **Any OS:**
   ```bash
   python -m pip install -r requirements.txt
   python bot.py
   ```

   **Android (Pydroid 3):** run `python setup.py`, then `python run.py`

5. Connect with TeamTalk 5 and **send the bot a private message** — it answers everything!

## Commands

### General

| Command | Description |
|---|---|
| `!help` | List all commands |
| `!ask [question]` | Ask the AI directly |
| `!joke` | Random joke |
| `!translate [text]` | Translate text to English |
| `!time` | Current server time |
| `!ping` | Liveness check with uptime and message counts |
| `!stats` | Usage statistics (all-time, today, current session) |
| `!top` | Top 5 chatters |
| `!statsall` | Full top-20 leaderboard |
| `!poll [q] \| [opt1] \| [opt2]` | Start a poll |
| `!vote [number]` | Vote in the active poll |
| `!yt [search]` | Search YouTube |
| `!ytinfo [link]` | Details for a YouTube video |
| `!warnings` | Check your own warnings |
| `!clear` | Clear your AI history and the active poll |
| `!about` | Bot version, provider, and model |

Anything sent to the bot **by PM** is also treated as a question — no command needed.

### Administration

Restricted to nicknames in `admins` (and TeamTalk server admins):

| Command | Description |
|---|---|
| `!kick [nick]` | Kick a user from the server |
| `!kickc [nick]` | Kick a user from their current channel |
| `!ban [nick]` | Ban a user from the server |
| `!mute [nick]` | Bot ignores that user's voice and messages (persisted) |
| `!unmute [nick]` | Stop ignoring the user |
| `!warn [nick] [reason]` | Warn a user manually |
| `!warnings [nick]` | List a user's warnings |
| `!clearwarnings [nick]` | Clear all warnings for a user |
| `!move [nick] [channel]` | Move a user to another channel |
| `!channels` | List channels with IDs and user counts |
| `!announce [text]` | Broadcast a message to the whole server |
| `!shutdown` | Stop the bot remotely |

### Anti-Spam (automatic)

The bot watches channel chat and steps in by itself:

| Rule | Default | Action |
|---|---|---|
| Repeated identical messages | 3× within 60s | Automatic warning |
| Flooding | 6+ messages within 10s | Automatic warning |
| Warnings reached | 3 warnings | **Auto-mute** — the bot ignores the user |

Warnings and mutes persist in `warnings.json` and survive restarts. Admins are exempt. All thresholds are tunable in the `moderation.anti_spam` section of the config.

## Configuration Reference

| Key | Description |
|---|---|
| `server.host` | TeamTalk server hostname or IP |
| `server.tcp_port` / `server.udp_port` | Server ports (commonly `10333`) |
| `server.username` / `server.password` | Bot's login credentials |
| `server.nickname` | Display name shown in the server |
| `server.encrypted` | Use TLS encryption (`true`/`false`) |
| `ai.provider` | `gemini`, `openrouter`, `groq`, or `openai` |
| `ai.api_key` | API key for the chosen provider |
| `ai.model` | Model identifier (e.g. `gemini-flash-latest`) |
| `ai.system_prompt` | Personality & language rules for the bot |
| `ai.max_tokens` / `ai.temperature` | Response length and creativity |
| `commands.prefix` | Command prefix (default `!`) |
| `commands.enabled` | Master switch for command handling |
| `moderation.anti_spam` | Anti-spam tuning (thresholds, mute limit, on/off) |
| `admins` | Nicknames allowed to use admin commands |

## Project Structure

```
teamtalk-ai-bot/
├── bot.py            # Main bot: events, commands, admin & moderation logic
├── ai_engine.py      # AI providers, fallback chain, per-user memory
├── stats_store.py    # Persistent statistics (stats.json)
├── moderation.py     # Anti-spam, warnings, mutes (warnings.json)
├── yt_helper.py      # YouTube search & video info
├── config.example.json  # Template — copy to config.txt and fill in
├── run.bat / setup.bat       # Windows launcher / installer
├── run.py / setup.py         # Android (Pydroid 3) launcher / installer
└── requirements.txt  # Python dependencies
```

Runtime files created automatically: `stats.json`, `warnings.json`, `__pycache__/`.

## Troubleshooting

| Problem | Solution |
|---|---|
| `Module not found: teamtalk` | `python -m pip install teamtalk.py` |
| Cannot connect to server | Verify `host`/ports in `config.txt`; confirm the TeamTalk server is running |
| API key errors | Ensure `ai.api_key` is set to a valid key (not the placeholder) |
| Bot doesn't reply | **PM the bot directly** — channel messages require "bot" or `?` |
| All AI models failed | Free-tier rate limits; the bot retries with fallback models automatically |

## Security

Never commit or share your real `config.txt` — it contains your server credentials and API key. Only `config.example.json` belongs in version control. If you fork this project, keep your secrets out of your fork too.

## Contributing

Issues and pull requests are welcome! This is an early beta release, so feedback from other TeamTalk server owners is especially valuable.

## License

Released under the [MIT License](LICENSE).
