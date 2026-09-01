from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import smtplib
import sqlite3
import time
from datetime import date, datetime, timezone
from email.message import EmailMessage
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ssl
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
DB_DIR = ROOT / "data"
DB_PATH = DB_DIR / "masala_junction.sqlite"
ALLOWED_STATUSES = {"pending", "confirmed", "cancelled", "completed"}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GMAIL_ADDRESS_ENV = "MJ_GMAIL_ADDRESS"
GMAIL_APP_PASSWORD_ENV = "MJ_GMAIL_APP_PASSWORD"
GMAIL_FROM_NAME_ENV = "MJ_GMAIL_FROM_NAME"
ADMIN_PASSWORD_ENV = "MJ_ADMIN_PASSWORD"
SESSION_SECRET_ENV = "MJ_SESSION_SECRET"
COOKIE_SECURE_ENV = "MJ_COOKIE_SECURE"
SESSION_COOKIE_NAME = "mj_admin_session"
SESSION_DURATION_SECONDS = 8 * 60 * 60
MAX_REQUEST_BODY_BYTES = 8 * 1024
PUBLIC_RESERVATION_LIMIT = 5
PUBLIC_RESERVATION_WINDOW_SECONDS = 10 * 60
ADMIN_LOGIN_LIMIT = 5
ADMIN_LOGIN_WINDOW_SECONDS = 15 * 60


def load_local_env_file() -> None:
    """Populate missing environment variables from a local .env file."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


load_local_env_file()

# A configured secret keeps sessions valid across restarts. A generated secret is
# safe for local use but intentionally signs everyone out when the server restarts.
SESSION_SECRET = os.environ.get(SESSION_SECRET_ENV, "").encode("utf-8") or secrets.token_bytes(32)
PUBLIC_RESERVATION_ATTEMPTS: dict[str, list[float]] = {}
ADMIN_LOGIN_ATTEMPTS: dict[str, list[float]] = {}


def get_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT DEFAULT '',
                reservation_date TEXT NOT NULL,
                reservation_time TEXT NOT NULL,
                guests TEXT NOT NULL,
                note TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(reservations)").fetchall()
        }
        if "email" not in columns:
            connection.execute("ALTER TABLE reservations ADD COLUMN email TEXT DEFAULT ''")
        connection.commit()


def row_to_reservation(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "phone": row["phone"],
        "email": row["email"] or "",
        "date": row["reservation_date"],
        "time": row["reservation_time"],
        "guests": row["guests"],
        "note": row["note"] or "",
        "status": row["status"],
        "createdAt": row["created_at"],
    }


def build_confirmation_message(reservation: dict) -> str:
    return (
        f"Hi {reservation['name']},\n\n"
        "Your Masala Junction table reservation is confirmed.\n\n"
        f"Date: {reservation['date']}\n"
        f"Time: {reservation['time']}\n"
        f"Guests: {reservation['guests']}\n\n"
        "Thank you,\n"
        "Masala Junction"
    )


def normalize_phone_number(value: str) -> str | None:
    """Return an E.164 number suitable for SMS, accepting common Indian input."""
    compact = re.sub(r"[\s().-]", "", value)
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    if compact.startswith("+"):
        digits = compact[1:]
        if digits.isdigit() and 8 <= len(digits) <= 15:
            return f"+{digits}"
        return None
    if compact.isdigit() and len(compact) == 10 and compact[0] in "6789":
        return f"+91{compact}"
    return None


def send_confirmation_email(reservation: dict) -> dict:
    if not reservation["email"]:
        return {
            "channel": "email",
            "status": "skipped",
            "reason": "no_email",
            "message": "Customer email is not available.",
        }

    gmail_address = os.environ.get(GMAIL_ADDRESS_ENV, "").strip()
    gmail_app_password = re.sub(r"\s+", "", os.environ.get(GMAIL_APP_PASSWORD_ENV, ""))
    from_name = os.environ.get(GMAIL_FROM_NAME_ENV, "Masala Junction").strip()

    if not gmail_address or not gmail_app_password:
        return {
            "channel": "email",
            "status": "not_configured",
            "message": "Gmail is not configured on the server.",
        }

    message = EmailMessage()
    message["Subject"] = f"Reservation #{reservation['id']} confirmed"
    message["From"] = f"{from_name} <{gmail_address}>"
    message["To"] = reservation["email"]
    message.set_content(build_confirmation_message(reservation))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
            smtp.login(gmail_address, gmail_app_password)
            smtp.send_message(message)
    except Exception as error:
        print(f"Gmail confirmation failed for reservation #{reservation['id']}: {error}")
        return {
            "channel": "email",
            "status": "error",
            "message": "Email confirmation could not be sent.",
        }

    return {
        "channel": "email",
        "status": "sent",
        "message": "Email confirmation sent.",
    }


def send_confirmation_notifications(reservation: dict) -> list[dict]:
    return [send_confirmation_email(reservation)]


def create_session_value() -> str:
    expires_at = int(time.time()) + SESSION_DURATION_SECONDS
    payload = str(expires_at).encode("ascii")
    signature = hmac.new(SESSION_SECRET, payload, hashlib.sha256).hexdigest()
    return f"{expires_at}.{signature}"


def is_valid_session(value: str | None) -> bool:
    if not value or "." not in value:
        return False
    expires_at, signature = value.rsplit(".", 1)
    if not expires_at.isdigit() or int(expires_at) < int(time.time()):
        return False
    expected = hmac.new(SESSION_SECRET, expires_at.encode("ascii"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def validate_reservation(payload: dict) -> tuple[dict | None, str | None]:
    name = str(payload.get("name", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    email = str(payload.get("email", "")).strip()
    reservation_date = str(payload.get("date", "")).strip()
    reservation_time = str(payload.get("time", "")).strip()
    guests = str(payload.get("guests", "")).strip()
    note = str(payload.get("note", "")).strip()

    if not name or not phone or not reservation_date or not reservation_time or not guests:
        return None, "Please fill all required reservation fields."

    if len(name) > 80:
        return None, "Name is too long."

    if not normalize_phone_number(phone):
        return None, "Please enter a valid mobile number, including country code if it is outside India."

    if email:
        if len(email) > 120:
            return None, "Email address is too long."
        if not EMAIL_PATTERN.match(email):
            return None, "Please enter a valid email address."

    try:
        parsed_date = date.fromisoformat(reservation_date)
    except ValueError:
        return None, "Please choose a valid date."

    if parsed_date < date.today():
        return None, "Please choose today or a future date."

    try:
        parsed_time = datetime.strptime(reservation_time, "%H:%M").time()
    except ValueError:
        return None, "Please choose a valid time."

    opening = datetime.strptime("11:00", "%H:%M").time()
    closing = datetime.strptime("23:00", "%H:%M").time()
    if parsed_time < opening or parsed_time > closing:
        return None, "Reservations are available between 11:00 AM and 11:00 PM."

    if guests not in {"1", "2", "3", "4", "5", "6+"}:
        return None, "Please choose the number of guests."

    return {
        "name": name,
        "phone": phone,
        "email": email,
        "date": reservation_date,
        "time": reservation_time,
        "guests": guests,
        "note": note[:500],
    }, None


class MasalaJunctionHandler(SimpleHTTPRequestHandler):
    server_version = "MasalaJunctionHTTP/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        if urlparse(self.path).path in {"/admin", "/admin.html", "/login", "/login.html"}:
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> tuple[dict | None, str | None]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None, "Invalid request body."
        if length > MAX_REQUEST_BODY_BYTES:
            return None, "Request is too large."
        if length <= 0:
            return {}, None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "Invalid JSON body."
        if not isinstance(payload, dict):
            return None, "JSON body must be an object."
        return payload, None

    def client_ip(self) -> str:
        return self.client_address[0]

    def is_rate_limited(self, attempts: dict[str, list[float]], limit: int, window: int) -> bool:
        now = time.monotonic()
        client_attempts = [attempt for attempt in attempts.get(self.client_ip(), []) if now - attempt < window]
        attempts[self.client_ip()] = client_attempts
        if len(client_attempts) >= limit:
            return True
        return False

    def record_attempt(self, attempts: dict[str, list[float]]) -> None:
        attempts.setdefault(self.client_ip(), []).append(time.monotonic())

    def session_value(self) -> str | None:
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            morsel = cookies.get(SESSION_COOKIE_NAME)
            return morsel.value if morsel else None
        except (KeyError, ValueError):
            return None

    def is_authenticated(self) -> bool:
        return is_valid_session(self.session_value())

    def require_admin(self) -> bool:
        if self.is_authenticated():
            return True
        self.send_json(401, {"error": "Admin sign-in is required."})
        return False

    def send_session_cookie(self, value: str | None = None) -> None:
        parts = [f"{SESSION_COOKIE_NAME}={value or ''}", "Path=/", "HttpOnly", "SameSite=Strict"]
        if value:
            parts.append(f"Max-Age={SESSION_DURATION_SECONDS}")
        else:
            parts.append("Max-Age=0")
        if os.environ.get(COOKIE_SECURE_ENV, "true").strip().lower() not in {"0", "false", "no"}:
            parts.append("Secure")
        self.send_header("Set-Cookie", "; ".join(parts))

    def send_redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def is_private_path(self, path: str) -> bool:
        filename = Path(path).name.lower()
        return (
            path == "/data"
            or path.startswith("/data/")
            or filename.startswith(".")
            or filename.endswith((".py", ".sqlite", ".db", ".env"))
        )

    def is_static_asset_path(self, path: str) -> bool:
        return path in {
            "/",
            "/index.html",
            "/style.css",
            "/script.js",
            "/admin.html",
            "/admin.js",
            "/login.html",
            "/login.js",
        } or path.startswith("/assets/")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/reservations":
            if not self.require_admin():
                return
            with get_connection() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM reservations
                    ORDER BY reservation_date ASC, reservation_time ASC, created_at DESC
                    """
                ).fetchall()
            self.send_json(200, {"reservations": [row_to_reservation(row) for row in rows]})
            return

        if path == "/api/admin/session":
            self.send_json(200, {"authenticated": self.is_authenticated()})
            return

        if path in {"/admin", "/admin.html"}:
            if not self.is_authenticated():
                self.send_redirect("/login")
                return
            self.path = "/admin.html"

        if path in {"/login", "/login.html"}:
            if self.is_authenticated():
                self.send_redirect("/admin")
                return
            self.path = "/login.html"

        path = urlparse(self.path).path
        if self.is_private_path(path):
            self.send_error(404)
            return

        if not self.is_static_asset_path(path):
            self.send_error(404)
            return

        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/admin/login":
            if self.is_rate_limited(ADMIN_LOGIN_ATTEMPTS, ADMIN_LOGIN_LIMIT, ADMIN_LOGIN_WINDOW_SECONDS):
                self.send_json(429, {"error": "Too many sign-in attempts. Please try again later."})
                return
            payload, error = self.read_json()
            if error:
                self.send_json(400, {"error": error})
                return
            configured_password = os.environ.get(ADMIN_PASSWORD_ENV, "")
            password = str(payload.get("password", ""))
            if not configured_password:
                self.send_json(503, {"error": "Admin sign-in has not been configured on the server."})
                return
            if not hmac.compare_digest(password, configured_password):
                self.record_attempt(ADMIN_LOGIN_ATTEMPTS)
                self.send_json(401, {"error": "Incorrect password."})
                return
            ADMIN_LOGIN_ATTEMPTS.pop(self.client_ip(), None)
            self.send_response(204)
            self.send_session_cookie(create_session_value())
            self.end_headers()
            return

        if path == "/api/admin/logout":
            if not self.require_admin():
                return
            self.send_response(204)
            self.send_session_cookie()
            self.end_headers()
            return

        if path == "/api/reservations":
            if self.is_rate_limited(
                PUBLIC_RESERVATION_ATTEMPTS,
                PUBLIC_RESERVATION_LIMIT,
                PUBLIC_RESERVATION_WINDOW_SECONDS,
            ):
                self.send_json(429, {"error": "Too many reservation requests. Please try again later."})
                return
            self.record_attempt(PUBLIC_RESERVATION_ATTEMPTS)
            payload, error = self.read_json()
            if error:
                self.send_json(400, {"error": error})
                return

            reservation, error = validate_reservation(payload)
            if error:
                self.send_json(400, {"error": error})
                return

            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with get_connection() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO reservations
                        (name, phone, email, reservation_date, reservation_time, guests, note, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        reservation["name"],
                        reservation["phone"],
                        reservation["email"],
                        reservation["date"],
                        reservation["time"],
                        reservation["guests"],
                        reservation["note"],
                        created_at,
                    ),
                )
                connection.commit()
                row = connection.execute(
                    "SELECT * FROM reservations WHERE id = ?",
                    (cursor.lastrowid,),
                ).fetchone()

            self.send_json(201, {"reservation": row_to_reservation(row)})
            return

        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "reservations"] and parts[3] == "confirmations":
            if not self.require_admin():
                return
            try:
                reservation_id = int(parts[2])
            except ValueError:
                self.send_json(400, {"error": "Invalid reservation id."})
                return
            with get_connection() as connection:
                row = connection.execute(
                    "SELECT * FROM reservations WHERE id = ?", (reservation_id,)
                ).fetchone()
            if row is None:
                self.send_json(404, {"error": "Reservation not found."})
                return
            reservation = row_to_reservation(row)
            if reservation["status"] != "confirmed":
                self.send_json(409, {"error": "Approve the reservation before sending a confirmation."})
                return
            self.send_json(200, {"reservation": reservation, "notifications": send_confirmation_notifications(reservation)})
            return

        self.send_error(404)
        return

    def do_PATCH(self) -> None:
        if not self.require_admin():
            return
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["api", "reservations"]:
            self.send_error(404)
            return

        try:
            reservation_id = int(parts[2])
        except ValueError:
            self.send_json(400, {"error": "Invalid reservation id."})
            return

        payload, error = self.read_json()
        if error:
            self.send_json(400, {"error": error})
            return

        status = str(payload.get("status", "")).strip().lower()
        if status not in ALLOWED_STATUSES:
            self.send_json(400, {"error": "Invalid reservation status."})
            return

        notifications = []
        with get_connection() as connection:
            existing_row = connection.execute(
                "SELECT * FROM reservations WHERE id = ?",
                (reservation_id,),
            ).fetchone()

            if existing_row is None:
                self.send_json(404, {"error": "Reservation not found."})
                return

            connection.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM reservations WHERE id = ?",
                (reservation_id,),
            ).fetchone()

        reservation = row_to_reservation(row)
        if status == "confirmed" and existing_row["status"] != "confirmed":
            notifications = send_confirmation_notifications(reservation)

        response = {"reservation": reservation}
        if notifications:
            response["notifications"] = notifications
        self.send_json(200, response)


def main() -> None:
    init_db()
    mimetypes.add_type("text/javascript", ".js")
    server = ThreadingHTTPServer(("localhost", 8000), MasalaJunctionHandler)
    print("Masala Junction backend running at http://localhost:8000")
    print(f"SQLite database: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
