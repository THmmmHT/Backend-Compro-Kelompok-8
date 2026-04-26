import httpx
import json
import re
from app.services.car_service import car_service

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2:1b"

# Kata kunci untuk mendeteksi intent secara deterministik
SCHEDULE_KEYWORDS = [
    "jadwal", "janjian", "janji", "ketemu", "bertemu", "temu",
    "appointment", "schedule", "booking", "book", "pesan jadwal",
    "konsultasi", "kunjungan", "visit", "datang", "test drive"
]

CAR_KEYWORDS = [
    "mobil", "car", "kendaraan", "budget", "harga", "juta", "jt",
    "cari", "rekomendasi", "recommend", "murah", "mahal",
    "mpv", "suv", "sedan", "hatchback", "matic", "manual"
]


class AIChatService:
    def _detect_intent(self, message: str) -> str:
        """Deteksi intent secara deterministik menggunakan keyword matching."""
        msg_lower = message.lower()
        
        has_schedule = any(kw in msg_lower for kw in SCHEDULE_KEYWORDS)
        has_car = any(kw in msg_lower for kw in CAR_KEYWORDS)
        
        if has_schedule:
            return "schedule"
        elif has_car:
            return "search_car"
        else:
            return "general"

    async def _handle_search_car(self, message: str) -> dict:
        """Handle pencarian mobil berdasarkan budget."""
        max_price = None
        
        # Regex untuk menangkap '200 juta', '200jt', '250.000.000'
        juta_match = re.search(r'(\d+)\s*(juta|jt)', message.lower())
        if juta_match:
            max_price = int(juta_match.group(1)) * 1000000
        else:
            num_match = re.search(r'(\d{3,}(?:\.\d{3})*)', message)
            if num_match:
                val = num_match.group(1).replace('.', '')
                if len(val) >= 7:
                    max_price = int(val)

        if max_price:
            cars, _ = await car_service.get_all_cars(page=1, limit=5, max_price=max_price)
        else:
            cars, _ = await car_service.get_all_cars(page=1, limit=5)
            
        recommendations = []
        cars_context_lines = []
        for c in cars:
            recommendations.append({
                "id": str(c.id),
                "brand": c.brand,
                "type": c.type,
                "price": c.price,
                "status": c.status
            })
            cars_context_lines.append(f"- {c.brand} ({c.type}): Rp {c.price:,.0f} (Status: {c.status})")
            
        if not cars:
            cars_context = "Tidak ada mobil di database yang harganya masuk dalam budget tersebut."
        else:
            cars_context = "\n".join(cars_context_lines)
            
        response_prompt = f"""
        Kamu adalah asisten dealer mobil yang ramah. Jawab dalam bahasa Indonesia.
        Pesan User: "{message}"
        
        Daftar mobil yang SESUAI budget user (berdasarkan database):
        {cars_context}
        
        Tugasmu:
        1. Beritahu user mobil apa saja yang tersedia dari daftar di atas.
        2. Jika ada mobil berstatus 'Terjual', beri tahu secara sopan bahwa mobil itu sudah terjual.
        3. Jika daftar mobil kosong, minta maaf dan katakan bahwa belum ada mobil yang sesuai budget.
        4. JANGAN PERNAH merekomendasikan atau menyebutkan mobil yang tidak ada di daftar di atas.
        5. Di akhir jawaban, tawarkan bahwa user bisa membuat jadwal untuk melihat mobil langsung.
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

    async def _handle_schedule(self, message: str) -> dict:
        """Handle permintaan untuk membuat jadwal/appointment."""
        # Ambil daftar mobil tersedia untuk ditawarkan
        cars, _ = await car_service.get_all_cars(page=1, limit=10, status="Tersedia")
        
        cars_list = []
        for c in cars:
            cars_list.append(f"- {c.brand} ({c.type}): Rp {c.price:,.0f} [ID: {str(c.id)}]")
        
        if cars_list:
            available_cars = "\n".join(cars_list)
        else:
            available_cars = "Saat ini belum ada mobil tersedia."

        response_prompt = f"""
        Kamu adalah asisten dealer mobil yang ramah. Jawab dalam bahasa Indonesia.
        Pesan User: "{message}"
        
        User ingin membuat jadwal untuk bertemu/konsultasi/test drive di showroom.
        
        Berikut daftar mobil yang tersedia di showroom:
        {available_cars}
        
        Tugasmu:
        1. Sambut user dengan ramah dan konfirmasi bahwa kamu bisa membantu membuat jadwal.
        2. Jelaskan bahwa untuk membuat jadwal, user perlu:
           a. Login terlebih dahulu ke akun mereka (jika belum login).
           b. Memilih mobil yang ingin dilihat dari daftar di atas.
           c. Menentukan tanggal kunjungan (minimal H+1 dari hari ini).
        3. Tampilkan daftar mobil yang tersedia dari data di atas agar user bisa memilih.
        4. Beritahu bahwa user bisa langsung membuat jadwal melalui menu 'Jadwal' di website, atau menghubungi admin untuk dibantu.
        5. Maksimal 2 jadwal pending per akun.
        6. JANGAN mengarang mobil yang tidak ada di daftar.
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
            "car_recommendations": [],
            "action": {
                "type": "navigate_schedule",
                "endpoint": "POST /api/v1/schedules",
                "required_fields": {
                    "car_id": "Pilih dari daftar mobil tersedia",
                    "date": "Format: YYYY-MM-DDTHH:MM:SS (minimal H+1)"
                },
                "note": "User harus login terlebih dahulu untuk membuat jadwal."
            }
        }

    async def _handle_general(self, message: str) -> dict:
        """Handle obrolan umum."""
        prompt_chat = f"""
        Kamu adalah asisten dealer mobil yang ramah. Jawab dalam bahasa Indonesia.
        Pesan User: "{message}"
        
        Tugasmu:
        1. Jawab pertanyaan user dengan sopan.
        2. Jika user bertanya tentang showroom, jelaskan bahwa kamu bisa membantu mencari mobil atau membuat jadwal kunjungan.
        3. Jangan mengarang data mobil. Sarankan user untuk bertanya tentang budget atau jenis mobil yang diinginkan.
        """
        
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(OLLAMA_URL, json={
                    "model": MODEL_NAME,
                    "prompt": prompt_chat,
                    "stream": False
                }, timeout=30.0)
                reply = res.json().get("response", "Maaf, saya sedang tidak bisa merespon.")
        except Exception:
            reply = "Maaf, koneksi ke AI sedang terganggu."
            
        return {
            "reply": reply,
            "car_recommendations": []
        }

    async def get_response(self, message: str) -> dict:
        """Main handler: detect intent → route to the right handler."""
        intent = self._detect_intent(message)
        
        if intent == "search_car":
            return await self._handle_search_car(message)
        elif intent == "schedule":
            return await self._handle_schedule(message)
        else:
            return await self._handle_general(message)

ai_chat_service = AIChatService()
