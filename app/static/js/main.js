// ==========================================
// Base API Helper
// ==========================================
async function apiCall(endpoint, data, method = 'POST') {
    try {
        const options = { method: method, headers: { 'Content-Type': 'application/json' } };
        if (method !== 'DELETE' && method !== 'GET') options.body = JSON.stringify(data);
        const response = await fetch(endpoint, options);
        if (!response.ok) throw new Error('API Error');
        return await response.json();
    } catch (error) {
        alert("Something went wrong. Check your connection!");
        console.error(error);
        return null;
    }
}

let currentUser = null;

async function requireLogin() {
    try {
        const response = await fetch('/me');
        if (!response.ok) throw new Error('Not logged in');
        currentUser = await response.json();
        return currentUser;
    } catch {
        window.location.href = '/login';
        return null;
    }
}

// ==========================================
// Authentication
// ==========================================
async function handleSignup(event) {
    event.preventDefault();
    const form = event.target;
    const data = { name: form.name.value, email: form.email.value, password: form.password.value };
    const result = await apiCall('/signup', data);
    if (result && result.id) window.location.href = '/dashboard';
}

async function handleLogin(event) {
    event.preventDefault();
    const form = event.target;
    const data = { email: form.email.value, password: form.password.value };
    const result = await apiCall('/login', data);
    if (result && result.id) window.location.href = '/dashboard';
}

async function handleLogout(event) {
    if (event) event.preventDefault();
    await fetch('/logout', { method: 'POST' });
    window.location.href = '/login';
}

// ==========================================
// Dashboard
// ==========================================
async function loadSubjects() {
    const user = await requireLogin();
    if (!user) return;
    const userNameElement = document.getElementById('userName');
    if (userNameElement) userNameElement.textContent = user.name || 'there';
    const response = await fetch('/subjects');
    const subjects = await response.json();
    const grid = document.getElementById('subjectGrid');
    if (!grid) return;
    grid.innerHTML = '';
    if (subjects.length === 0) { grid.innerHTML = '<p>No subjects yet. Create one below!</p>'; return; }
    subjects.forEach(sub => {
        const div = document.createElement('div');
        div.className = 'glass-panel';
        div.style.cursor = 'pointer';
        div.innerHTML = `<h3>${sub.name}</h3>`;
        div.onclick = () => window.location.href = `/subject?id=${sub.id}`;
        grid.appendChild(div);
    });
}

async function createSubject(event) {
    event.preventDefault();
    const input = document.getElementById('newSubjectName');
    const result = await apiCall('/subjects', { name: input.value });
    if (result) { input.value = ''; loadSubjects(); }
}

async function loadRecentLessons() {
    const user = await requireLogin();
    if (!user) return;
    const grid = document.getElementById('recentLessonsGrid');
    if (!grid) return;
    const response = await fetch('/lessons/recent');
    const lessons = await response.json();
    grid.innerHTML = '';
    if (lessons.length === 0) { grid.innerHTML = '<p>No lessons yet. Create a subject and add your first lesson!</p>'; return; }
    lessons.forEach(lesson => {
        const div = document.createElement('div');
        div.className = 'glass-panel';
        div.style.cursor = 'pointer';
        div.innerHTML = `<h3>${lesson.title}</h3><p style="opacity: 0.7; margin-top: 0.25rem;">${lesson.subject_name}</p>`;
        div.onclick = () => window.location.href = `/lesson?id=${lesson.id}`;
        grid.appendChild(div);
    });
}

async function loadInProgressLessons() {
    const user = await requireLogin();
    if (!user) return;
    const section = document.getElementById('inProgressSection');
    const grid = document.getElementById('inProgressGrid');
    if (!grid || !section) return;
    const response = await fetch('/lessons/in-progress');
    const lessons = await response.json();
    if (lessons.length === 0) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    grid.innerHTML = '';
    lessons.forEach(lesson => {
        const div = document.createElement('div');
        div.className = 'glass-panel';
        div.style.cursor = 'pointer';
        div.innerHTML = `<h3>▶ ${lesson.title}</h3><p style="opacity: 0.7; margin-top: 0.25rem;">${lesson.subject_name}</p>`;
        div.onclick = () => window.location.href = `/lesson?id=${lesson.id}`;
        grid.appendChild(div);
    });
}

// ==========================================
// Subject Page
// ==========================================
async function loadLessons() {
    const user = await requireLogin();
    if (!user) return;
    const urlParams = new URLSearchParams(window.location.search);
    const subjectId = urlParams.get('id');
    if (!subjectId) return;
    const response = await fetch(`/subjects/${subjectId}/lessons`);
    const lessons = await response.json();
    const grid = document.getElementById('lessonGrid');
    if (!grid) return;
    grid.innerHTML = '';
    if (lessons.length === 0) { grid.innerHTML = '<p>No lessons yet. Paste some material below to generate one!</p>'; return; }
    lessons.forEach(lesson => {
        const div = document.createElement('div');
        div.className = 'glass-panel';
        div.style.cursor = 'pointer';
        div.innerHTML = `<h3>${lesson.title}</h3>`;
        div.onclick = () => window.location.href = `/lesson?id=${lesson.id}`;
        grid.appendChild(div);
    });
}

async function createLesson(event) {
    event.preventDefault();
    const urlParams = new URLSearchParams(window.location.search);
    const subjectId = urlParams.get('id');
    const form = event.target;
    const btn = document.getElementById('generateBtn');
    btn.textContent = 'Generating Lesson...';
    btn.style.opacity = '0.7';
    btn.disabled = true;
    const result = await apiCall('/lessons', { title: form.title.value, subject_id: parseInt(subjectId), raw_material_text: form.raw_material.value });
    if (result) { form.reset(); loadLessons(); }
    btn.textContent = 'Generate Lesson';
    btn.style.opacity = '1';
    btn.disabled = false;
}

// ==========================================
// Lesson Page (with progress tracking)
// ==========================================
let progressSaveTimeout = null;

async function loadSingleLesson() {
    const user = await requireLogin();
    if (!user) return;
    const urlParams = new URLSearchParams(window.location.search);
    const lessonId = urlParams.get('id');
    if (!lessonId) return;
    const contentDiv = document.getElementById('lessonContent');
    if (!contentDiv) return;
    try {
        const response = await fetch(`/lessons/${lessonId}`);
        if (!response.ok) throw new Error('Lesson not found');
        const lesson = await response.json();
        document.getElementById('lessonTitle').textContent = lesson.title;
        contentDiv.innerHTML = lesson.content;

        const badge = document.getElementById('completedBadge');
        const completeBtn = document.getElementById('markCompleteBtn');
        if (lesson.completed) {
            if (badge) badge.style.display = 'inline-block';
            if (completeBtn) { completeBtn.textContent = '✓ Completed'; completeBtn.disabled = true; }
        }

        if (lesson.last_position && !lesson.completed) {
            setTimeout(() => {
                const scrollY = parseFloat(lesson.last_position) * document.body.scrollHeight;
                window.scrollTo({ top: scrollY, behavior: 'smooth' });
            }, 300);
        }

        window.addEventListener('scroll', () => {
            if (progressSaveTimeout) clearTimeout(progressSaveTimeout);
            progressSaveTimeout = setTimeout(() => saveScrollProgress(lessonId), 1500);
        });
    } catch (error) {
        contentDiv.innerHTML = '<p>Failed to load this lesson. Please try again.</p>';
        console.error(error);
    }
}

async function saveScrollProgress(lessonId) {
    const scrollableHeight = document.body.scrollHeight - window.innerHeight;
    if (scrollableHeight <= 0) return;
    const scrollPercent = Math.min(window.scrollY / scrollableHeight, 1).toFixed(3);
    await fetch(`/lessons/${lessonId}/progress`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ last_position: scrollPercent })
    });
}

async function markLessonComplete(lessonId) {
    const result = await fetch(`/lessons/${lessonId}/progress`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ completed: true })
    });
    if (result.ok) {
        document.getElementById('completedBadge').style.display = 'inline-block';
        const btn = document.getElementById('markCompleteBtn');
        btn.textContent = '✓ Completed';
        btn.disabled = true;
    }
}

// ==========================================
// Progress Page (XP / Levels)
// ==========================================
async function loadProgressOverview() {
    const user = await requireLogin();
    if (!user) return;

    const container = document.getElementById('progressList');
    if (!container) return;

    const response = await fetch('/progress/overview');
    const data = await response.json();
    const lessons = data.lessons;

    const levelLabel = document.getElementById('levelLabel');
    const xpLabel = document.getElementById('xpLabel');
    const xpFill = document.getElementById('xpProgressFill');
    const xpToNextText = document.getElementById('xpToNextText');
    const encouragementText = document.getElementById('encouragementText');

    if (levelLabel) levelLabel.textContent = `Level ${data.level}`;
    if (xpLabel) xpLabel.textContent = `${data.total_xp} XP total`;
    if (xpFill) xpFill.style.width = `${data.percent_to_next_level}%`;
    if (xpToNextText) xpToNextText.textContent = `${data.xp_into_level} / ${data.xp_needed_for_next} XP to Level ${data.level + 1}`;
    if (encouragementText) encouragementText.textContent = getEncouragementMessage(data.level, user.name);

    container.innerHTML = '';

    if (lessons.length === 0) {
        container.innerHTML = '<p>No lessons yet. Create one to start earning XP!</p>';
        return;
    }

    lessons.forEach(lesson => {
        const div = document.createElement('div');
        div.className = 'glass-panel';

        const statusBadge = lesson.completed
            ? '<span style="font-size: 0.8rem; padding: 0.2rem 0.6rem; border-radius: 12px; background: rgba(74,222,128,0.2); color: #4ade80;">✓ Completed</span>'
            : '<span style="font-size: 0.8rem; opacity: 0.6;">In progress</span>';

        let quizHtml = '';
        if (lesson.quizzes.length > 0) {
            quizHtml = '<div style="margin-top: 0.75rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">';
            lesson.quizzes.forEach(q => {
                const color = q.score >= 70 ? '#4ade80' : q.score >= 40 ? '#facc15' : '#f87171';
                quizHtml += `<span style="font-size: 0.8rem; padding: 0.2rem 0.6rem; border-radius: 12px; background: rgba(255,255,255,0.08); color: ${color};">${q.difficulty}: ${q.score}%</span>`;
            });
            quizHtml += '</div>';
        }

        div.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                <div>
                    <h3>${lesson.title}</h3>
                    <p style="margin-bottom: 0; opacity: 0.7; font-size: 0.85rem;">${lesson.subject_name} · +${lesson.xp_earned} XP earned</p>
                </div>
                ${statusBadge}
            </div>
            ${quizHtml}
        `;
        div.style.cursor = 'pointer';
        div.onclick = () => window.location.href = `/lesson?id=${lesson.id}`;
        container.appendChild(div);
    });
}

function getEncouragementMessage(level, name) {
    const who = name || 'there';
    if (level === 1) return `Every expert starts at Level 1, ${who} — let's go! 🚀`;
    if (level < 3) return `Level ${level} already, ${who}! Keep the momentum going. 🌱`;
    if (level < 5) return `Level ${level}, ${who} — you're building real mastery! 💪`;
    if (level < 8) return `Level ${level}! Seriously impressive dedication, ${who}. ⭐`;
    return `Level ${level}?! You're unstoppable, ${who}. 🏆`;
}

// ==========================================
// Timetable
// ==========================================
let notifiedEntriesToday = new Set();

function initTimetableNotifications(entries) {
    if (!("Notification" in window)) {
        console.warn("This browser doesn't support notifications.");
        return;
    }

    console.log("Notification permission status:", Notification.permission);

    if (Notification.permission === "default") {
        Notification.requestPermission().then(perm => {
            console.log("Notification permission result:", perm);
        });
    }

    if (Notification.permission === "denied") {
        console.warn("Notifications are blocked for this site. Check browser site settings.");
    }

    setInterval(() => {
        if (Notification.permission !== "granted") return;

        const now = new Date();
        const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        const currentDay = dayNames[now.getDay()];
        const currentTime = now.toTimeString().slice(0, 5);

        entries.forEach(entry => {
            const key = `${entry.id}-${now.toDateString()}`;
            if (entry.day_of_week === currentDay && entry.start_time === currentTime && !notifiedEntriesToday.has(key)) {
                notifiedEntriesToday.add(key);
                new Notification("📚 G-Zia Learning Space", {
                    body: `Time for: ${entry.title}${entry.subject_name ? ' (' + entry.subject_name + ')' : ''}`,
                });
            }
        });
    }, 10000);
}

async function loadTimetable() {
    const user = await requireLogin();
    if (!user) return;
    const grid = document.getElementById('timetableGrid');
    if (!grid) return;
    const response = await fetch('/api/timetable');
    const entries = await response.json();
    initTimetableNotifications(entries);
    grid.innerHTML = '';
    if (entries.length === 0) { grid.innerHTML = '<p>No study periods scheduled yet. Add one below!</p>'; return; }
    const dayOrder = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
    entries.sort((a, b) => dayOrder.indexOf(a.day_of_week) - dayOrder.indexOf(b.day_of_week) || a.start_time.localeCompare(b.start_time));
    entries.forEach(entry => {
        const div = document.createElement('div');
        div.className = 'glass-panel';
        div.style.display = 'flex';
        div.style.justifyContent = 'space-between';
        div.style.alignItems = 'center';
        div.innerHTML = `
            <div>
                <strong>${entry.day_of_week}</strong> · ${entry.start_time}–${entry.end_time}<br>
                <span>${entry.title}${entry.subject_name ? ' (' + entry.subject_name + ')' : ''}</span>
            </div>
            <button onclick="deleteTimetableEntry(${entry.id})" style="width: auto; padding: 0.4rem 0.8rem; opacity: 0.7;">Delete</button>
        `;
        grid.appendChild(div);
    });
}

async function createTimetableEntry(event) {
    event.preventDefault();
    const form = event.target;
    const result = await apiCall('/api/timetable', { subject_id: null, title: form.title.value, day_of_week: form.day_of_week.value, start_time: form.start_time.value, end_time: form.end_time.value });
    if (result) { form.reset(); loadTimetable(); }
}

async function deleteTimetableEntry(entryId) {
    await apiCall(`/api/timetable/${entryId}`, null, 'DELETE');
    loadTimetable();
}

// ==========================================
// Quiz
// ==========================================
async function generateQuiz(lessonId, difficulty, btn) {
    const originalText = btn.textContent;
    btn.textContent = 'Generating...';
    btn.disabled = true;
    const result = await apiCall(`/lessons/${lessonId}/quiz`, { difficulty });
    btn.textContent = originalText;
    btn.disabled = false;
    if (result && result.id) window.location.href = `/quiz?quiz_id=${result.id}`;
}

let quizData = null;
let quizAnswers = {};

async function loadQuiz() {
    const user = await requireLogin();
    if (!user) return;
    const urlParams = new URLSearchParams(window.location.search);
    const quizId = urlParams.get('quiz_id');
    if (!quizId) return;
    const container = document.getElementById('quizContainer');
    try {
        const response = await fetch(`/quizzes/${quizId}`);
        if (!response.ok) throw new Error('Quiz not found');
        quizData = await response.json();
        renderQuiz();
    } catch (err) {
        container.innerHTML = '<p>Failed to load quiz.</p>';
        console.error(err);
    }
}

function renderQuiz() {
    const container = document.getElementById('quizContainer');
    quizAnswers = {};
    let html = `<h2>${quizData.lesson_title} — ${quizData.difficulty} quiz</h2>`;
    quizData.questions.forEach((q, qIndex) => {
        html += `<div class="quiz-question" data-qindex="${qIndex}"><p style="color: var(--text-main); font-weight: 600;">${qIndex + 1}. ${q.question}</p>`;
        q.options.forEach((opt, oIndex) => {
            html += `<div class="quiz-option" data-qindex="${qIndex}" data-oindex="${oIndex}" onclick="selectQuizOption(${qIndex}, ${oIndex})">${opt}</div>`;
        });
        html += `<div class="quiz-explanation" style="display: none;" id="explain-${qIndex}"></div></div>`;
    });
    html += `<button id="submitQuizBtn" onclick="submitQuiz()">Submit Quiz</button>`;
    container.innerHTML = html;
}

function selectQuizOption(qIndex, oIndex) {
    quizAnswers[qIndex] = oIndex;
    document.querySelectorAll(`.quiz-option[data-qindex="${qIndex}"]`).forEach(el => {
        el.classList.toggle('selected', parseInt(el.dataset.oindex) === oIndex);
    });
}

async function submitQuiz() {
    let correctCount = 0;
    quizData.questions.forEach((q, qIndex) => {
        const selected = quizAnswers[qIndex];
        const options = document.querySelectorAll(`.quiz-option[data-qindex="${qIndex}"]`);
        options.forEach(el => {
            const oIndex = parseInt(el.dataset.oindex);
            if (oIndex === q.correct_index) el.classList.add('correct');
            else if (oIndex === selected) el.classList.add('incorrect');
        });
        const explainEl = document.getElementById(`explain-${qIndex}`);
        explainEl.style.display = 'block';
        explainEl.textContent = q.explanation;
        if (selected === q.correct_index) correctCount++;
    });
    const scorePercent = Math.round((correctCount / quizData.questions.length) * 100);
    document.getElementById('submitQuizBtn').style.display = 'none';
    const container = document.getElementById('quizContainer');
    const scoreDiv = document.createElement('div');
    scoreDiv.className = 'quiz-score';
    scoreDiv.innerHTML = `<h2>${scorePercent}%</h2><p>${correctCount} out of ${quizData.questions.length} correct</p>`;
    container.appendChild(scoreDiv);
    await apiCall(`/quizzes/${quizData.id}/submit`, { score: scorePercent });
}

// ==========================================
// Chat
// ==========================================
let currentChatSessionId = null;
let pendingAttachment = null;

async function initChatPage() {
    const user = await requireLogin();
    if (!user) return;

    const fileInput = document.getElementById('fileInput');
    if (fileInput) fileInput.addEventListener('change', handleFileSelected);

    const urlParams = new URLSearchParams(window.location.search);
    const lessonId = urlParams.get('lesson_id');
    const sessionId = urlParams.get('session_id');

    if (lessonId) {
        const result = await apiCall('/chats', { lesson_id: parseInt(lessonId) });
        if (result) openChatSession(result.id);
        return;
    }
    if (sessionId) { openChatSession(parseInt(sessionId)); return; }

    const result = await apiCall('/chats', {});
    if (result) openChatSession(result.id);
}

async function handleFileSelected(event) {
    const file = event.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
        const response = await fetch('/uploads', { method: 'POST', body: formData });
        if (!response.ok) { const err = await response.json(); alert(err.detail || 'Upload failed'); return; }
        const result = await response.json();
        pendingAttachment = { url: result.url, mimeType: result.mime_type, name: file.name };
        const preview = document.getElementById('attachmentPreview');
        document.getElementById('attachmentPreviewName').textContent = `📎 ${file.name}`;
        preview.classList.add('visible');
    } catch (err) {
        console.error(err);
        alert('Upload failed. Check your connection.');
    }
    event.target.value = '';
}

function clearPendingAttachment() {
    pendingAttachment = null;
    document.getElementById('attachmentPreview').classList.remove('visible');
}

async function openChatSession(sessionId) {
    currentChatSessionId = sessionId;
    const response = await fetch(`/chats/${sessionId}/messages`);
    const messages = await response.json();
    const container = document.getElementById('chatMessages');
    container.innerHTML = '';
    if (messages.length === 0) {
        container.innerHTML = '<div class="chat-empty-state"><h3>👋 Ask me anything</h3><p>Start the conversation below.</p></div>';
        return;
    }
    messages.forEach(msg => appendChatBubble(msg.role, msg.content, msg.attachment_url));
    container.scrollTop = container.scrollHeight;
}

function renderMarkdown(text) {
    if (typeof marked !== 'undefined') return marked.parse(text);
    return text;
}

function appendChatBubble(role, content, attachmentUrl = null) {
    const container = document.getElementById('chatMessages');
    const emptyState = container.querySelector('.chat-empty-state');
    if (emptyState) emptyState.remove();

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${role}`;

    let html = '';
    if (attachmentUrl) {
        if (attachmentUrl.match(/\.(png|jpe?g|webp|heic)$/i)) html += `<img src="${attachmentUrl}" alt="attachment">`;
        else html += `<div class="file-chip">📎 ${attachmentUrl.split('/').pop()}</div>`;
    }
    if (content) html += role === 'model' ? renderMarkdown(content) : content;
    bubble.innerHTML = html;

    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
    return bubble;
}

async function sendChatMessage(event) {
    event.preventDefault();
    if (!currentChatSessionId) {
        const result = await apiCall('/chats', {});
        if (!result) return;
        currentChatSessionId = result.id;
    }

    const input = document.getElementById('chatTextInput');
    const text = input.value.trim();
    if (!text && !pendingAttachment) return;

    appendChatBubble('user', text, pendingAttachment?.url);
    input.value = '';

    const attachmentToSend = pendingAttachment;
    clearPendingAttachment();

    const container = document.getElementById('chatMessages');
    const typingEl = document.createElement('div');
    typingEl.className = 'typing-indicator';
    typingEl.id = 'typingIndicator';
    typingEl.textContent = 'Thinking...';
    container.appendChild(typingEl);
    container.scrollTop = container.scrollHeight;

    const result = await apiCall(`/chats/${currentChatSessionId}/messages`, {
        content: text,
        attachment_url: attachmentToSend?.url || null,
        attachment_mime: attachmentToSend?.mimeType || null,
    });

    document.getElementById('typingIndicator')?.remove();

    if (result && result.reply) appendChatBubble('model', result.reply);
    else appendChatBubble('model', 'Sorry, something went wrong. Please try again.');
}