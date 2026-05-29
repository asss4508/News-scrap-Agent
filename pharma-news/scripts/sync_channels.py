import asyncio
import os
import base64
from pathlib import Path
from datetime import datetime, timezone, timedelta

from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELETHON_SESSION"]

KST = timezone(timedelta(hours=9))
MESSAGES_PER_CHANNEL = 500

def load_channel_list():
    config_path = Path(__file__).parent.parent.parent / "data" / "channels_to_sync.txt"
    if not config_path.exists():
        return []
    channels = []
    for line in config_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            try:
                channels.append(int(line))
            except ValueError:
                channels.append(line)
    return channels

async def sync():
    channels = load_channel_list()
    if not channels:
        print("동기화할 채널이 없습니다. data/channels_to_sync.txt를 확인해주세요.")
        return

    output_dir = Path(__file__).parent.parent.parent / "data" / "channels"
    output_dir.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await client.start()

    for channel in channels:
        try:
            entity = await client.get_entity(channel)
            name = getattr(entity, "username", None) or str(entity.id)
            print(f"채널 동기화: {name}")

            messages = []
            async for msg in client.iter_messages(entity, limit=MESSAGES_PER_CHANNEL):
                if not msg.text:
                    continue
                dt = msg.date.astimezone(KST).strftime("%Y-%m-%d %H:%M")
                messages.append(f"[{dt}] {msg.text}")

            content = "\n\n".join(reversed(messages))
            out_file = output_dir / f"{name}.txt"
            out_file.write_text(content, encoding="utf-8")
            print(f"  {len(messages)}개 메시지 저장 → {out_file.name}")

        except Exception as e:
            print(f"  오류 ({channel}): {e}")

    await client.disconnect()
    print("채널 동기화 완료")

if __name__ == "__main__":
    asyncio.run(sync())
