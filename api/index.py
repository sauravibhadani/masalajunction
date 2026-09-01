"""Vercel serverless API. Configure Supabase and Gmail settings in Vercel."""
from __future__ import annotations
import hashlib, hmac, json, os, re, smtplib, ssl, time
from datetime import date, datetime, timezone
from email.message import EmailMessage
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STATUSES = {"pending", "confirmed", "cancelled", "completed"}
COOKIE = "mj_admin_session"; SESSION_SECONDS = 28800; MAX_BODY = 8192
ATTEMPTS: dict[str, list[float]] = {}

def secret(): return os.environ.get("MJ_SESSION_SECRET", "").encode()
def row(r): return {"id":r["id"],"name":r["name"],"phone":r["phone"],"email":r.get("email") or "","date":r["reservation_date"],"time":r["reservation_time"],"guests":r["guests"],"note":r.get("note") or "","status":r["status"],"createdAt":r["created_at"]}
def phone(v):
    v=re.sub(r"[\s().-]","",v)
    if v.startswith("00"): v="+"+v[2:]
    if v.startswith("+"): return v if v[1:].isdigit() and 8<=len(v[1:])<=15 else None
    return "+91"+v if len(v)==10 and v.isdigit() and v[0] in "6789" else None
def validate(p):
    out={k:str(p.get(k,"")).strip() for k in ("name","phone","email","date","time","guests","note")}
    if not all(out[k] for k in ("name","phone","date","time","guests")): return None,"Please fill all required reservation fields."
    if len(out["name"])>80: return None,"Name is too long."
    if not phone(out["phone"]): return None,"Please enter a valid mobile number, including country code if it is outside India."
    if out["email"] and (len(out["email"])>120 or not EMAIL.match(out["email"])): return None,"Please enter a valid email address."
    try: d=date.fromisoformat(out["date"]); t=datetime.strptime(out["time"],"%H:%M").time()
    except ValueError: return None,"Please choose a valid date and time."
    if d<date.today(): return None,"Please choose today or a future date."
    if not datetime.strptime("11:00","%H:%M").time()<=t<=datetime.strptime("23:00","%H:%M").time(): return None,"Reservations are available between 11:00 AM and 11:00 PM."
    if out["guests"] not in {"1","2","3","4","5","6+"}: return None,"Please choose the number of guests."
    out["note"]=out["note"][:500]; return out,None
def db(method, query=None, payload=None):
    url=os.environ.get("SUPABASE_URL","").rstrip("/"); key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")
    if not url or not key: raise RuntimeError("The reservation database is not configured.")
    url += "/rest/v1/reservations" + (("?"+urlencode(query)) if query else "")
    req=Request(url, data=json.dumps(payload).encode() if payload is not None else None, method=method, headers={"apikey":key,"Authorization":"Bearer "+key,"Content-Type":"application/json","Prefer":"return=representation"})
    try:
        with urlopen(req,timeout=12) as res: return json.loads(res.read().decode() or "[]")
    except HTTPError as e: raise RuntimeError(f"Database request failed ({e.code}).") from e
    except URLError as e: raise RuntimeError("Could not reach the reservation database.") from e
def email(r):
    if not r["email"]: return {"channel":"email","status":"skipped","message":"Customer email is not available."}
    address=os.environ.get("MJ_GMAIL_ADDRESS","").strip(); password=re.sub(r"\s+","",os.environ.get("MJ_GMAIL_APP_PASSWORD",""))
    if not address or not password: return {"channel":"email","status":"not_configured","message":"Gmail is not configured on the server."}
    msg=EmailMessage(); msg["Subject"]=f"Reservation #{r['id']} confirmed"; msg["From"]=f"{os.environ.get('MJ_GMAIL_FROM_NAME','Masala Junction').strip()} <{address}>"; msg["To"]=r["email"]
    msg.set_content(f"Hi {r['name']},\n\nYour Masala Junction table reservation is confirmed.\n\nDate: {r['date']}\nTime: {r['time']}\nGuests: {r['guests']}\n\nThank you,\nMasala Junction")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com",465,context=ssl.create_default_context(),timeout=12) as smtp: smtp.login(address,password); smtp.send_message(msg)
    except Exception as e: print(f"Email error: {e}"); return {"channel":"email","status":"error","message":"Email confirmation could not be sent."}
    return {"channel":"email","status":"sent","message":"Email confirmation sent."}

class handler(BaseHTTPRequestHandler):
    def end_headers(self): self.send_header("X-Content-Type-Options","nosniff"); self.send_header("Cache-Control","no-store"); super().end_headers()
    def reply(self,status,payload):
        body=json.dumps(payload).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def body(self):
        try: n=int(self.headers.get("Content-Length","0")); assert 0<=n<=MAX_BODY; v=json.loads(self.rfile.read(n).decode()) if n else {}; assert isinstance(v,dict); return v,None
        except (ValueError,AssertionError,json.JSONDecodeError,UnicodeDecodeError): return None,"Invalid JSON body."
    def auth(self):
        try: value=SimpleCookie(self.headers.get("Cookie","")).get(COOKIE); value=value.value if value else ""; expires,sig=value.rsplit(".",1)
        except (ValueError,KeyError): return False
        return bool(secret()) and expires.isdigit() and int(expires)>=int(time.time()) and hmac.compare_digest(sig,hmac.new(secret(),expires.encode(),hashlib.sha256).hexdigest())
    def admin(self):
        if self.auth(): return True
        self.reply(401,{"error":"Admin sign-in is required."}); return False
    def cookie(self,value=None):
        secure = "; Secure" if os.environ.get("MJ_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"} else ""
        self.send_header("Set-Cookie",f"{COOKIE}={value or ''}; Path=/; HttpOnly; SameSite=Strict{secure}; Max-Age={SESSION_SECONDS if value else 0}")
    def do_GET(self):
        p=urlparse(self.path).path
        if p=="/api/admin/session": self.reply(200,{"authenticated":self.auth()}); return
        if p!="/api/reservations": self.reply(404,{"error":"Not found."}); return
        if not self.admin(): return
        try: self.reply(200,{"reservations":[row(x) for x in db("GET",{"select":"*","order":"reservation_date.asc,reservation_time.asc,created_at.desc"})]})
        except RuntimeError as e: self.reply(503,{"error":str(e)})
    def do_POST(self):
        p=urlparse(self.path).path
        if p=="/api/admin/login":
            data,err=self.body(); password=os.environ.get("MJ_ADMIN_PASSWORD","")
            if err: self.reply(400,{"error":err}); return
            if not password: self.reply(503,{"error":"Admin sign-in has not been configured on the server."}); return
            if not hmac.compare_digest(str(data.get("password","")),password): self.reply(401,{"error":"Incorrect password."}); return
            expires=str(int(time.time())+SESSION_SECONDS); self.send_response(204); self.cookie(expires+"."+hmac.new(secret(),expires.encode(),hashlib.sha256).hexdigest()); self.end_headers(); return
        if p=="/api/admin/logout":
            if self.admin(): self.send_response(204); self.cookie(); self.end_headers()
            return
        if p=="/api/reservations":
            data,err=self.body(); reservation,error=validate(data or {}) if not err else (None,err)
            if error: self.reply(400,{"error":error}); return
            try:
                saved=db("POST",payload={"name":reservation["name"],"phone":reservation["phone"],"email":reservation["email"],"reservation_date":reservation["date"],"reservation_time":reservation["time"],"guests":reservation["guests"],"note":reservation["note"],"status":"pending","created_at":datetime.now(timezone.utc).isoformat(timespec="seconds")})[0]; self.reply(201,{"reservation":row(saved)})
            except (RuntimeError,IndexError) as e: self.reply(503,{"error":str(e)})
            return
        parts=p.strip("/").split("/")
        if len(parts)==4 and parts[:2]==["api","reservations"] and parts[3]=="confirmations":
            if not self.admin(): return
            try:
                rows=db("GET",{"select":"*","id":f"eq.{int(parts[2])}"})
                if not rows: self.reply(404,{"error":"Reservation not found."}); return
                r=row(rows[0])
                if r["status"]!="confirmed": self.reply(409,{"error":"Approve the reservation before sending a confirmation."}); return
                self.reply(200,{"reservation":r,"notifications":[email(r)]})
            except (RuntimeError,ValueError) as e: self.reply(503,{"error":str(e)})
            return
        self.reply(404,{"error":"Not found."})
    def do_PATCH(self):
        parts=urlparse(self.path).path.strip("/").split("/")
        if len(parts)!=3 or parts[:2]!=["api","reservations"]: self.reply(404,{"error":"Not found."}); return
        if not self.admin(): return
        data,err=self.body(); status=str((data or {}).get("status","")).strip().lower()
        if err or status not in STATUSES: self.reply(400,{"error":err or "Invalid reservation status."}); return
        try:
            ident=int(parts[2]); old=db("GET",{"select":"*","id":f"eq.{ident}"})
            if not old: self.reply(404,{"error":"Reservation not found."}); return
            r=row(db("PATCH",{"id":f"eq.{ident}"},{"status":status})[0]); response={"reservation":r}
            if status=="confirmed" and old[0]["status"]!="confirmed": response["notifications"]=[email(r)]
            self.reply(200,response)
        except (RuntimeError,ValueError,IndexError) as e: self.reply(503,{"error":str(e)})
