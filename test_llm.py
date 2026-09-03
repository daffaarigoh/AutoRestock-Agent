import asyncio
import os
import sys
import httpx
import smtplib

# Fix console encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from core.llm_client import gateway
from core.config import settings

async def test_environment_and_services():
    print("=================================================================")
    print("🔍 DIAGNOSTIK KONFIGURASI .ENV (AutoRestock-Agent)")
    print("=================================================================")
    print(f"Port Server      : {settings.API_PORT}")
    print(f"Mock Mode        : {settings.MOCK_MODELS}")
    print(f"Model Qwen       : {settings.MODEL_QWEN_NAME} -> {settings.MODEL_QWEN_URL}")
    print(f"Model Nemotron   : {settings.MODEL_NEMOTRON_NAME} -> {settings.MODEL_NEMOTRON_URL}")
    print(f"Model OCR        : {settings.MODEL_OCR_NAME} -> {settings.MODEL_OCR_LIGHTON_URL}")
    print(f"Email SMTP       : {settings.SMTP_EMAIL} ({settings.SMTP_SERVER}:{settings.SMTP_PORT})")
    print(f"Telegram Bot ID  : {settings.TELEGRAM_BOT_TOKEN[:15]}... (Chat ID: {settings.TELEGRAM_CHAT_ID})")
    print("=================================================================\n")
    
    # 1. Test Telegram
    print("1️⃣ [TELEGRAM] Menguji koneksi bot Telegram...")
    if settings.TELEGRAM_BOT_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getMe")
                if res.status_code == 200:
                    bot_info = res.json().get("result", {})
                    print(f"   ✅ [BERHASIL] Bot terhubung: @{bot_info.get('username')} ({bot_info.get('first_name')})")
                else:
                    print(f"   ❌ [GAGAL] Token bot tidak valid: {res.text}")
        except Exception as e:
            print(f"   ❌ [GAGAL] Error koneksi Telegram: {e}")
    else:
        print("   ⚠️ Telegram tidak dikonfigurasi.")

    # 2. Test SMTP Email
    print("\n2️⃣ [EMAIL SMTP] Menguji login SMTP Gmail...")
    if settings.SMTP_EMAIL and settings.SMTP_PASSWORD:
        try:
            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=8) as server:
                server.starttls()
                server.login(settings.SMTP_EMAIL, settings.SMTP_PASSWORD)
                print(f"   ✅ [BERHASIL] Akun SMTP login sukses ({settings.SMTP_EMAIL})")
        except Exception as e:
            print(f"   ❌ [GAGAL] Login SMTP gagal: {e}")
    else:
        print("   ⚠️ SMTP tidak dikonfigurasi.")

    # 3. Test LLM Gateway
    print("\n3️⃣ [LLM GATEWAY] Menguji pemanggilan model AI...")
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant."},
        {"role": "user", "content": "Tolong balas: 'Halo dari AutoRestock AI'"}
    ]
    
    if settings.MOCK_MODELS:
        print("   ℹ️ MOCK_MODELS=True (Mode simulasi aktif)")
        res = await gateway.chat_completion(settings.MODEL_QWEN_NAME, messages)
        print(f"   ✅ [MOCK RESPONSE]: {res}")
    else:
        try:
            res = await gateway.chat_completion(settings.MODEL_QWEN_NAME, messages, temperature=0.7)
            print(f"   ✅ [BERHASIL] Balasan dari LLM:")
            print(f"   \"{res}\"")
        except Exception as e:
            print(f"   ❌ [GAGAL] Error saat memanggil LLM: {e}")
            print("   ℹ️ Alasan: Pastikan WiFi Anda sudah terhubung ke jaringan kantor/VPN (10.7.1.21) untuk mengakses api.balillm.ai, atau aktifkan MOCK_MODELS=True di .env jika ingin uji offline.")

    print("\n=================================================================")
    print("🏁 Diagnostik selesai.")
    print("=================================================================")

if __name__ == "__main__":
    asyncio.run(test_environment_and_services())
