import httpx
import json
from app.services.car_service import car_service

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2:1b"

class AIChatService:
    async def get_response(self, message: str) -> dict:
        # Step 1: Extract intent and parameters via LLM
        prompt = f"""
        You are an AI assistant for a car showroom. Extract the user's intent to find cars.
        User message: "{message}"
        
        Return ONLY a JSON object with:
        - "brand": string or null
        - "max_price": integer or null
        - "intent": string (e.g. "search_car", "general_chat")
        
        Example: {{"brand": "toyota", "max_price": 300000000, "intent": "search_car"}}
        """
        
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(OLLAMA_URL, json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                }, timeout=30.0)
                res_data = res.json()
                response_text = res_data.get("response", "{}")
                parsed = json.loads(response_text)
        except Exception:
            # Fallback
            parsed = {"brand": None, "max_price": None, "intent": "general_chat"}
        
        if parsed.get("intent") == "search_car":
            brand = parsed.get("brand")
            max_price = parsed.get("max_price")
            
            cars, _ = await car_service.get_all_cars(
                page=1, limit=5, brand=brand, max_price=max_price, status="Tersedia"
            )
            
            recommendations = []
            for c in cars:
                recommendations.append({
                    "id": str(c.id),
                    "brand": c.brand,
                    "type": c.type,
                    "price": c.price
                })
            
            if recommendations:
                reply = f"Saya menemukan beberapa mobil {brand or ''} yang mungkin Anda suka."
            else:
                reply = "Maaf, saya tidak menemukan mobil yang sesuai dengan kriteria Anda saat ini. Silakan hubungi admin."
                
            return {
                "reply": reply,
                "car_recommendations": recommendations
            }
            
        else:
            # General chat
            prompt_chat = f"You are a helpful car showroom assistant. Answer this in Indonesian: {message}"
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

ai_chat_service = AIChatService()
