import json
import secrets
import time
from datetime import datetime, timedelta

from .auth import credentials, hash_password, public_user
from . import inventory, medicine_info
from .domain import (Invalid, SCALE, boolean, date, forecast, medication_input,
                     occurrences, prescription_input, quantity, serialize_med, text, zone)


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def owned(db, table, ident, user_id):
    if table not in ("medications", "prescriptions"):
        raise ValueError("Tabla no válida")
    item = db.execute(f"SELECT * FROM {table} WHERE id=? AND user_id=?", (ident, user_id)).fetchone()
    if not item:
        raise NotFound("No se ha encontrado el registro.")
    return item


def insert(db, table, fields):
    columns = ",".join(fields)
    placeholders = ",".join("?" for _ in fields)
    return db.execute(f"INSERT INTO {table}({columns}) VALUES ({placeholders})", tuple(fields.values())).lastrowid


def update(db, table, ident, fields):
    sets = ",".join(f"{key}=?" for key in fields)
    db.execute(f"UPDATE {table} SET {sets} WHERE id=?", (*fields.values(), ident))


def medication_save(db, user, data, ident=None, now=None):
    now = int(time.time()) if now is None else now
    fields = medication_input(data, user["timezone"])
    if fields["prescription_id"]:
        owned(db, "prescriptions", fields["prescription_id"], user["id"])
    if ident:
        inventory.sync_due(db,now,user['id'],ident)
        old = owned(db, "medications", ident, user["id"])
        if fields["unit"] != old["unit"] and db.execute("SELECT 1 FROM stock_movements WHERE medication_id=? LIMIT 1", (ident,)).fetchone():
            raise Invalid("La unidad de existencias tiene movimientos. Crea otro medicamento para cambiar de unidad.")
        update(db, "medications", ident, dict(fields,auto_cursor=now))
    else:
        stock = quantity(data.get("stock", 0), "Existencias")
        if stock < 0:
            raise Invalid("Las existencias no pueden ser negativas.")
        ident = insert(db, "medications", dict(fields, user_id=user["id"], stock=stock, created_at=now,
                       auto_cursor=now-1))
        insert(db, "stock_movements", dict(medication_id=ident, amount=stock, kind="initial", recorded_at=now, note="Existencias iniciales"))
    return ident


def stock_add(db, user_id, ident, data, now=None):
    now = int(time.time()) if now is None else now
    # El bloqueo es previo a la lectura: compras, tomas y correcciones son atómicas.
    inventory.sync_due(db,now,user_id,ident)
    med = owned(db, "medications", ident, user_id)
    kind = data.get("kind", "purchase")
    if kind not in ("purchase", "adjustment", "verification"):
        raise Invalid("Movimiento no válido.")
    amount = quantity(data.get("amount"), "Cantidad", positive=kind == "purchase")
    note = text(data.get("note", ""), "Nota", 1000)
    price = data.get("price")
    cents = None
    if price not in (None, ""):
        price_units = quantity(price, "Precio")
        if price_units < 0 or price_units % 10:
            raise Invalid("El precio debe ser positivo con hasta 2 decimales.")
        cents = price_units // 10
    # Una corrección indica el total contado físicamente, no una diferencia.
    delta = amount if kind == "purchase" else amount - med["stock"]
    if med["stock"] + delta < 0:
        raise Invalid("Las existencias no pueden ser negativas.")
    db.execute("UPDATE medications SET stock=stock+? WHERE id=?", (delta, ident))
    if kind == 'verification':
        note = f"Contado: {amount / SCALE:g} {med['unit']}; calculado: {med['stock'] / SCALE:g} {med['unit']}." + (' ' + note if note else '')
        db.execute('UPDATE medications SET stock_verified_at=? WHERE id=?',(now,ident))
    return insert(db, "stock_movements", dict(medication_id=ident, amount=delta, kind=kind, recorded_at=now, note=note, price_cents=cents))


def record_dose(db, user_id, ident, data, now=None):
    now = int(time.time()) if now is None else now
    inventory.sync_due(db,now,user_id,ident)
    med = owned(db, "medications", ident, user_id)
    status = data.get("status", "taken")
    if status not in ("taken", "skipped"):
        raise Invalid("Estado de toma no válido.")
    note = text(data.get("note", ""), "Nota", 1000)
    scheduled = data.get("scheduled_at", now)
    if type(scheduled) is not int or scheduled > now + 300 or scheduled < now - 366 * 86400:
        raise Invalid("La toma debe ser pasada o actual (máximo un año).")
    existing = db.execute("SELECT * FROM doses WHERE medication_id=? AND scheduled_at=?", (ident, scheduled)).fetchone()
    if not existing and med["schedule"] == "as_needed":
        if not med["active"] or now < med["start_at"] or (med["end_at"] is not None and now > med["end_at"]):
            raise Invalid("Este medicamento no está activo en esta fecha.")
    elif not existing and scheduled not in occurrences(med, scheduled, scheduled):
        raise Invalid("Esta toma no corresponde a la pauta activa. Actualiza la agenda.")
    if existing:
        if existing["status"] == status:
            if status == 'taken' and existing['automatic']:
                db.execute('UPDATE doses SET automatic=0,note=?,recorded_at=? WHERE id=?',(note,now,existing['id']))
            return existing["id"]
        # Omitir devuelve el descuento real, incluso si el stock solo cubrió parte.
        if status == 'skipped':
            db.execute('UPDATE medications SET stock=stock+? WHERE id=?',(existing['amount'],ident))
            db.execute("UPDATE doses SET status='skipped',amount=0,automatic=0,note=?,recorded_at=? WHERE id=?",(note,now,existing['id']))
            if existing['amount']:
                insert(db,'stock_movements',dict(medication_id=ident,amount=existing['amount'],kind='undo',recorded_at=now,note='Toma omitida: devolución del descuento',dose_id=existing['id']))
            return existing['id']
    expected = (existing['expected_amount'] or med['dose']) if existing else med['dose']
    amount = expected if status == "taken" else 0
    if amount > med["stock"]:
        raise Conflict("No hay existencias suficientes. Registra la compra o corrige el inventario antes de confirmar.")
    if existing:
        ident_dose = existing['id']
        update(db,'doses',ident_dose,dict(status=status,amount=amount,automatic=0,note=note,recorded_at=now,expected_amount=expected))
    else:
        ident_dose = insert(db, "doses", dict(medication_id=ident, scheduled_at=scheduled, recorded_at=now,
                           status=status, amount=amount, note=note, automatic=0, expected_amount=expected))
    if amount:
        db.execute("UPDATE medications SET stock=stock-? WHERE id=?", (amount, ident))
        insert(db, "stock_movements", dict(medication_id=ident, amount=-amount, kind="dose", recorded_at=now, dose_id=ident_dose))
    return ident_dose


def undo_dose(db, user_id, dose_id, now=None):
    now = int(time.time()) if now is None else now
    dose = db.execute("SELECT d.* FROM doses d JOIN medications m ON m.id=d.medication_id WHERE d.id=? AND m.user_id=?", (dose_id, user_id)).fetchone()
    if not dose:
        raise NotFound("La toma ya no existe.")
    med = owned(db,'medications',dose['medication_id'],user_id)
    if med['schedule'] != 'as_needed':
        # Un registro omitido impide que el descuento automático reaparezca.
        return record_dose(db,user_id,med['id'],dict(scheduled_at=dose['scheduled_at'],status='skipped'),now)
    db.execute("UPDATE medications SET stock=stock+? WHERE id=?", (dose["amount"], dose["medication_id"]))
    db.execute("DELETE FROM doses WHERE id=?", (dose_id,))
    if dose["amount"]:
        insert(db, "stock_movements", dict(medication_id=dose["medication_id"], amount=dose["amount"], kind="undo", recorded_at=now, note="Toma deshecha"))
    # Se conserva el movimiento original en el historial; se desvincula al eliminar la toma.


def medications(db, user_id, now):
    result = []
    for med in db.execute("SELECT * FROM medications WHERE user_id=? ORDER BY active DESC,name COLLATE NOCASE", (user_id,)):
        resolved = [r[0] for r in db.execute("SELECT scheduled_at FROM doses WHERE medication_id=? AND scheduled_at>=?", (med["id"], now))]
        item = serialize_med(med, now, resolved)
        item['information'] = medicine_info.information(db, med['id'], now)
        result.append(item)
    return result


def agenda(db, user, day, now):
    tz = zone(user["timezone"])
    date(day)
    start_day = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=tz)
    start, end = int(start_day.timestamp()), int((start_day + timedelta(days=1)).timestamp()) - 1
    items = []
    meds = db.execute("SELECT * FROM medications WHERE user_id=? ORDER BY name", (user["id"],)).fetchall()
    for med in meds:
        records = {r["scheduled_at"]: dict(r) for r in db.execute("SELECT * FROM doses WHERE medication_id=? AND scheduled_at BETWEEN ? AND ?", (med["id"], start, end))}
        for at in sorted(set(occurrences(med, start, end)) | set(records)):
            recorded = records.get(at)
            items.append(dict(medication_id=med["id"], name=med["name"], brand=med["brand"], form=med["form"], strength=med["strength"],
                              dose=med["dose"] / SCALE, unit=med["unit"], instructions=med["instructions"], scheduled_at=at,
                              status=recorded["status"] if recorded else 'untracked' if at<=now and at<=med['auto_cursor'] else 'pending', dose_id=recorded["id"] if recorded else None,
                              automatic=bool(recorded['automatic']) if recorded else False,
                              expected_amount=(recorded['expected_amount'] or med['dose']) / SCALE if recorded else med['dose'] / SCALE,
                              stock_shortfall=max(0,recorded['expected_amount']-recorded['amount']) / SCALE if recorded and recorded['status']=='taken' else 0,
                              recorded_at=recorded["recorded_at"] if recorded else None,
                              amount=recorded["amount"] / SCALE if recorded else None,
                              overdue=not recorded and at < now - 900))
    return sorted(items, key=lambda r: (r["scheduled_at"], r["name"]))


def dashboard(db, user, now=None):
    now = int(time.time()) if now is None else now
    today = datetime.fromtimestamp(now, zone(user["timezone"])).strftime("%Y-%m-%d")
    meds = medications(db, user["id"], now)
    recipes = [dict(r) for r in db.execute("SELECT * FROM prescriptions WHERE user_id=? ORDER BY renewal_date IS NULL,renewal_date,title", (user["id"],))]
    for recipe in recipes:
        recipe["renewal_warning"] = recipe["renewal_date"] is not None and recipe["renewal_date"] <= (datetime.fromtimestamp(now, zone(user["timezone"])) + timedelta(days=7)).strftime("%Y-%m-%d")
    return dict(now=now, today=today, medications=meds, prescriptions=recipes, agenda=agenda(db, user, today, now),
                unread_alerts=db.execute("SELECT count(*) FROM alerts WHERE user_id=? AND read=0", (user["id"],)).fetchone()[0])


def history(db, user_id, ident):
    owned(db, "medications", ident, user_id)
    movements = [dict(r) for r in db.execute("SELECT * FROM stock_movements WHERE medication_id=? ORDER BY id DESC LIMIT 100", (ident,))]
    doses = [dict(r) for r in db.execute("SELECT * FROM doses WHERE medication_id=? ORDER BY scheduled_at DESC LIMIT 100", (ident,))]
    for row in movements + doses:
        row["amount"] /= SCALE
    for row in doses:
        row['expected_amount'] /= SCALE
    return dict(movements=movements, doses=doses)


def settings_save(db, user, data):
    tz = text(data.get("timezone", user["timezone"]), "Zona horaria", 100, True)
    zone(tz)
    topic = text(data.get("ntfy_topic", ""), "Tema ntfy", 100)
    import re
    if topic and not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", topic):
        raise Invalid("El tema ntfy debe tener entre 16 y 100 letras, números, guiones o guiones bajos.")
    enabled = boolean(data.get("ntfy_enabled", False), "Avisos ntfy")
    if enabled and not topic:
        raise Invalid("Indica un tema ntfy.")
    update(db, "users", user["id"], dict(timezone=tz, ntfy_topic=topic, ntfy_enabled=enabled,
            stock_alerts=boolean(data.get("stock_alerts", True), "Avisos de existencias"),
            prescription_alerts=boolean(data.get("prescription_alerts", True), "Avisos de recetas")))
    return public_user(db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())


def export_data(db, user):
    meds = [dict(r) for r in db.execute("SELECT * FROM medications WHERE user_id=?", (user["id"],))]
    recipes = [dict(r) for r in db.execute("SELECT * FROM prescriptions WHERE user_id=?", (user["id"],))]
    doses = [dict(r) for r in db.execute("SELECT d.* FROM doses d JOIN medications m ON m.id=d.medication_id WHERE m.user_id=?", (user["id"],))]
    movements = [dict(r) for r in db.execute("SELECT s.* FROM stock_movements s JOIN medications m ON m.id=s.medication_id WHERE m.user_id=?", (user["id"],))]
    links = [dict(r) for r in db.execute('SELECT l.* FROM medicine_links l JOIN medications m ON m.id=l.medication_id WHERE m.user_id=?', (user['id'],))]
    return dict(format="pastillas", version=3, exported_at=int(time.time()), quantity_scale=SCALE,
                timezone=user["timezone"], medications=meds, prescriptions=recipes, doses=doses, stock_movements=movements,
                medicine_links=links)


def create_user(db, data):
    name, password = credentials(data)
    return insert(db, "users", dict(username=name, password=hash_password(password), ntfy_topic="pastillas-" + secrets.token_hex(12)))
