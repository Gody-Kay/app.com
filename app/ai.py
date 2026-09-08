import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from groq import Groq

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

GROQ_MODEL = "openai/gpt-oss-120b"


def generate_lesson_content(title: str, raw_material: str) -> str:
    prompt = f"""You are a friendly, patient tutor helping a student learn.

Topic: {title}

Study material provided by the student:
\"\"\"
{raw_material}
\"\"\"

Break this down into a clear, well-structured lesson. Use this format:
1. A brief, encouraging introduction (1-2 sentences)
2. Key concepts explained simply, using headers
3. A couple of concrete examples
4. A short summary at the end

Use simple HTML tags for formatting (like <h3>, <p>, <ul>, <li>, <strong>) since this will be displayed directly in a web page. Do not include <html>, <head>, or <body> tags — just the content itself. Keep the tone warm and encouraging, like a supportive teacher."""

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def generate_chat_reply(conversation_history: list[dict], new_message: str, system_prompt: str | None = None) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for msg in conversation_history:
        messages.append({
            "role": "assistant" if msg["role"] == "model" else "user",
            "content": msg["content"]
        })
    messages.append({"role": "user", "content": new_message})

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
    )
    return response.choices[0].message.content


def generate_chat_reply_with_file(conversation_history: list[dict], new_message: str, file_path: str, mime_type: str) -> str:
    contents = []
    for msg in conversation_history:
        contents.append({
            "role": "user" if msg["role"] == "user" else "model",
            "parts": [{"text": msg["content"]}]
        })

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    text_part = new_message if new_message else "Please look at this and help me understand it."
    contents.append({
        "role": "user",
        "parts": [
            {"text": text_part},
            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
        ]
    })

    response = gemini_client.models.generate_content(model="gemini-3.6-flash", contents=contents)
    return response.text


def generate_quiz(lesson_title: str, lesson_content: str, difficulty: str) -> str:
    prompt = f"""Based on this lesson, create a 5-question multiple choice quiz at {difficulty} difficulty.

Lesson title: {lesson_title}
Lesson content: {lesson_content}

Respond with ONLY valid JSON, no markdown code fences, no extra text. Use exactly this structure:
[
  {{
    "question": "...",
    "options": ["...", "...", "...", "..."],
    "correct_index": 0,
    "explanation": "..."
  }}
]

correct_index is the 0-based index of the correct option. Make questions genuinely test understanding of the lesson content, appropriate for {difficulty} difficulty level."""

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()