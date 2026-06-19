import discord
import csv
import os
from datetime import datetime, timezone

# ── CONFIG ────────────────────────────────────────────────
# Map your Discord channel names → language labels
CHANNEL_LANGUAGE_MAP = {
    "arabic":            "Arabic",
    "french":            "French",
    "german":            "German",
    "korean":            "Korean",
    "polish":            "Polish",
    "russian":           "Russian",
    "spanish":           "Spanish",
    "turkish":           "Turkish",
    "japanese":          "Japanese",
    "other-moderation":  "Other",
    "indian":            "Indian",
}

# ─────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

client = discord.Client(intents=intents)

# In-memory store: message_id → (posted_at, channel_language, subject)
report_posts = {}

REPORTS_FILE  = "reports.csv"
REACTIONS_FILE = "reactions.csv"


def ensure_csv_headers():
    if not os.path.exists(REPORTS_FILE):
        with open(REPORTS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["message_id", "channel", "language", "subject", "posted_at"])

    if not os.path.exists(REACTIONS_FILE):
        with open(REACTIONS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["message_id", "member", "emoji",
                             "reacted_at", "response_time_minutes", "language", "subject"])


def parse_subject(message: discord.Message) -> str:
    """Extract the report reason from the message text or embeds."""
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
        "protection of minors", "lawfulness",
    ]
    for s in subjects:
        if s in lower:
            return s.title()
    return "Unknown"


@client.event
async def on_ready():
    ensure_csv_headers()
    print(f"Logged in as {client.user} — Watching report channels.")


@client.event
async def on_message(message: discord.Message):
    channel_name = message.channel.name if hasattr(message.channel, "name") else ""
    language = CHANNEL_LANGUAGE_MAP.get(channel_name)
    if not language:
        return  # not a report channel we care about

    subject = parse_subject(message)
    posted_at = message.created_at.replace(tzinfo=timezone.utc)
    report_posts[message.id] = (posted_at, language, subject)

    with open(REPORTS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([message.id, channel_name, language, subject,
                         posted_at.isoformat()])


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
    reacted_at = datetime.now(timezone.utc)
    response_minutes = round((reacted_at - posted_at).total_seconds() / 60, 1)

    with open(REACTIONS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            payload.message_id,
            str(member),
            emoji_str,
            reacted_at.isoformat(),
            response_minutes,
            language,
            subject,
        ])

    print(f"Logged: {member} reacted {emoji_str} in {language} "
          f"— {response_minutes} min response time")


token = os.environ.get("DISCORD_TOKEN")
if not token:
    raise RuntimeError("DISCORD_TOKEN environment variable not set.")
client.run(token)
