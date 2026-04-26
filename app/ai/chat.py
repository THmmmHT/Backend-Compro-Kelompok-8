import httpx
import json
import re
from collections import defaultdict
from app.services.car_service import car_service
from app.models.user import User

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "llama3.2:1b"
MAX_HISTORY = 10

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
    def __init__(self):
        self.history: dict[str, list[dict]] = defaultdict(list)

    def _add_to_history(self, session_id: str, role: str, content: str):
        self.history[session_id].append({"role": role, "content": content})
        if len(self.history[session_id]) > MAX_HISTORY:
            self.history[session_id] = self.history[session_id][-MAX_HISTORY:]

    def _detect_intent(self, message: str) -> str:
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in SCHEDULE_KEYWORDS):
            return "schedule"
        elif any(kw in msg_lower for kw in CAR_KEYWORDS):
            return "search_car"
        return "general"

    async def _call_ollama(self, system_prompt: str, messages: list, timeout: float = 45.0) -> str:
        """Panggil Ollama Chat API dengan format messages."""
        try:
            all_messages = [{"role": "system", "content": system_prompt}] + messages
            async with httpx.AsyncClient() as client:
                res = await client.post(OLLAMA_URL, json={
                    "model": MODEL_NAME,
                    "messages": all_messages,
                    "stream": False
                }, timeout=timeout)
                data = res.json()
                return data.get("message", {}).get("content", "Maaf, saya gagal merangkai jawaban.")
        except Exception:
            return "Maaf, ada gangguan koneksi ke server AI."

    async def _handle_search_car(self, message: str, user: User, session_id: str) -> dict:
        max_price = None
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
                "id": str(c.id), "brand": c.brand,
                "type": c.type, "price": c.price, "status": c.status
            })
            cars_context_lines.append(f"- {c.brand} ({c.type}): Rp {c.price:,.0f} [{c.status}]")

        cars_context = "\n".join(cars_context_lines) if cars else "Tidak ada mobil yang sesuai budget."

        system_prompt = f"""Kamu asisten dealer mobil. Jawab singkat dan natural dalam bahasa Indonesia.
Nama user: {user.username}. Data mobil di showroom:
{cars_context}
Aturan: Hanya rekomendasikan mobil dari data di atas. Jika status Terjual, bilang sudah terjual. Jawab langsung tanpa basa-basi berlebihan."""

        # Bangun messages dari history
        messages = list(self.history[session_id]) + [{"role": "user", "content": message}]

        reply = await self._call_ollama(system_prompt, messages)
        return {"reply": reply, "car_recommendations": recommendations}

    async def _handle_schedule(self, message: str, user: User, session_id: str) -> dict:
        cars, _ = await car_service.get_all_cars(page=1, limit=10, status="Tersedia")
        cars_list = [f"- {c.brand} ({c.type}): Rp {c.price:,.0f}" for c in cars]
        available_cars = "\n".join(cars_list) if cars_list else "Belum ada mobil tersedia."

        system_prompt = f"""Kamu asisten dealer mobil. Jawab singkat dan natural dalam bahasa Indonesia.
Nama user: {user.username}. User ingin buat jadwal kunjungan.
Mobil tersedia:
{available_cars}
Aturan: Bantu user buat jadwal. Syarat: pilih mobil, tanggal minimal besok, max 2 jadwal pending. Arahkan ke menu Jadwal di website."""

        messages = list(self.history[session_id]) + [{"role": "user", "content": message}]

        reply = await self._call_ollama(system_prompt, messages)
        return {
            "reply": reply, "car_recommendations": [],
            "action": {
                "type": "navigate_schedule",
                "endpoint": "POST /api/v1/schedules",
                "required_fields": {"car_id": "Pilih mobil", "date": "YYYY-MM-DDTHH:MM:SS (min H+1)"}
            }
        }

    async def _handle_general(self, message: str, user: User, session_id: str) -> dict:
        system_prompt = f"""Kamu asisten dealer mobil. Jawab singkat dan natural dalam bahasa Indonesia.
Nama user: {user.username}. Kamu bisa bantu cari mobil dan buat jadwal kunjungan. Jangan mengarang data mobil."""

        messages = list(self.history[session_id]) + [{"role": "user", "content": message}]

        reply = await self._call_ollama(system_prompt, messages, timeout=30.0)
        return {"reply": reply, "car_recommendations": []}

    async def get_response(self, message: str, user: User, session_id: str = "default") -> dict:
        self._add_to_history(session_id, "user", message)

        intent = self._detect_intent(message)
        if intent == "search_car":
            result = await self._handle_search_car(message, user, session_id)
        elif intent == "schedule":
            result = await self._handle_schedule(message, user, session_id)
        else:
            result = await self._handle_general(message, user, session_id)

        self._add_to_history(session_id, "assistant", result["reply"])
        return result

ai_chat_service = AIChatService()
