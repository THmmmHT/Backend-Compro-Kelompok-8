import httpx
import json
from app.services.car_service import car_service

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2:1b"

class AIChatService:
    async def get_response(self, message: str) -> dict:
        # Step 1: Extract budget using a very simple prompt
        budget_prompt = f"""
        Tugas: Ekstrak batas harga maksimal (budget) dari kalimat berikut.
        Kalimat: "{message}"
        
        Aturan:
        - Jika ada kata "juta", kalikan dengan 1000000. (contoh: 200 juta = 200000000)
        - Hanya kembalikan ANGKA tanpa titik, koma, atau teks apapun.
        - Jika tidak ada budget, kembalikan angka 0.
        
        Output:
        """
        
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(OLLAMA_URL, json={
                    "model": MODEL_NAME,
                    "prompt": budget_prompt,
                    "stream": False
                }, timeout=15.0)
                
                budget_str = res.json().get("response", "0").strip()
                import re
                numbers = re.findall(r'\d+', budget_str)
                max_price = int("".join(numbers)) if numbers else 0
        except Exception:
            max_price = 0
            
        # Jika max_price = 0, kita ambil semua mobil, jika tidak filter sesuai budget.
        # Kita tambahkan 10% toleransi agar mobil yang sedikit di atas budget tetap masuk pertimbangan
        search_max = (max_price * 1.1) if max_price > 0 else None
        
        cars, _ = await car_service.get_all_cars(page=1, limit=10, max_price=search_max)
        
        recommendations = []
        cars_context_lines = []
        for c in cars:
            if c.status == "Tersedia":
                recommendations.append({
                    "id": str(c.id),
                    "brand": c.brand,
                    "type": c.type,
                    "price": c.price,
                    "status": c.status
                })
            
            cars_context_lines.append(f"- {c.brand} ({c.type}): Rp {c.price:,.0f} (Status: {c.status})")
            
        if not cars:
            cars_context = "Tidak ada mobil di database yang mendekati budget ini."
        else:
            cars_context = "\n".join(cars_context_lines)
            
        # Step 2: Generate friendly response
        response_prompt = f"""
        Kamu adalah asisten showroom mobil yang ramah. Jawablah dalam bahasa Indonesia.
        
        Pesan pengguna: "{message}"
        Budget terdeteksi: Rp {max_price:,.0f}
        
        Daftar mobil yang SESUAI budget dari database kami:
        {cars_context}
        
        Instruksi:
        1. Berikan rekomendasi HANYA dari daftar mobil di atas. Jangan merekomendasikan mobil lain.
        2. Jika ada mobil dengan status 'Terjual', beritahu dengan sopan bahwa mobil tersebut masuk budget tapi sayangnya sudah laku.
        3. Jika daftar mobil kosong, minta maaf dan katakan belum ada mobil yang cocok dengan budget tersebut.
        4. Jawablah dengan singkat, ramah, dan profesional.
        """
        
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(OLLAMA_URL, json={
                    "model": MODEL_NAME,
                    "prompt": response_prompt,
                    "stream": False
                }, timeout=45.0)
                reply = res.json().get("response", "Maaf, saya gagal merangkai jawaban.")
        except Exception:
            reply = "Maaf, ada gangguan koneksi ke server AI."

        return {
            "reply": reply,
            "car_recommendations": recommendations
        }

ai_chat_service = AIChatService()
