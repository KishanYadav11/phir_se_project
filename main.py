import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("methi")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)  # correct client IP behind Render

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY environment variable is not set.")

MODEL = "inclusionai/ling-3.2-flash:free"
MAX_INPUT_CHARS = 1000
MAX_HISTORY = 10

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
    timeout=40,
    max_retries=1,
    default_headers={
        "HTTP-Referer": "https://methi-chatbot.onrender.com",
        "X-Title": "Leak Weak - METHI Chatbot",
    },
)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

SYSTEM_PROMPT = ("made by kishan , projjwal,shaswata, param, soumalya"
    "You are METHI, a supportive, empathetic and knowledgeable AI health ally for the "
    "'Leak Weak' menstrual health and hygiene project. Give scientifically accurate, "
    "easy-to-understand, non-judgmental information in a warm tone. Keep answers concise "
    "(under about 200 words) and use plain text without markdown headings.\n\n"
    "Safety rules:\n"
    "- You are not a doctor. Do not diagnose conditions or recommend medicine doses.\n"
    "- Advise seeing a doctor for: very heavy bleeding (soaking a pad/tampon every hour), "
    "severe pain that stops daily activity, periods missing for 3+ months, bleeding after "
    "menopause or between periods, fever with tampon use, or a possible pregnancy.\n"
    "- If someone mentions self-harm, abuse, or feeling unsafe, respond with care, encourage "
    "them to reach out to a trusted adult or a local emergency/helpline number, and do not "
    "continue with unrelated topics.\n"
    "- Only discuss menstrual health, hygiene, puberty and related wellbeing. Politely decline "
    "unrelated requests.\n"
    "- Never claim to be human."
)


def clean_history(raw):
    """Accept only well-formed user/assistant messages, capped in size."""
    cleaned = []
    if not isinstance(raw, list):
        return cleaned
    for item in raw[-MAX_HISTORY:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            cleaned.append({"role": role, "content": content.strip()[:MAX_INPUT_CHARS]})
    return cleaned


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
@limiter.limit("10 per minute; 100 per day")
def chat():
    data = request.get_json(silent=True) or {}
    user_input = str(data.get("message", "")).strip()

    if not user_input:
        return jsonify({"reply": "Please type a message so METHI can help you."}), 400
    if len(user_input) > MAX_INPUT_CHARS:
        return jsonify({"reply": f"Your message is too long. Please keep it under {MAX_INPUT_CHARS} characters."}), 400

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += clean_history(data.get("history"))
    messages.append({"role": "user", "content": user_input})

    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=600,
            temperature=0.6,
        )
        reply = (completion.choices[0].message.content or "").strip()
        if not reply:
            raise ValueError("Empty reply from model")
        return jsonify({"reply": reply})
    except Exception as e:
        log.error("API error: %s", e)
        return jsonify({"reply": "METHI is having a little trouble connecting right now. Please try again in a moment."}), 502


@app.errorhandler(429)
def too_many_requests(_):
    return jsonify({"reply": "You're sending messages too quickly. Please wait a minute and try again."}), 429


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)