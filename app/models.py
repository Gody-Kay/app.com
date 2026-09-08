from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    subjects = relationship("Subject", back_populates="owner")


class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="subjects")
    lessons = relationship("Lesson", back_populates="subject")


class Lesson(Base):
    __tablename__ = "lessons"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    raw_material_text = Column(Text, nullable=True)
    ai_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    subject = relationship("Subject", back_populates="lessons")
    progress = relationship("Progress", back_populates="lesson", uselist=False)
    quizzes = relationship("Quiz", back_populates="lesson")


class Progress(Base):
    __tablename__ = "progress"
    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"))
    last_position = Column(String, nullable=True)
    completed = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow)

    lesson = relationship("Lesson", back_populates="progress")


class Quiz(Base):
    __tablename__ = "quizzes"
    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"))
    difficulty = Column(String, nullable=False)
    questions_json = Column(Text, nullable=False)
    score = Column(Integer, nullable=True)
    taken_at = Column(DateTime, default=datetime.utcnow)

    lesson = relationship("Lesson", back_populates="quizzes")


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True)
    title = Column(String, nullable=False)
    day_of_week = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)

    owner = relationship("User")
    subject = relationship("Subject")


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=True)
    title = Column(String, nullable=False, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User")
    lesson = relationship("Lesson")
    messages = relationship("ChatMessage", back_populates="session", order_by="ChatMessage.created_at")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"))
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    attachment_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")