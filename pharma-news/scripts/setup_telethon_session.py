"""
이 스크립트를 로컬에서 한 번만 실행해서 Telethon 세션 문자열을 생성하세요.
생성된 세션 문자열을 GitHub Secrets에 TELETHON_SESSION으로 추가하면 됩니다.

실행 방법:
  pip install telethon
  python setup_telethon_session.py

my.telegram.org 에서 API_ID와 API_HASH를 먼저 발급받아야 합니다.
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

async def main():
    api_id = int(input("API ID: ").strip())
    api_hash = input("API Hash: ").strip()

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()

    session_string = client.session.save()
    print("\n" + "="*60)
    print("세션 문자열 (GitHub Secret에 TELETHON_SESSION으로 추가):")
    print("="*60)
    print(session_string)
    print("="*60)

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
