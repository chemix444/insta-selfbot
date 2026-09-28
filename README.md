# insta-selfbot

Discord selfbot that rewrites Instagram and TikTok links in DMs and group chats to
`oginstagram.com` / `tnktok.com` so they embed properly.

- Links someone else sends get a reply with the rewritten link.
- Links you send yourself are edited in place.
- Everything goes through one queue with a 30 second delay between actions.

> Selfbots are against Discord's Terms of Service. Use at your own risk.

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then put your token in .env
./run.sh
```

Never commit your `.env`; it's in `.gitignore`.
