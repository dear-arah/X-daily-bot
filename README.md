# X Daily Bot

Drafts one X post per weekday and sends it to a private Discord channel. Each draft has two variants and a "Post to X" link under each. Tap the link, X opens with the text filled in, edit it if you like, and press Post. The bot never touches the X API, and it runs entirely on free tiers: GitHub Actions, a Discord webhook and a free-tier language model.

## What a draft is

The bot rotates through five post types, one per day:

1. **Saw this from Agora**: something Agora published or announced, with your own take.
2. **Build in public**: something you built or wrote, from your articles or your notes.
3. **Dev tip**: one concrete tip taken from the Agora knowledge pack.
4. **Community question**: a specific question for developers, tied to this week's tech news.
5. **Event reminder**: an event you added to the inbox.

If a type has nothing to work from that day (for example no event in the inbox), the bot moves on to the next type. The model never copies a source's wording; it adds a take, a reason to care, or a question. Each draft says why that angle should start replies and lists its sources, so you can check facts before posting.

## How links are checked

- Before drafting, the bot opens the link of the material it picked, three times in a row. If any try returns 404 or 410, it skips that item and uses the next one (or another post type). Some pages open only part of the time, which gives your readers a 404 too, so they are treated as dead.
- The model is given the page's real text (title, description and main paragraphs), not just a headline, so it has facts to work from.
- A draft may only contain the link the bot gave the model. Any other link, including one the model made up, is rejected and the run ends with a "No draft today" message.
- Sites that block automated requests (403, 429) are not treated as dead, so those links are kept but cannot be checked. Always click the link in the draft before you post.
- Headlines from the unchecked search feed are not used as general context for the model.

## Where the bot gets its material

- **The inbox** (`inbox/notes.md`): paste things you want posted about. Entries are separated by a line with only `---` and can start with a tag: `[linkedin]` (an Agora LinkedIn post, text and/or link), `[event]`, `[built]` or `[note]`. Each entry is used once. You can edit this file from the GitHub mobile app.
- **Feeds** (`config/sources.yaml`): Agora's GitHub and community posts, your own dev.to and Medium articles, and tech and AI news.
- **The Agora skills pack**: downloaded fresh on every run from https://github.com/AgoraIO/skills (MIT). The bot picks the files that match the day's topic.
- **Your voice** (`config/voice.md`) and **role** (`config/persona.md`): edit these to tune the tone.

LinkedIn cannot be read automatically (it blocks automated requests), which is why Agora LinkedIn posts go through the inbox.

## Setup

1. Create a private Discord channel, open its settings, then Integrations, then Webhooks, and create a webhook. Copy its URL.
2. In `config/sources.yaml`, replace `<DEVTO_USERNAME>` and `<MEDIUM_USERNAME>` with your usernames.
3. In this repository, open Settings, then Secrets and variables, then Actions, and add:
   - `DISCORD_WEBHOOK_URL`: the webhook URL.
   - `GEMINI_API_KEY`: a free key from Google AI Studio, created in a project without billing.
   - `GROQ_API_KEY`: a free key from the Groq console (fallback provider).
4. Open the Actions tab, choose `draft`, and run it once with "Run workflow". A draft should appear in Discord.

The workflow then runs on weekdays at 00:27 UTC (08:27 in UTC+8). To change it, edit the cron line in `.github/workflows/draft.yml`. The odd minute is on purpose: GitHub delays or drops scheduled runs at :00 and :30 when it is busy.

Running the workflow twice on one day does nothing the second time, unless you tick "force" when running it by hand.

## When something goes wrong

- If the model cannot write a usable draft, or the draft is too long even after one retry, Discord gets a short "No draft today" message with the reason. Nothing is used up.
- If Discord rejects the post, the run fails (GitHub emails you) and nothing is marked as used, so the next run tries again with the same material.
- If the Agora skills pack cannot be downloaded, the bot still drafts from `config/agora-context.md`.
- Free model names change often. If every run says no draft, check the `providers` list in `config/bot.yaml`.

## Run locally

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env   # then fill in your keys
sh scripts/sync-agora-skills.sh knowledge/agora-skills
.venv/bin/pytest
.venv/bin/python -m xpost run --dry-run --force
```

`--dry-run` prints the draft instead of sending it and saves nothing. It still calls the language model, so it needs a Gemini or Groq key, but not the webhook. `.env` is listed in `.gitignore`; never commit it.

## Notes

- Processed material is remembered in a `state` branch that the workflow maintains. Do not edit it by hand.
- GitHub pauses scheduled workflows in a repository with no commits for 60 days (and a paused repository cannot re-enable itself). Adding entries to `inbox/notes.md` is a commit, so normal use keeps the schedule alive. If drafts stop, open the Actions tab and re-enable the `draft` workflow.
- If Discord accepts a post but saving the state fails afterwards, the run shows as failed and the next run may draft from the same material again.
- Keep the repository public if you want unlimited Actions minutes. A weekday run uses well under a minute.
