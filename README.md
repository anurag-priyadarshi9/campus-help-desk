# Campus Help Desk

Students file complaints and follow them; staff reply and change the status.

**Stack:** HTML/CSS/JavaScript frontend, Python (Flask) backend, SQLite database.

## Run it

```
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

The database file `helpdesk.db` is created on first run.

## Logins

- Student: use **Create account** on the home page.
- Staff (seeded):

## Project layout

```
app.py            Flask API + SQLite schema
static/index.html Page markup
static/style.css  Styles
static/app.js     Frontend logic (fetch calls to /api)
```

## API

| Method | Path | Who |
|---|---|---|
| POST | /api/register, /api/login, /api/logout | anyone |
| GET | /api/me, /api/meta | anyone |
| GET, POST | /api/tickets | logged in (students see only their own) |
| GET | /api/tickets/<id> | owner or staff |
| POST | /api/tickets/<id>/replies | owner or staff |
| PATCH | /api/tickets/<id> (status) | staff |
| GET | /api/stats | staff |

## Before deploying

Set a real `SECRET_KEY` environment variable and run behind a production server (for example gunicorn) instead of `debug=True`.
