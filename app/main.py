import os
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.database import engine, Base, get_db
from app import models, auth
from app.auth import get_current_user
from app.ai import generate_lesson_content, generate_chat_reply, generate_chat_reply_with_file, generate_quiz

load_dotenv()

Base.metadata.create_all(bind=engine)
os.makedirs("app/static/uploads", exist_ok=True)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-fallback-change-me"))

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

ALLOWED_MIME_TYPES = {
    "image/png", "image/jpeg", "image/jpg", "image/webp", "image/heic",
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str | None = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class SubjectRequest(BaseModel):
    name: str


class LessonRequest(BaseModel):
    title: str
    subject_id: int
    raw_material_text: str | None = None


class TimetableRequest(BaseModel):
    subject_id: int | None = None
    title: str
    day_of_week: str
    start_time: str
    end_time: str


class ChatSessionRequest(BaseModel):
    lesson_id: int | None = None
    title: str | None = None


class ChatMessageRequest(BaseModel):
    content: str
    attachment_url: str | None = None
    attachment_mime: str | None = None


class QuizRequest(BaseModel):
    difficulty: str


class QuizSubmitRequest(BaseModel):
    score: int


class ProgressRequest(BaseModel):
    last_position: str | None = None
    completed: bool | None = None


# ---- Page routes ----
@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


@app.get("/signup")
def signup_page(request: Request):
    return templates.TemplateResponse(request=request, name="signup.html")


@app.get("/dashboard")
def dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/subject")
def subject_page(request: Request):
    return templates.TemplateResponse(request=request, name="subject.html")


@app.get("/lesson")
def lesson_page(request: Request):
    return templates.TemplateResponse(request=request, name="lesson.html")


@app.get("/timetable")
def timetable_page(request: Request):
    return templates.TemplateResponse(request=request, name="timetable.html")


@app.get("/chat")
def chat_page(request: Request):
    return templates.TemplateResponse(request=request, name="chat.html")


@app.get("/quiz")
def quiz_page(request: Request):
    return templates.TemplateResponse(request=request, name="quiz.html")


@app.get("/progress")
def progress_page(request: Request):
    return templates.TemplateResponse(request=request, name="progress.html")


# ---- Test routes ----
@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


@app.get("/test-db")
def test_db(db: Session = Depends(get_db)):
    user_count = db.query(models.User).count()
    return {"status": "connected", "users_in_db": user_count}


# ---- Auth routes ----
@app.post("/signup")
@limiter.limit("5/minute")
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)):
    existing = auth.get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = auth.create_user(db, payload.email, payload.password, payload.name)
    request.session["user_id"] = user.id
    return {"id": user.id, "email": user.email, "name": user.name}


@app.post("/login")
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    request.session["user_id"] = user.id
    return {"id": user.id, "email": user.email, "name": user.name}


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"status": "logged out"}


@app.get("/me")
def me(current_user: models.User = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email, "name": current_user.name}


# ---- File upload ----
@app.post("/uploads")
def upload_file(file: UploadFile = File(...), current_user: models.User = Depends(get_current_user)):
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"File type {file.content_type} not supported")
    contents = file.file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")
    ext = os.path.splitext(file.filename)[1]
    safe_name = f"{uuid.uuid4().hex}{ext}"
    save_path = f"app/static/uploads/{safe_name}"
    with open(save_path, "wb") as f:
        f.write(contents)
    return {"url": f"/static/uploads/{safe_name}", "mime_type": file.content_type}


# ---- Subject routes ----
@app.post("/subjects")
def create_subject(payload: SubjectRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    subject = models.Subject(name=payload.name, owner_id=current_user.id)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return {"id": subject.id, "name": subject.name}


@app.get("/subjects")
def list_subjects(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    subjects = db.query(models.Subject).filter(models.Subject.owner_id == current_user.id).all()
    return [{"id": s.id, "name": s.name} for s in subjects]


# ---- Lesson routes: SPECIFIC PATHS FIRST, generic {lesson_id} LAST ----
@app.post("/lessons")
def create_lesson(payload: LessonRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    subject = db.query(models.Subject).filter(
        models.Subject.id == payload.subject_id, models.Subject.owner_id == current_user.id
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    ai_content = None
    if payload.raw_material_text:
        try:
            ai_content = generate_lesson_content(payload.title, payload.raw_material_text)
        except Exception as e:
            print(f"AI generation failed: {e}")
            ai_content = None

    lesson = models.Lesson(
        title=payload.title, subject_id=payload.subject_id,
        raw_material_text=payload.raw_material_text, ai_content=ai_content,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return {"id": lesson.id, "title": lesson.title, "subject_id": lesson.subject_id}


@app.get("/subjects/{subject_id}/lessons")
def list_lessons(subject_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    subject = db.query(models.Subject).filter(
        models.Subject.id == subject_id, models.Subject.owner_id == current_user.id
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    lessons = db.query(models.Lesson).filter(models.Lesson.subject_id == subject_id).all()
    return [{"id": l.id, "title": l.title} for l in lessons]


@app.get("/lessons/recent")
def get_recent_lessons(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    lessons = (
        db.query(models.Lesson).join(models.Subject)
        .filter(models.Subject.owner_id == current_user.id)
        .order_by(models.Lesson.created_at.desc()).limit(5).all()
    )
    return [{"id": l.id, "title": l.title, "subject_name": l.subject.name} for l in lessons]


@app.get("/lessons/in-progress")
def get_in_progress_lessons(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    lessons = (
        db.query(models.Lesson).join(models.Subject).join(models.Progress)
        .filter(
            models.Subject.owner_id == current_user.id,
            models.Progress.completed == False,
            models.Progress.last_position.isnot(None),
        )
        .order_by(models.Progress.updated_at.desc()).limit(5).all()
    )
    return [{"id": l.id, "title": l.title, "subject_name": l.subject.name} for l in lessons]


def calculate_total_xp(lessons):
    total_xp = 0
    for lesson in lessons:
        progress = lesson.progress
        if progress and progress.completed:
            total_xp += 20

        quizzes = [q for q in lesson.quizzes if q.score is not None]
        for q in quizzes:
            total_xp += 10
            difficulty_multiplier = 1.5 if q.difficulty.lower() == "hard" else (1.2 if q.difficulty.lower() == "medium" else 1.0)
            total_xp += (q.score / 100) * 20 * difficulty_multiplier

    return round(total_xp)


def xp_to_level(total_xp):
    level = 1
    xp_for_next = 100
    xp_floor = 0
    while total_xp >= xp_floor + xp_for_next:
        xp_floor += xp_for_next
        level += 1
        xp_for_next = 100 * level

    xp_into_level = total_xp - xp_floor
    percent_to_next = round((xp_into_level / xp_for_next) * 100) if xp_for_next > 0 else 0

    return {
        "level": level,
        "total_xp": total_xp,
        "xp_into_level": xp_into_level,
        "xp_needed_for_next": xp_for_next,
        "percent_to_next_level": percent_to_next,
    }


@app.get("/progress/overview")
def get_progress_overview(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    lessons = (
        db.query(models.Lesson).join(models.Subject)
        .filter(models.Subject.owner_id == current_user.id)
        .order_by(models.Lesson.created_at.desc()).all()
    )

    total_xp = calculate_total_xp(lessons)
    level_info = xp_to_level(total_xp)

    result = []
    for lesson in lessons:
        progress = lesson.progress
        quizzes = sorted(
            [q for q in lesson.quizzes if q.score is not None],
            key=lambda q: q.taken_at, reverse=True
        )

        lesson_xp = 0
        if progress and progress.completed:
            lesson_xp += 20
        for q in quizzes:
            lesson_xp += 10
            mult = 1.5 if q.difficulty.lower() == "hard" else (1.2 if q.difficulty.lower() == "medium" else 1.0)
            lesson_xp += (q.score / 100) * 20 * mult
        lesson_xp = round(lesson_xp)

        result.append({
            "id": lesson.id,
            "title": lesson.title,
            "subject_name": lesson.subject.name,
            "completed": progress.completed if progress else False,
            "last_position": progress.last_position if progress else None,
            "xp_earned": lesson_xp,
            "quizzes": [
                {"difficulty": q.difficulty, "score": q.score, "taken_at": q.taken_at.isoformat()}
                for q in quizzes
            ],
        })

    return {"lessons": result, **level_info}


@app.get("/lessons/{lesson_id}")
def get_lesson(lesson_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    lesson = (
        db.query(models.Lesson).join(models.Subject)
        .filter(models.Lesson.id == lesson_id, models.Subject.owner_id == current_user.id)
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    content = lesson.ai_content if lesson.ai_content else lesson.raw_material_text
    progress = lesson.progress
    return {
        "id": lesson.id, "title": lesson.title, "content": content,
        "last_position": progress.last_position if progress else None,
        "completed": progress.completed if progress else False,
    }


@app.put("/lessons/{lesson_id}/progress")
def update_progress(lesson_id: int, payload: ProgressRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    lesson = (
        db.query(models.Lesson).join(models.Subject)
        .filter(models.Lesson.id == lesson_id, models.Subject.owner_id == current_user.id)
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    progress = lesson.progress
    if not progress:
        progress = models.Progress(lesson_id=lesson_id)
        db.add(progress)

    if payload.last_position is not None:
        progress.last_position = payload.last_position
    if payload.completed is not None:
        progress.completed = payload.completed
    progress.updated_at = datetime.utcnow()

    db.commit()
    return {"status": "saved"}


# ---- Quiz routes ----
@app.post("/lessons/{lesson_id}/quiz")
def create_quiz(lesson_id: int, payload: QuizRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    lesson = (
        db.query(models.Lesson).join(models.Subject)
        .filter(models.Lesson.id == lesson_id, models.Subject.owner_id == current_user.id)
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    content = lesson.ai_content if lesson.ai_content else lesson.raw_material_text
    try:
        questions_text = generate_quiz(lesson.title, content, payload.difficulty)
        json.loads(questions_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quiz generation failed: {e}")
    quiz = models.Quiz(lesson_id=lesson_id, difficulty=payload.difficulty, questions_json=questions_text)
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return {"id": quiz.id}


@app.get("/quizzes/{quiz_id}")
def get_quiz(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    quiz = (
        db.query(models.Quiz).join(models.Lesson).join(models.Subject)
        .filter(models.Quiz.id == quiz_id, models.Subject.owner_id == current_user.id)
        .first()
    )
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return {
        "id": quiz.id, "lesson_title": quiz.lesson.title, "difficulty": quiz.difficulty,
        "questions": json.loads(quiz.questions_json), "score": quiz.score,
    }


@app.post("/quizzes/{quiz_id}/submit")
def submit_quiz(quiz_id: int, payload: QuizSubmitRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    quiz = (
        db.query(models.Quiz).join(models.Lesson).join(models.Subject)
        .filter(models.Quiz.id == quiz_id, models.Subject.owner_id == current_user.id)
        .first()
    )
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    quiz.score = payload.score
    db.commit()
    return {"status": "saved", "score": quiz.score}


# ---- Timetable routes ----
@app.post("/api/timetable")
def create_timetable_entry(payload: TimetableRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = models.TimetableEntry(
        owner_id=current_user.id, subject_id=payload.subject_id, title=payload.title,
        day_of_week=payload.day_of_week, start_time=payload.start_time, end_time=payload.end_time,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "title": entry.title, "day_of_week": entry.day_of_week, "start_time": entry.start_time, "end_time": entry.end_time}


@app.get("/api/timetable")
def list_timetable_entries(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entries = db.query(models.TimetableEntry).filter(models.TimetableEntry.owner_id == current_user.id).all()
    return [
        {"id": e.id, "title": e.title, "day_of_week": e.day_of_week, "start_time": e.start_time,
         "end_time": e.end_time, "subject_name": e.subject.name if e.subject else None}
        for e in entries
    ]


@app.delete("/api/timetable/{entry_id}")
def delete_timetable_entry(entry_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = db.query(models.TimetableEntry).filter(
        models.TimetableEntry.id == entry_id, models.TimetableEntry.owner_id == current_user.id
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return {"status": "deleted"}


# ---- Chat routes ----
@app.post("/chats")
def create_chat_session(payload: ChatSessionRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    session = models.ChatSession(owner_id=current_user.id, lesson_id=payload.lesson_id, title=payload.title or "New Chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id, "title": session.title, "lesson_id": session.lesson_id}


@app.get("/chats")
def list_chat_sessions(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    sessions = (
        db.query(models.ChatSession).filter(models.ChatSession.owner_id == current_user.id)
        .order_by(models.ChatSession.created_at.desc()).all()
    )
    return [{"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()} for s in sessions]


@app.get("/chats/{session_id}/messages")
def get_chat_messages(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id, models.ChatSession.owner_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat not found")
    return [{"id": m.id, "role": m.role, "content": m.content, "attachment_url": m.attachment_url} for m in session.messages]


@app.post("/chats/{session_id}/messages")
def send_chat_message(session_id: int, payload: ChatMessageRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id, models.ChatSession.owner_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat not found")

    user_msg = models.ChatMessage(session_id=session_id, role="user", content=payload.content, attachment_url=payload.attachment_url)
    db.add(user_msg)
    db.commit()

    history = [{"role": m.role, "content": m.content} for m in session.messages if m.id != user_msg.id]

    if session.lesson_id:
        lesson = db.query(models.Lesson).filter(models.Lesson.id == session.lesson_id).first()
        lesson_content = (lesson.ai_content or lesson.raw_material_text or "") if lesson else ""
        system_prompt = (
            f"You are a warm, patient tutor helping {current_user.name or 'the student'} understand a specific lesson. "
            f"Stay focused on teaching and clarifying this lesson's material — go straight into helping, don't make small talk first. "
            f"Lesson title: {lesson.title if lesson else ''}\n"
            f"Lesson content for your reference:\n{lesson_content[:3000]}"
        )
    else:
        system_prompt = (
            f"You are a friendly, casual conversational companion talking with {current_user.name or 'the student'}. "
            f"Keep things natural and to the point — respond directly to what they say without launching into a lecture "
            f"unless they're clearly asking to learn something. Remember their name is {current_user.name or 'unknown'} and use it naturally."
        )

    try:
        if payload.attachment_url:
            file_path = f"app/static/uploads/{os.path.basename(payload.attachment_url)}"
            reply_text = generate_chat_reply_with_file(history, payload.content, file_path, payload.attachment_mime or "image/jpeg")
        else:
            reply_text = generate_chat_reply(history, payload.content, system_prompt=system_prompt)
    except Exception as e:
        reply_text = f"Sorry, I ran into an error: {e}"

    ai_msg = models.ChatMessage(session_id=session_id, role="model", content=reply_text)
    db.add(ai_msg)

    if session.title == "New Chat":
        session.title = (payload.content[:40] + ("..." if len(payload.content) > 40 else "")) if payload.content else "Image chat"

    db.commit()
    return {"reply": reply_text}