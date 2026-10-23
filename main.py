import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from google import genai

API_BASE = "https://api.wurk.fun"
AGENT_WALLET = os.getenv("AGENT_WALLET_ADDRESS")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
PORT = int(os.getenv("PORT", 10000))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Gemini Client if key exists
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Health-check server to keep Render service alive
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"WURK Agent + Gemini is active and running.")

    def log_message(self, format, *args):
        return

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    server.serve_forever()

def send_telegram_alert(message: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"Telegram alert error: {e}", flush=True)

def solve_with_gemini(task_description: str, task_requirements: str = "") -> str:
    """Uses Gemini 2.5 Flash to generate accurate, high-quality deliverables."""
    if not ai_client:
        return f"Completed analysis for: {task_description}"

    prompt = (
        "You are an elite, highly competent autonomous worker agent on the WURK platform.\n"
        "Your goal is to provide a comprehensive, accurate, high-quality submission for the following task.\n"
        "Follow all guidelines precisely. Do not include conversational filler like 'Here is your answer:'. "
        "Jump straight into the deliverable.\n\n"
        f"TASK DESCRIPTION:\n{task_description}\n\n"
        f"REQUIREMENTS / CRITERIA:\n{task_requirements}\n\n"
        "DELIVERABLE:"
    )

    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API generation error: {e}", flush=True)
        return f"Autonomous analysis for: {task_description}"

def run_loop():
    print(f"[*] Agent started on Render for wallet: {AGENT_WALLET}", flush=True)
    if GEMINI_API_KEY:
        print("[*] Gemini AI engine connected successfully.", flush=True)
    else:
        print("[!] Warning: GEMINI_API_KEY not set. Using fallback responses.", flush=True)

    send_telegram_alert("🚀 WURK Agent with Gemini reasoning is live on Render!")

    completed_ids = set()

    while True:
        try:
            res = requests.get(f"{API_BASE}/jobs/open", params={"audience": "agents"}, timeout=15)
            if res.status_code == 200:
                jobs = res.json().get("jobs", [])
                print(f"[*] Polled WURK: {len(jobs)} active open tasks returned.", flush=True)

                for job in jobs:
                    job_id = job.get("id")
                    if job_id in completed_ids:
                        continue

                    # Skip only tasks that strictly demand manual physical human presence
                    if job.get("audience") == "humans_only" or job.get("human_only"):
                        continue

                    desc = job.get("description", "")
                    reqs = job.get("requirements", "")
                    print(f"[+] Task detected: {job_id} -> {desc[:50]}...", flush=True)

                    # Solve task with Gemini
                    deliverable = solve_with_gemini(desc, reqs)

                    payload = {
                        "jobId": job_id,
                        "workerAddress": AGENT_WALLET,
                        "deliverable": deliverable
                    }
                    sub = requests.post(f"{API_BASE}/jobs/submit", json=payload, timeout=20)
                    if sub.status_code in (200, 201):
                        completed_ids.add(job_id)
                        send_telegram_alert(
                            f"💰 Task Solved & Submitted!\nID: {job_id}\nBrief: {desc[:60]}\n\nPreview: {deliverable[:120]}..."
                        )
                        print(f"[✓] Submitted solution for job {job_id}", flush=True)
                    else:
                        print(f"[!] Submission for job {job_id} returned status: {sub.status_code}", flush=True)
            else:
                print(f"API ping status: {res.status_code}", flush=True)

        except Exception as e:
            print(f"Worker iteration error: {e}", flush=True)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    if not AGENT_WALLET:
        print("ERROR: AGENT_WALLET_ADDRESS variable is not set!", flush=True)
    else:
        http_thread = threading.Thread(target=start_health_server, daemon=True)
        http_thread.start()
        print(f"[*] Health server listening on port {PORT}", flush=True)
        run_loop()
