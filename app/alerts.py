import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from .db import connect
from . import inventory
from .domain import SCALE, forecast, occurrences, zone

log = logging.getLogger(__name__)


def ntfy_base():
    base = os.environ.get("NTFY_BASE_URL", "https://ntfy.sh").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("NTFY_BASE_URL debe ser una URL HTTP/HTTPS sin credenciales, consulta ni fragmento.")
    return base


def add(db, user_id, key, title, message, kind, now):
    db.execute("INSERT OR IGNORE INTO alerts(user_id,dedupe_key,title,message,kind,created_at) VALUES (?,?,?,?,?,?)",
               (user_id, key, title, message, kind, now))


def generate(db, now):
    inventory.sync_due(db,now)
    for user in db.execute("SELECT * FROM users").fetchall():
        tz = zone(user["timezone"])
        today = datetime.fromtimestamp(now, tz).strftime("%Y-%m-%d")
        for med in db.execute("SELECT * FROM medications WHERE user_id=? AND active=1", (user["id"],)).fetchall():
            if med["end_at"] is not None and med["end_at"] < now:
                continue
            if med["reminders"]:
                # No se acumulan avisos antiguos tras apagar el NAS. La agenda conserva las tomas pendientes.
                for at in occurrences(med, now - 600, now):
                    recorded = db.execute("SELECT status,automatic FROM doses WHERE medication_id=? AND scheduled_at=?",(med['id'],at)).fetchone()
                    # Un descuento estimado no debe cancelar el recordatorio de tomarlo.
                    if not recorded or (recorded['status']=='taken' and recorded['automatic']):
                        clock = datetime.fromtimestamp(at, tz).strftime("%H:%M")
                        add(db, user["id"], f"dose:{med['id']}:{at}", "Hora de tu toma",
                            f"{clock} · {med['name']}: {med['dose'] / SCALE:g} {med['unit']}. {med['instructions']}".strip(), "dose", now)
            resolved = [r[0] for r in db.execute("SELECT scheduled_at FROM doses WHERE medication_id=? AND scheduled_at>=?", (med["id"], now))]
            prediction = forecast(med, now, resolved)
            if user["stock_alerts"] and (prediction["stock_warning"] or med["stock"] < med["dose"]):
                add(db, user["id"], f"stock:{med['id']}:{today}", "Revisa tus existencias",
                    f"{med['name']}: quedan {med['stock'] / SCALE:g} {med['unit']}. Planifica la reposición.", "stock", now)
        if user["prescription_alerts"]:
            horizon = (datetime.fromtimestamp(now, tz) + timedelta(days=7)).strftime("%Y-%m-%d")
            for recipe in db.execute("SELECT * FROM prescriptions WHERE user_id=? AND renewal_date<=?", (user["id"], horizon)).fetchall():
                add(db, user["id"], f"prescription:{recipe['id']}:{today}:{recipe['renewal_date']}", "Renueva tu receta",
                    f"{recipe['title']}: renovación prevista el {recipe['renewal_date']}.", "prescription", now)
    db.execute("DELETE FROM alerts WHERE created_at<?", (now - 90 * 86400,))
    db.commit()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def deliver(db, now, sender=None):
    sender = sender or urllib.request.build_opener(NoRedirect()).open
    pending = db.execute("SELECT a.*,u.ntfy_topic FROM alerts a JOIN users u ON u.id=a.user_id WHERE a.delivered=0 AND a.attempts<5 AND u.ntfy_enabled=1 AND a.created_at>=? AND a.last_attempt<=? ORDER BY a.id LIMIT 20",
                         (now - 600, now - 60)).fetchall()
    for alert in pending:
        payload = json.dumps(dict(topic=alert["ntfy_topic"], title=alert["title"], message=alert["message"], tags=["pill" if alert["kind"] == "dose" else "warning"])).encode()
        request = urllib.request.Request(ntfy_base(), data=payload, headers={"Content-Type": "application/json", "User-Agent": "Pastillas/0.1"})
        token = os.environ.get("NTFY_TOKEN", "")
        if token:
            request.add_header("Authorization", "Bearer " + token)
        delivered = 0
        try:
            with sender(request, timeout=5) as response:
                delivered = int(200 <= response.status < 300)
        except Exception:
            # No se registran mensajes, temas privados ni tokens en los logs.
            log.warning("No se pudo entregar el aviso %s a ntfy; se reintentará.", alert["id"])
        db.execute("UPDATE alerts SET delivered=?,attempts=attempts+1,last_attempt=? WHERE id=?", (delivered, now, alert["id"]))
        db.commit()


def worker(stop):
    while not stop.is_set():
        try:
            with connect() as db:
                now = int(time.time())
                generate(db, now)
                deliver(db, now)
        except Exception:
            log.exception("Error en el proceso de avisos")
        stop.wait(30)
