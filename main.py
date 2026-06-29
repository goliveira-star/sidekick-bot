import discord
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

# ── CONFIG ────────────────────────────────────────────────
CHANNEL_LANGUAGE_MAP = {
    "arabic":           "Arabic",
    "french":           "French",
    "german":           "German",
    "korean":           "Korean",
    "polish":           "Polish",
    "russian":          "Russian",
    "spanish":          "Spanish",
    "turkish":          "Turkish",
    "japanese":         "Japanese",
    "indian":           "Indian",
}
# ─────────────────────────────────────────────────────────

# Google Sheets setup
def init_sheets():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(spreadsheet_id)

    # Get or create the two sheets
    try:
        reports_ws = spreadsheet.worksheet("Reports")
    except gspread.WorksheetNotFound:
        reports_ws = spreadsheet.add_worksheet("Reports", rows=10000, cols=6)
        reports_ws.append_row(["message_id", "channel", "language", "subject", "posted_at"])

    try:
        reactions_ws = spreadsheet.worksheet("Reactions")
    except gspread.WorksheetNotFound:
        reactions_ws = spreadsheet.add_worksheet("Reactions", rows=10000, cols=7)
        reactions_ws.append_row(["message_id", "member", "emoji", "reacted_at",
                                  "response_time_minutes", "language", "subject"])
    return reports_ws, reactions_ws


reports_ws, reactions_ws = init_sheets()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

client = discord.Client(intents=intents)

# In-memory store: message_id → (posted_at, language, subject)
report_posts = {}


def parse_subject(message: discord.Message) -> str:
    content = message.content or ""
    for embed in message.embeds:
        if embed.description:
            content += " " + embed.description
        for field in embed.fields:
            content += " " + field.name + " " + field.value
    lower = content.lower()
    subjects = [
        "violence", "terrorism", "nudity", "pornography", "hate speech",
        "self-harm", "doxxing", "fraud", "game hacking", "harassment",
        "protection of minors", "lawfulness", "rights", "child endangerment", "bullying", "false sensationalism", "hate",
    ]
    for s in subjects:
        if s in lower:
            return s.replace('_', ' ').title()
    return "Unknown"


@client.event
async def on_ready():
    print(f"Logged in as {client.user} — Watching report channels.")


@client.event
async def on_message(message: discord.Message):
    channel_name = message.channel.name if hasattr(message.channel, "name") else ""
    language = CHANNEL_LANGUAGE_MAP.get(channel_name)
    if not language:
        return

    subject = parse_subject(message)
    posted_at = message.created_at.replace(tzinfo=timezone.utc)
    report_posts[message.id] = (posted_at, language, subject)

    reports_ws.append_row([
        str(message.id), channel_name, language, subject,
        posted_at.isoformat()
    ])
    print(f"Logged report: {subject} in {language}")


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.message_id not in report_posts:
        return

    guild = client.get_guild(payload.guild_id)
    if not guild:
        return

    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return

    posted_at, language, subject = report_posts[payload.message_id]
    emoji_str = str(payload.emoji)
    if emoji_str == '👀':
        return
    reacted_at = datetime.now(timezone.utc)
    response_minutes = round((reacted_at - posted_at).total_seconds() / 60, 1)

    reactions_ws.append_row([
        str(payload.message_id),
        str(member),
        emoji_str,
        reacted_at.isoformat(),
        response_minutes,
        language,
        subject,
    ])
    print(f"Logged: {member} reacted {emoji_str} in {language} — {response_minutes} min")


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args):
        pass

port = int(os.environ.get("PORT", 8080))
threading.Thread(target=lambda: HTTPServer(("0.0.0.0", port), _Health).serve_forever(), daemon=True).start()

token = os.environ.get("DISCORD_TOKEN")
if not token:
    raise RuntimeError("DISCORD_TOKEN environment variable not set.")
client.run(token)
