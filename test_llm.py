import asyncio
import os
from core.llm_client import gateway
from core.config import settings

async def test_real_llm():
    print("========================================")
    print("🔍 UJI COBA LLM ASLI (AutoRestock-Agent)")
    print("========================================")
    print(f"URL Qwen     : {settings.MODEL_QWEN_URL}")
    print(f"URL Nemotron : {settings.MODEL_NEMOTRON_URL}")
    print("========================================\n")
    
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant."},
        {"role": "user", "content": "Tolong balas pesan ini dengan kalimat: 'Halo, saya adalah AI asli yang merespon secara langsung, bukan mock!'. Jangan tambahkan kalimat lain."}
    ]
    
    print("Tunggu sebentar, sedang mengirim pesan ke LLM...")
    try:
        response = await gateway.chat_completion("qwen-35b", messages, temperature=0.7)
        print("\n✅ [BERHASIL] Balasan dari LLM:")
        print(f"\"{(response)}\"")
    except Exception as e:
        print("\n❌ [GAGAL] Error saat memanggil LLM:")
        print(e)
        print("\nAlasan: Pastikan WiFi Anda sudah terhubung ke jaringan yang benar (10.7.1.21) atau cek API_KEY di .env")

if __name__ == "__main__":
    asyncio.run(test_real_llm())
