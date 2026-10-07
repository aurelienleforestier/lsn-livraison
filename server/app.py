import os, json, base64, hashlib, secrets, smtplib, ssl, time, copy, re
from collections import defaultdict, deque
from threading import Lock
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Any

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from controls import locations, control_transition
from sqlalchemy import create_engine, String, Boolean, DateTime, Integer, Text, ForeignKey, select, inspect, text, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_CONFIGURED = bool(os.getenv("DATABASE_URL"))
REQUIRE_DATABASE = os.getenv("REQUIRE_DATABASE", "false").lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR/'lsn_pharma.db').as_posix()}")
if DATABASE_URL.startswith(("postgres://", "postgresql://")):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.split("://", 1)[1]
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "12"))
RESET_MINUTES = int(os.getenv("RESET_MINUTES", "30"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in {"1","true","yes","on"}

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(20), default="operator")
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    csrf_token: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AppState(Base):
    __tablename__ = "app_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    data: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

def utcnow():
    return datetime.now(timezone.utc)

def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def hash_password(password: str) -> str:
    if not 10 <= len(password) <= 200:
        raise ValueError("Le mot de passe doit contenir au moins 10 caractères.")
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(derived).decode()

def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_b64, hash_b64 = stored.split("$", 2)
        if algo != "scrypt": return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(hash_b64.encode())
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=len(expected))
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False

def default_state() -> dict[str, Any]:
    return {
        "appVersion": 60,
        "routes": [
            {"id":"T01","name":"Tournée 01 — Paris Sud","published":True,"pharmacies":["PH-001458","PH-001459","PH-001460"]},
            {"id":"T02","name":"Tournée 02 — Hauts-de-Seine","published":True,"pharmacies":["PH-001462","PH-001463"]},
            {"id":"T03","name":"Tournée 03 — Essonne","published":True,"pharmacies":["PH-001458","PH-001459","PH-001460","PH-001461"]},
        ],
        "pharmacyMeta": {},
        "loadByRoute": {},
        "deliveredByRoute": {},
        "deliveryStarted": {},
        "deliveryCursorByRoute": {},
        "tourRunMeta": {},
        "tourHistory": [],
        "binAdjustments": [],
        "bins": {
            "available": [f"BAC-{i:06d}" for i in range(1,21)],
            "client": {"PH-001458":["BAC-OLD-001","BAC-OLD-002","BAC-OLD-003","BAC-OLD-004","BAC-OLD-005"]},
        },
    }

def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def audit(db: Session, user_id: Optional[int], action: str, details: dict | None = None):
    db.add(AuditLog(user_id=user_id, action=action, details=json.dumps(details or {}, ensure_ascii=False)))

def create_initial_admin(db: Session):
    count = db.scalar(select(User.id).limit(1))
    if count is not None:
        return
    email = os.getenv("LSN_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("LSN_ADMIN_PASSWORD", "")
    name = os.getenv("LSN_ADMIN_NAME", "Pharmacien administrateur").strip() or "Pharmacien administrateur"
    if not email or not (password or os.getenv("LSN_ADMIN_PASSWORD_HASH")):
        print("[LSN PHARMA] Aucun compte initial. Définir LSN_ADMIN_EMAIL et LSN_ADMIN_PASSWORD puis redémarrer.")
        return
    try:
        ph = os.getenv("LSN_ADMIN_PASSWORD_HASH") or hash_password(password)
    except ValueError as exc:
        raise RuntimeError(str(exc))
    db.add(User(email=email, name=name, role="admin", password_hash=ph, active=True, must_change_password=True))
    audit(db, None, "bootstrap_admin", {"email": email})
    db.commit()
    print(f"[LSN PHARMA] Compte administrateur initial créé: {email}")

def init_database():
    Base.metadata.create_all(engine)
    if "last_activity_at" not in {c["name"] for c in inspect(engine).get_columns("sessions")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE sessions ADD COLUMN last_activity_at TIMESTAMP"))
            connection.execute(text("UPDATE sessions SET last_activity_at = created_at"))
    with SessionLocal() as db:
        st = db.get(AppState, 1)
        if not st:
            db.add(AppState(id=1, data=json.dumps(default_state(), ensure_ascii=False), version=1, updated_at=utcnow()))
            db.commit()
        create_initial_admin(db)

DATABASE_READY = False
if DATABASE_CONFIGURED or not REQUIRE_DATABASE:
    init_database()
    DATABASE_READY = True
app = FastAPI(title="LSN PHARMA Interne — Test", docs_url=None, redoc_url=None, openapi_url=None)
_attempts = defaultdict(deque)
_attempt_lock = Lock()

@app.middleware("http")
async def security_boundary(request: Request, call_next):
    path = request.url.path
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail":"Origine refusée"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail":"Origine refusée"}, status_code=403)
        try:
            if int(request.headers.get("content-length", "0")) > 2_000_000:
                return JSONResponse({"detail":"Requête trop volumineuse"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail":"Requête incorrecte"}, status_code=400)
    if path in {"/api/auth/login", "/api/auth/forgot", "/api/auth/reset"}:
        key = ((request.client.host if request.client else "unknown"), path)
        now = time.monotonic()
        with _attempt_lock:
            q = _attempts[key]
            while q and q[0] < now - 600: q.popleft()
            if len(q) >= 25:
                return JSONResponse({"detail":"Trop de tentatives. Réessayer dans quelques minutes."}, status_code=429)
            q.append(now)
    if not DATABASE_READY and path not in {"/health", "/robots.txt"}:
        if path.startswith("/api/"):
            return JSONResponse({"detail":"La base de test n’est pas encore reliée."}, status_code=503)
        return HTMLResponse(MAINTENANCE_HTML, status_code=503, headers={"Cache-Control":"no-store", "X-Robots-Tag":"noindex, nofollow"})
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://unpkg.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response

MAINTENANCE_HTML = """<!doctype html><html lang=fr><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>LSN PHARMA — Test</title><style>body{font:17px system-ui;background:#f5f7f8;color:#111827;padding:30px}.card{max-width:490px;margin:9vh auto;background:white;padding:30px;border-radius:18px}p{line-height:1.6}</style><div class=card><h1>LSN PHARMA</h1><h2>Version de test</h2><p>L’application est installée. La connexion à la base de test reste à terminer.</p><p>Ton application habituelle est inchangée.</p></div></html>"""

@app.get("/robots.txt")
def robots(): return Response("User-agent: *\nDisallow: /\n", media_type="text/plain")

class LoginIn(BaseModel):
    email: str = Field(min_length=2, max_length=254)  # nom utilisateur ou e-mail
    password: str = Field(min_length=1, max_length=200)
class PasswordIn(BaseModel):
    password: str = Field(min_length=10, max_length=200)
class ForgotIn(BaseModel):
    email: str = Field(min_length=2, max_length=254)  # nom utilisateur ou e-mail
class ResetIn(BaseModel):
    token: str
    password: str
class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: Optional[str] = Field(default=None, max_length=254)
    role: str = "operator"
    temporary_password: str = Field(min_length=10, max_length=200)
class UserPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    role: Optional[str] = None
    active: Optional[bool] = None
class StatePayload(BaseModel):
    state: dict[str, Any]
    version: int = Field(ge=1)

INTERNAL_EMAIL_SUFFIX = "@users.lsn.invalid"

def public_email(value: str) -> str:
    value = (value or "").strip()
    return "" if value.lower().endswith(INTERNAL_EMAIL_SUFFIX) else value

def internal_user_email() -> str:
    return "internal-" + secrets.token_hex(8) + INTERNAL_EMAIL_SUFFIX

def find_user_by_identifier(db: Session, identifier: str) -> Optional[User]:
    key = (identifier or "").strip().casefold()
    if not key:
        return None
    users = db.scalars(select(User)).all()
    for user in users:
        if (user.email or "").strip().casefold() == key or (user.name or "").strip().casefold() == key:
            return user
    return None

def pharmacist_reset_email(db: Session) -> str:
    configured = os.getenv("LSN_ADMIN_EMAIL", "").strip().lower()
    if configured:
        return configured
    admins = db.scalars(select(User).where(User.role == "admin", User.active == True).order_by(User.id.asc())).all()
    for admin in admins:
        email = public_email(admin.email)
        if email:
            return email
    return ""

def serialize_user(u: User):
    return {"id": str(u.id), "email": public_email(u.email), "name": u.name, "role": u.role, "active": u.active, "mustChangePassword": u.must_change_password,
            "createdAt": u.created_at.isoformat() if u.created_at else None,
            "lastLoginAt": u.last_login_at.isoformat() if u.last_login_at else None}

def get_auth(request: Request, db: Session) -> tuple[User, UserSession]:
    raw = request.cookies.get("lsn_session")
    if not raw:
        raise HTTPException(401, "Authentification requise")
    s = db.scalar(select(UserSession).where(UserSession.token_hash == digest_token(raw)))
    if not s or s.expires_at.replace(tzinfo=timezone.utc) <= utcnow() or (s.last_activity_at or s.created_at).replace(tzinfo=timezone.utc) <= utcnow() - timedelta(minutes=15):
        if s:
            db.delete(s); db.commit()
        raise HTTPException(401, "Session expirée")
    u = db.get(User, s.user_id)
    if not u or not u.active:
        raise HTTPException(401, "Compte désactivé")
    if u.must_change_password and request.url.path not in {"/api/me", "/api/auth/change-password", "/api/auth/logout", "/change-password", "/login", "/"}:
        raise HTTPException(403, "Le mot de passe temporaire doit être remplacé.")
    return u, s

def current_auth(request: Request, db: Session = Depends(db_session)):
    return get_auth(request, db)

def require_csrf(request: Request, auth=Depends(current_auth)):
    u, s = auth
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not secrets.compare_digest(supplied, s.csrf_token):
        raise HTTPException(403, "Jeton CSRF invalide")
    return u, s

def admin_auth(auth=Depends(require_csrf)):
    u, s = auth
    if u.role != "admin":
        raise HTTPException(403, "Accès réservé au Pharmacien / Admin")
    return u, s

def admin_read_auth(auth=Depends(current_auth)):
    u, s = auth
    if u.role != "admin":
        raise HTTPException(403, "Accès réservé au Pharmacien / Admin")
    return u, s

@app.get("/health")
def health(): return {"ok": True, "databaseReady": DATABASE_READY, "version": "6.2-validation"}

@app.get("/")
def root(request: Request, db: Session = Depends(db_session)):
    try:
        u, _ = get_auth(request, db)
        if u.must_change_password: return RedirectResponse("/change-password", status_code=302)
        return FileResponse(STATIC_DIR / "app.html")
    except HTTPException:
        return RedirectResponse("/login", status_code=302)

@app.get("/login")
def login_page(request: Request, db: Session = Depends(db_session)):
    try:
        get_auth(request, db)
        return RedirectResponse("/", status_code=302)
    except HTTPException:
        return FileResponse(STATIC_DIR / "login.html")

@app.get("/forgot")
def forgot_page(): return FileResponse(STATIC_DIR / "forgot.html")
@app.get("/reset")
def reset_page(): return FileResponse(STATIC_DIR / "reset.html")
@app.get("/change-password")
def change_password_page(request: Request, db: Session = Depends(db_session)):
    try: get_auth(request, db)
    except HTTPException: return RedirectResponse("/login", status_code=302)
    return FileResponse(STATIC_DIR / "change-password.html")
@app.get("/manifest.webmanifest")
def manifest(): return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")
@app.get("/lsn-logo.svg")
def lsn_logo(): return FileResponse(STATIC_DIR / "lsn-logo.svg", media_type="image/svg+xml")
@app.get("/sw.js")
def sw(): return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")

@app.post("/api/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(db_session)):
    identifier = payload.email.strip()
    u = find_user_by_identifier(db, identifier)
    if not u or not u.active or not verify_password(payload.password, u.password_hash):
        audit(db, u.id if u else None, "login_failed", {"identifier": identifier}); db.commit()
        raise HTTPException(401, "Utilisateur ou mot de passe incorrect")
    raw = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    db.add(UserSession(token_hash=digest_token(raw), csrf_token=csrf, user_id=u.id, expires_at=utcnow()+timedelta(hours=SESSION_HOURS)))
    u.last_login_at = utcnow()
    audit(db, u.id, "login_success")
    db.commit()
    response.set_cookie("lsn_session", raw, httponly=True, secure=COOKIE_SECURE, samesite="strict", max_age=SESSION_HOURS*3600, path="/")
    return {"user": serialize_user(u), "mustChangePassword": u.must_change_password}

@app.post("/api/auth/logout")
def logout(response: Response, auth=Depends(require_csrf), db: Session = Depends(db_session)):
    u, s = auth
    audit(db, u.id, "logout")
    db.delete(s); db.commit()
    response.delete_cookie("lsn_session", path="/")
    return {"ok": True}

@app.get("/api/me")
def me(auth=Depends(current_auth)):
    u, s = auth
    return {"user": serialize_user(u), "csrf": s.csrf_token}

@app.post("/api/auth/change-password")
def change_password(payload: PasswordIn, auth=Depends(require_csrf), db: Session = Depends(db_session)):
    u, s = auth
    try: u.password_hash = hash_password(payload.password)
    except ValueError as e: raise HTTPException(400, str(e))
    u.must_change_password = False
    audit(db, u.id, "password_changed")
    db.commit()
    return {"ok": True}

def send_reset_email(to_email: str, reset_url: str, account_name: str = "") -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return False
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", user or "noreply@lsnpharma.local")
    msg = EmailMessage()
    label = account_name.strip() or "Compte LSN PHARMA"
    msg["Subject"] = f"LSN PHARMA — Réinitialisation du mot de passe — {label}"
    msg["From"] = sender; msg["To"] = to_email
    msg.set_content(f"Une demande de réinitialisation a été effectuée pour : {label}.\n\nLien valable {RESET_MINUTES} minutes :\n{reset_url}\n\nSi cette demande est légitime, utilise ce lien pour définir un nouveau mot de passe.")
    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls(context=ctx)
        if user: smtp.login(user, password)
        smtp.send_message(msg)
    return True

@app.post("/api/auth/forgot")
def forgot(payload: ForgotIn, db: Session = Depends(db_session)):
    identifier = payload.email.strip()
    u = find_user_by_identifier(db, identifier)
    if u and u.active:
        token = secrets.token_urlsafe(32)
        db.add(PasswordReset(token_hash=digest_token(token), user_id=u.id, expires_at=utcnow()+timedelta(minutes=RESET_MINUTES)))
        audit(db, u.id, "password_reset_requested", {"identifier": identifier})
        db.commit()
        reset_url = f"{PUBLIC_BASE_URL}/reset?token={token}"
        recipient = public_email(u.email) if u.role == "admin" else pharmacist_reset_email(db)
        if os.getenv("SMTP_HOST") and recipient:
            try:
                send_reset_email(recipient, reset_url, u.name)
            except Exception as exc:
                print("[LSN PHARMA] Erreur SMTP:", exc)
        elif not os.getenv("SMTP_HOST"):
            print(f"[LSN PHARMA] Demande de réinitialisation pour {u.name}; destinataire Pharmacien/Admin: {recipient or 'non configuré'}")
    return {"ok": True, "message": "Demande enregistrée. Le Pharmacien/Admin peut réinitialiser le mot de passe."}

@app.post("/api/auth/reset")
def reset_password(payload: ResetIn, db: Session = Depends(db_session)):
    pr = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == digest_token(payload.token), PasswordReset.used_at.is_(None)))
    if not pr or pr.expires_at.replace(tzinfo=timezone.utc) < utcnow():
        raise HTTPException(400, "Lien invalide ou expiré")
    u = db.get(User, pr.user_id)
    if not u or not u.active: raise HTTPException(400, "Compte indisponible")
    try: u.password_hash = hash_password(payload.password)
    except ValueError as e: raise HTTPException(400, str(e))
    u.must_change_password = False; pr.used_at = utcnow()
    for s in db.scalars(select(UserSession).where(UserSession.user_id == u.id)).all(): db.delete(s)
    audit(db, u.id, "password_reset_completed")
    db.commit()
    return {"ok": True}

ROUTE_FIELDS = ("loadByRoute", "deliveredByRoute", "deliveryStarted", "deliveryCursorByRoute", "tourRunMeta")

def physical_load(data, rid):
    return any(x.get("bins") or x.get("parcels", 0) for x in data.get("loadByRoute", {}).get(rid, {}).values())

def owner_id(data, rid):
    return str(data.get("tourRunMeta", {}).get(rid, {}).get("operator", {}).get("id", ""))

def visible_state(data, user):
    out = copy.deepcopy(data)
    if user.role == "admin": return out
    out["routes"] = [r for r in out.get("routes", []) if r.get("published")]
    owned = {r["id"] for r in out["routes"] if owner_id(data, r["id"]) == str(user.id)}
    out["busyRoutes"] = {r["id"]: True for r in out["routes"] if r["id"] not in owned and (physical_load(data, r["id"]) or data.get("deliveryStarted", {}).get(r["id"]))}
    for key in ROUTE_FIELDS: out[key] = {rid: value for rid, value in out.get(key, {}).items() if rid in owned}
    allowed_pharmacies = {pid for r in out["routes"] if r["id"] in owned for pid in r.get("pharmacies", [])}
    out["pharmacyMeta"] = {pid: v for pid, v in out.get("pharmacyMeta", {}).items() if pid in allowed_pharmacies}
    out["tourHistory"] = []
    out["binAdjustments"] = []
    return out

def validate_state(data):
    locations(data)
    def walk(x):
        if isinstance(x, str) and ("<" in x or ">" in x):
            raise HTTPException(400, "Caractères de balisage interdits")
        if isinstance(x, dict):
            for v in x.values(): walk(v)
        if isinstance(x, list):
            for v in x: walk(v)
    walk(data)
    routes = data.get("routes", [])
    if len(routes) > 300 or len({r.get("id") for r in routes}) != len(routes):
        raise HTTPException(400, "Liste de tournées invalide")
    for r in routes:
        if not re.fullmatch(r"T[0-9]{2,8}", str(r.get("id", ""))): raise HTTPException(400, "Numéro de tournée invalide")
        if len(set(r.get("pharmacies", []))) != len(r.get("pharmacies", [])): raise HTTPException(400, "Pharmacie en double")
        for pid in r.get("pharmacies", []):
            if not re.fullmatch(r"PH-[0-9]+", str(pid)): raise HTTPException(400, "Pharmacie invalide")
    seen = {}
    def place(code, location):
        if not re.fullmatch(r"BAC-[A-Z0-9-]{1,40}", str(code)): raise HTTPException(400, "Numéro de bac invalide")
        if code in seen: raise HTTPException(409, f"{code} a déjà une autre affectation. Recharge les données avant de continuer.")
        seen[code] = location
    for code in data.get("bins", {}).get("available", []): place(code, "warehouse")
    for pid, codes in data.get("bins", {}).get("client", {}).items():
        for code in codes: place(code, pid)
    for rid, loads in data.get("loadByRoute", {}).items():
        for pid, load in loads.items():
            delivered = data.get("deliveredByRoute", {}).get(rid, {}).get(pid, {})
            if delivered.get("done"): continue
            for code in load.get("bins", []): place(code, rid + "/" + pid)
            parcels = load.get("parcels", 0)
            if not isinstance(parcels, int) or not 0 <= parcels <= 10000: raise HTTPException(400, "Nombre de colis invalide")

@app.get("/api/state")
def get_state(auth=Depends(current_auth), db: Session = Depends(db_session)):
    u, _ = auth
    st = db.get(AppState, 1)
    return {"state": visible_state(json.loads(st.data), u), "version": st.version, "updatedAt": st.updated_at.isoformat()}

@app.put("/api/state")
def put_state(payload: StatePayload, auth=Depends(require_csrf), db: Session = Depends(db_session)):
    u, user_session = auth
    st = db.scalar(select(AppState).where(AppState.id == 1).with_for_update())
    if st.version != payload.version:
        raise HTTPException(409, "Les données ont changé sur un autre appareil. Recharge avant de recommencer cette action.")
    current = json.loads(st.data)
    incoming = copy.deepcopy(payload.state)
    locations(incoming)
    for k in ("currentUser", "selectedRoute", "adminSelectedRoute", "currentScreen", "busyRoutes"):
        incoming.pop(k, None)
    if u.role != "admin":
        merged = copy.deepcopy(current)
        route_ids = {r["id"] for r in current.get("routes", []) if r.get("published")}
        touched = set()
        for key in ROUTE_FIELDS:
            before = visible_state(current, u).get(key, {})
            after = incoming.get(key, {})
            if not isinstance(after, dict): raise HTTPException(400, "État invalide")
            for rid in set(before) | set(after):
                if before.get(rid) == after.get(rid): continue
                if rid not in route_ids: raise HTTPException(403, "Tournée non publiée")
                if owner_id(current, rid) not in ("", str(u.id)) and (physical_load(current, rid) or current.get("deliveryStarted", {}).get(rid)):
                    raise HTTPException(409, "Cette tournée est utilisée par un autre opérateur")
                touched.add(rid)
                merged.setdefault(key, {})
                if rid in after: merged[key][rid] = after[rid]
                else: merged[key].pop(rid, None)
        new_hist = incoming.get("tourHistory", [])
        for run in new_hist:
            rid = run.get("routeId")
            if rid not in route_ids or owner_id(current, rid) != str(u.id): raise HTTPException(403, "Archivage de tournée refusé")
            if any(h.get("id") == run.get("id") for h in current.get("tourHistory", [])): continue
            run["operatorId"] = str(u.id); run["operatorName"] = u.name
            merged.setdefault("tourHistory", []).append(run)
            touched.add(rid)
        if incoming.get("bins") != current.get("bins"):
            if not touched and incoming.get("binAdjustments") == []: raise HTTPException(403, "Mouvement de bac sans opération")
            merged["bins"] = incoming.get("bins", current.get("bins"))
        adjustments = incoming.get("binAdjustments", [])
        for item in adjustments:
            item["operatorId"] = str(u.id); item["operatorName"] = u.name
        merged.setdefault("binAdjustments", []).extend(adjustments)
        incoming = merged
    for r in incoming.get("routes", []):
        rid = r["id"]
        if (physical_load(incoming, rid) or incoming.get("deliveryStarted", {}).get(rid)) and not owner_id(current, rid):
            incoming.setdefault("tourRunMeta", {}).setdefault(rid, {})["operator"] = {"id":str(u.id), "name":u.name, "role":u.role}
    validate_state(incoming)
    moves = control_transition(current, incoming, u.role != "admin")
    user_session.last_activity_at = utcnow()
    new_version = payload.version + 1
    changed = db.execute(update(AppState).where(AppState.id == 1, AppState.version == payload.version).values(data=json.dumps(incoming,ensure_ascii=False,separators=(",",":")), version=new_version, updated_at=utcnow(), updated_by=u.id))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Conflit de version ; aucune modification enregistrée")
    audit(db, u.id, "state_saved", {"version":new_version,"movements":moves,"beforeSha256":hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest(),"afterSha256":hashlib.sha256(json.dumps(incoming,sort_keys=True).encode()).hexdigest()})
    db.commit()
    return {"ok":True, "version":new_version, "state":visible_state(incoming, u)}

@app.get("/api/users")
def list_users(auth=Depends(admin_read_auth), db: Session = Depends(db_session)):
    users = db.scalars(select(User).order_by(User.active.desc(), User.name.asc())).all()
    return {"users": [serialize_user(x) for x in users]}

@app.post("/api/users")
def create_user(payload: UserCreate, auth=Depends(admin_auth), db: Session = Depends(db_session)):
    admin, _ = auth
    name = payload.name.strip()
    if any(ch in name for ch in "<>"): raise HTTPException(400, "Nom invalide")
    for existing in db.scalars(select(User)).all():
        if (existing.name or "").strip().casefold() == name.casefold():
            raise HTTPException(409, "Ce nom utilisateur existe déjà")
    role = payload.role if payload.role in {"admin","operator"} else "operator"
    email = (payload.email or "").strip().lower()
    if email:
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(409, "Cette adresse e-mail existe déjà")
    else:
        email = internal_user_email()
    try: ph = hash_password(payload.temporary_password)
    except ValueError as e: raise HTTPException(400, str(e))
    u = User(name=name, email=email, role=role, password_hash=ph, active=True, must_change_password=True)
    db.add(u); db.flush(); audit(db, admin.id, "user_created", {"userId":u.id,"name":u.name,"role":role}); db.commit(); db.refresh(u)
    return {"user": serialize_user(u)}

@app.patch("/api/users/{user_id}")
def patch_user(user_id: int, payload: UserPatch, auth=Depends(admin_auth), db: Session = Depends(db_session)):
    admin, _ = auth
    u = db.get(User, user_id)
    if not u: raise HTTPException(404, "Profil introuvable")
    if payload.name is not None:
        new_name = payload.name.strip()
        if any(ch in new_name for ch in "<>"): raise HTTPException(400, "Nom invalide")
        for existing in db.scalars(select(User)).all():
            if existing.id != u.id and (existing.name or "").strip().casefold() == new_name.casefold():
                raise HTTPException(409, "Ce nom utilisateur existe déjà")
        u.name = new_name
    if payload.role is not None:
        if payload.role not in {"admin","operator"}: raise HTTPException(400, "Rôle invalide")
        if u.id == admin.id and payload.role != "admin": raise HTTPException(400, "Vous ne pouvez pas retirer votre propre rôle administrateur")
        u.role = payload.role
    if payload.active is not None:
        if u.id == admin.id and payload.active is False: raise HTTPException(400, "Vous ne pouvez pas désactiver votre propre compte")
        u.active = payload.active
        if not u.active:
            for s in db.scalars(select(UserSession).where(UserSession.user_id == u.id)).all(): db.delete(s)
    audit(db, admin.id, "user_updated", {"userId":u.id,"role":u.role,"active":u.active}); db.commit(); db.refresh(u)
    return {"user": serialize_user(u)}

@app.post("/api/users/{user_id}/temporary-password")
def admin_temp_password(user_id: int, payload: PasswordIn, auth=Depends(admin_auth), db: Session = Depends(db_session)):
    admin, _ = auth
    u = db.get(User, user_id)
    if not u: raise HTTPException(404, "Profil introuvable")
    try: u.password_hash = hash_password(payload.password)
    except ValueError as e: raise HTTPException(400, str(e))
    u.must_change_password = True
    for s in db.scalars(select(UserSession).where(UserSession.user_id == u.id)).all(): db.delete(s)
    audit(db, admin.id, "temporary_password_set", {"userId":u.id}); db.commit()
    return {"ok": True}

@app.get("/api/audit")
def audit_list(auth=Depends(admin_read_auth), db: Session = Depends(db_session)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)).all()
    return {"events":[{"id":x.id,"userId":x.user_id,"action":x.action,"details":json.loads(x.details or "{}"),"createdAt":x.created_at.isoformat()} for x in rows]}

@app.get("/sync.js")
def sync_script(auth=Depends(current_auth)): return FileResponse(STATIC_DIR / "sync.js", media_type="application/javascript")

@app.post("/api/auth/activity")
def user_activity(auth=Depends(require_csrf), db: Session = Depends(db_session)):
    _, session = auth
    session.last_activity_at = utcnow()
    db.commit()
    return {"ok":True}
