import google.generativeai as genai
import cv2
import base64

class AIEngine:
    def __init__(self, key):
        genai.configure(api_key=key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        print("[AIEngine] Ready with gemini-2.5-flash")

    def analyze_scene(self, frame, mode):
        if frame is None:
            return "Camera error."
        try:
            # ── Higher resolution for better scene detail ──────────────────
            # 320x240 was too small — Gemini missed objects and lost context
            # 640x480 gives much richer scene understanding with minimal extra latency
            small = cv2.resize(frame, (640, 480))

            # Quality 85 preserves enough detail for accurate object recognition
            _, buffer = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 85])
            img_b64 = base64.b64encode(buffer.tobytes()).decode('utf-8')

            # ── Mode-specific prompts ──────────────────────────────────────
            if mode == "Indoor":
                prompt = (
                    "You are a navigation assistant helping a visually impaired person indoors. "
                    "Look at this image carefully and give a SHORT, CLEAR spoken description. "
                    "Follow this exact order:\n"
                    "1. Where am I? (e.g. corridor, room, kitchen, office)\n"
                    "2. What is directly ahead of me? Is the path clear or blocked?\n"
                    "3. What objects are on my LEFT and RIGHT within 3 metres?\n"
                    "4. Any hazards — steps, wet floor, cables, open doors, low objects?\n"
                    "5. Any people nearby?\n\n"
                    "Rules:\n"
                    "- Use simple words a blind person can act on immediately.\n"
                    "- Give exact directions: left, right, ahead, behind.\n"
                    "- Estimate distances: one step, two metres, arm's reach.\n"
                    "- If path is blocked say: OBSTACLE AHEAD — then describe it.\n"
                    "- Do NOT say 'I see' or 'The image shows'. Speak directly.\n"
                    "- Keep it under 60 words. Be precise, not poetic."
                )
            else:  # Outdoor
                prompt = (
                    "You are a navigation assistant helping a visually impaired person outdoors. "
                    "Look at this image carefully and give a SHORT, CLEAR spoken description. "
                    "Follow this exact order:\n"
                    "1. What type of outdoor area is this? (road, footpath, park, market, etc.)\n"
                    "2. Is the path ahead clear? Any vehicles, people or barriers blocking it?\n"
                    "3. Road or footpath condition — steps, kerbs, uneven ground, puddles?\n"
                    "4. Traffic — any vehicles moving nearby and from which direction?\n"
                    "5. Any landmarks visible — signs, buildings, crossings, traffic lights?\n\n"
                    "Rules:\n"
                    "- Use simple words a blind person can act on immediately.\n"
                    "- Give exact directions: left, right, ahead.\n"
                    "- Estimate distances: nearby, ten metres, across the road.\n"
                    "- If path is blocked say: OBSTACLE AHEAD — then describe it.\n"
                    "- Do NOT say 'I see' or 'The image shows'. Speak directly.\n"
                    "- Keep it under 60 words. Be precise and calm."
                )

            response = self.model.generate_content([
                {'mime_type': 'image/jpeg', 'data': img_b64},
                prompt
            ])

            if response and response.text:
                return response.text.strip()
            return "Path appears clear."

        except Exception as e:
            print(f"[AIEngine] Error: {e}")
            if "429" in str(e):
                return "BUSY"
            if "quota" in str(e).lower():
                return "BUSY"
            return "ERROR"