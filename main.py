import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mithi")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY environment variable is not set.")

# Set DEBUG_ERRORS=1 on Render to see the real error inside the chat
DEBUG_ERRORS = os.getenv("DEBUG_ERRORS") == "1"

# Models are tried in order. You can override them on Render with an environment
# variable called MODELS (comma separated), so no code change is needed later.
DEFAULT_MODELS = [
    "openrouter/free",
    "inclusionai/ling-3.2-flash:free",
]
MODELS = [m.strip() for m in os.getenv("MODELS", "").split(",") if m.strip()] or DEFAULT_MODELS

MAX_INPUT_CHARS = 1000
MAX_HISTORY = 10

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
    timeout=20,
    max_retries=0,
    default_headers={
        "HTTP-Referer": "https://mithi-chatbot.onrender.com",
        "X-Title": "Leak Weak - MITHI Chatbot",
    },
)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

SYSTEM_PROMPT = (
    "You are MITHI, built by the Leak Weak team (Kishan, Projjwal, Shaswata, Soumalya and Param). "
    "You are a supportive, empathetic and knowledgeable AI health ally for the "
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


def build_messages(history, user_input, merge_system):
    """Some free models reject a system role, so the 2nd attempt folds it into the first user message."""
    convo = [dict(m) for m in history] + [{"role": "user", "content": user_input}]
    if not merge_system:
        return [{"role": "system", "content": SYSTEM_PROMPT}] + convo
    for m in convo:
        if m["role"] == "user":
            m["content"] = SYSTEM_PROMPT + "\n\nUser: " + m["content"]
            break
    return convo


def ask_model(history, user_input):
    last_error = None
    for model in MODELS:
        for merge_system in (False, True):
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=build_messages(history, user_input, merge_system),
                    max_tokens=600,
                    temperature=0.6,
                )
                reply = (completion.choices[0].message.content or "").strip()
                if reply:
                    return reply
                last_error = ValueError(f"Empty reply from {model}")
                log.warning("Empty reply from %s (merged_system=%s)", model, merge_system)
            except Exception as e:
                last_error = e
                log.error("Model %s failed (merged_system=%s): %s: %s",
                          model, merge_system, type(e).__name__, e)
    raise last_error or RuntimeError("All models failed")


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
@limiter.limit("10 per minute; 100 per day")
def chat():
    data = request.get_json(silent=True) or {}
    user_input = str(data.get("message", "")).strip()

    if not user_input:
        return jsonify({"reply": "Please type a message so MITHI can help you."}), 400
    if len(user_input) > MAX_INPUT_CHARS:
        return jsonify({"reply": f"Your message is too long. Please keep it under {MAX_INPUT_CHARS} characters."}), 400

    history = clean_history(data.get("history"))

    try:
        reply = ask_model(history, user_input)
        return jsonify({"reply": reply})
    except Exception as e:
        log.error("All attempts failed: %s: %s", type(e).__name__, e)
        if DEBUG_ERRORS:
            return jsonify({"reply": f"DEBUG: {type(e).__name__}: {str(e)[:300]}"}), 502
        return jsonify({"reply": "MITHI is having a little trouble connecting right now. Please try again in a moment."}), 502


@app.errorhandler(429)
def too_many_requests(_):
    return jsonify({"reply": "You're sending messages too quickly. Please wait a minute and try again."}), 429


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)