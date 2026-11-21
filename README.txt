EduLearn - Updated Edition

FEATURES
- Admin can add, edit and delete courses.
- Admin can create/delete multiple quizzes for each course.
- Admin can add and delete MCQ and True/False questions.
- Admin can upload MP4, MOV and WebM video files directly (no YouTube required).
- Students can play uploaded videos from the course page.
- Admin can upload and delete PDF notes.
- Existing course/questions database is upgraded automatically on startup.

INSTALLATION (Windows)
1. Install Python 3.10 or newer.
2. Extract this ZIP file.
3. Open Command Prompt in the EduLearn folder.
4. Run: py -m pip install -r requirements.txt
5. Run: py app.py
6. Open: http://127.0.0.1:5000

DEFAULT ADMIN LOGIN
Email: admin@edulearn.local
Password: Admin@123
Change the default password before using this on a public server. Set EDULEARN_SECRET to a long random secret key.

VIDEO STORAGE
Uploaded videos are stored in uploads/videos. The application currently allows files up to 1 GB. Hosting providers may impose a lower request-size limit. MOV playback depends on the browser and the codecs used inside the MOV file; MP4 (H.264/AAC) offers the broadest browser compatibility.

IMPORTANT
This is a local development Flask app. Before public deployment, configure HTTPS, a production WSGI server, a strong secret key, CSRF protection, backups, and appropriate upload limits/storage. Never expose the Flask development server directly to the public internet.
