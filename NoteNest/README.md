# NoteNest — Student Notes Sharing Portal

A small Flask + SQLite web app where students can upload PDF notes, search by title/subject/unit, filter by subject and semester, and download notes.

## Features
- Responsive green-and-white UI
- Upload PDF notes with title, subject, semester, and unit
- Search and filter uploaded notes
- Download notes
- Account registration and login
- Delete only notes uploaded by your own account
- SQLite metadata storage
- 15 MB upload limit and PDF-only extension check

## Run locally (Windows PowerShell)

1. Install Python 3.10+.
2. Open this folder in VS Code.
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

5. Start the app:

   ```powershell
   python app.py
   ```

6. Open `http://127.0.0.1:5000` in your browser.

## Suggested DevOps extension
1. Push the code to GitHub.
2. Add automated tests for the upload/search/download features.
3. Configure Jenkins to install dependencies and run tests on each push.
4. Add an Ansible playbook to deploy the app to a Linux test server.
5. Optionally use Azure DevOps Pipelines as an alternative CI pipeline.

## Notes
This is a learning/demo starter, not a production-ready public file-sharing service. Before exposing it publicly, add authentication and authorization, validate actual PDF file contents, add malware scanning and rate limits, use a production WSGI server, configure secrets securely, and review copyright/privacy requirements.
Jenkins CI pipeline verified
Testing automatic Jenkins build.

Jenkins CI/CD: Testing automatic deployment with Ansible on Ubuntu VMware.
