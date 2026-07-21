import os, json, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from openai import OpenAI

GROQ_KEY = os.getenv("GROQ_API_KEY")
OR_KEY = os.getenv("OPENROUTER_API_KEY")

client = OpenAI(api_key=GROQ_KEY, base_url="https://api.groq.com/openai/v1") if GROQ_KEY else OpenAI(api_key=OR_KEY, base_url="https://openrouter.ai/api/v1")
MODEL = "llama-3.3-70b-versatile" if GROQ_KEY else "meta-llama/llama-3.3-70b-instruct"

def clean_md(text):
    text = re.sub(r'\*{1,2}(.*?)\*{1,2}', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    return text.strip()

SYSTEM_PROMPT = (
    "You are a research analyst. The user asks a question or gives a topic. "
    "Provide a structured report:\n"
    "1. Executive Summary (2-3 sentences)\n"
    "2. Key Facts (3-5 points)\n"
    "3. Analysis & Conclusions\n"
    "4. Recommendations\n\n"
    "Be specific, no fluff. Write in English."
)

PREDICT_PERSPECTIVES = {
    "optimist": "You are an optimistic analyst. Find the best-case scenarios. Write in English.",
    "realist": "You are a pragmatic analyst. Assess the most likely course of events. Write in English.",
    "pessimist": "You are a critical analyst. Find risks and worst-case scenarios. Write in English.",
    "expert": "You are an expert in this field. Give a deep professional analysis. Write in English."
}

def research(topic):
    r = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": topic}
        ]
    )
    return clean_md(r.choices[0].message.content)

def predict(topic):
    results = []
    for name, prompt in PREDICT_PERSPECTIVES.items():
        r = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": topic}
            ]
        )
        results.append(f"{name.title()}:\n{r.choices[0].message.content}")

    s = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Synthesize the 4 analyses into a single forecast with probabilities."},
            {"role": "user", "content": "\n\n---\n\n".join(results)}
        ]
    )
    return clean_md(f"Forecast:\n{s.choices[0].message.content}")

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get('content-length', 0))
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"topic": raw.decode()}
            topic = body.get('topic', '')

            if not topic:
                self.send_json({"error": "topic required"}, 400)
                return

            if self.path == '/research':
                result = research(topic)
            elif self.path == '/predict':
                result = predict(topic)
            else:
                self.send_json({"error": "not found"}, 404)
                return

            self.send_json({"result": result})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, fmt, *args):
        print(f"[API] {args[0]} {args[1]} {args[2]}")

if __name__ == '__main__':
    port = int(os.getenv("API_PORT", "9999"))
    print(f"Research API on port {port}")
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()

