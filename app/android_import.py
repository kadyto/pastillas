"""Importa copias JSON de Pastillas sin servidor ni sobrescribir el botiquín local."""
import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal

from . import domain, service


def integer(value, label, low=0, high=10**12):
    if type(value) is not int or not low <= value <= high:
        raise domain.Invalid(label + ': valor no válido en la copia.')
    return value


def flag(value):
    if type(value) not in (bool, int) or value not in (0, 1):
        raise domain.Invalid('Indicador no válido en la copia.')
    return bool(value)


def instant(value):
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(integer(value, 'Fecha', 946684800, 4133980799), timezone.utc).isoformat()
    except (ValueError, OverflowError):
        raise domain.Invalid('Fecha no válida en la copia.') from None


def import_data(db, user, raw, now=None):
    now = int(time.time()) if now is None else now
    try:
        data = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError):
        raise domain.Invalid('El archivo no contiene una copia JSON válida.') from None
    if not isinstance(data, dict) or data.get('format') != 'pastillas' or data.get('version') not in (3, 4) or data.get('quantity_scale') != domain.SCALE:
        raise domain.Invalid('Utiliza una exportación JSON de Pastillas compatible (versión 3 o 4).')
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    try:
        if db.execute('SELECT 1 FROM android_imports WHERE digest=?', (digest,)).fetchone():
            raise domain.Invalid('Esta copia ya se ha importado. No se han duplicado los datos.')
        for table in ('prescriptions', 'medications', 'doses', 'stock_movements', 'medicine_links'):
            if not isinstance(data.get(table, []), list) or any(not isinstance(row, dict) for row in data.get(table, [])):
                raise domain.Invalid('La estructura de la copia no es válida.')
        recipes, medications, doses = {}, {}, {}
        for row in data.get('prescriptions', []):
            old = integer(row.get('id'), 'Identificador', 1)
            if old in recipes:
                raise domain.Invalid('La copia contiene recetas duplicadas.')
            recipes[old] = service.insert(db, 'prescriptions', dict(domain.prescription_input(row), user_id=user['id']))
        for row in data.get('medications', []):
            old = integer(row.get('id'), 'Identificador', 1)
            if old in medications:
                raise domain.Invalid('La copia contiene medicamentos duplicados.')
            recipe = row.get('prescription_id')
            if recipe is not None and recipe not in recipes:
                raise domain.Invalid('La copia contiene una receta vinculada que no existe.')
            values = dict(row, dose=Decimal(integer(row.get('dose'), 'Dosis', 1)) / domain.SCALE,
                          times=json.loads(row['times']) if isinstance(row.get('times'), str) else row.get('times', []),
                          start_at=instant(row.get('start_at')), end_at=instant(row.get('end_at')),
                          active=flag(row.get('active', 1)), reminders=flag(row.get('reminders', 1)),
                          prescription_id=recipes.get(recipe))
            fields = domain.medication_input(values, data.get('timezone', user['timezone']))
            fields.update(user_id=user['id'], stock=integer(row.get('stock'), 'Existencias'),
                          created_at=integer(row.get('created_at', now), 'Fecha', 946684800, 4133980799),
                          auto_cursor=min(integer(row.get('auto_cursor') or data.get('exported_at', now), 'Cursor'), now),
                          stock_verified_at=row.get('stock_verified_at'))
            if fields['stock_verified_at'] is not None:
                instant(fields['stock_verified_at'])
            medications[old] = service.insert(db, 'medications', fields)
        for row in data.get('doses', []):
            old = integer(row.get('id'), 'Toma', 1)
            if old in doses or row.get('medication_id') not in medications or row.get('status') not in ('taken', 'skipped'):
                raise domain.Invalid('La copia contiene una toma no válida.')
            instant(row.get('scheduled_at'));instant(row.get('recorded_at'))
            doses[old] = service.insert(db, 'doses', dict(medication_id=medications[row['medication_id']],
                scheduled_at=row['scheduled_at'], recorded_at=row['recorded_at'], status=row['status'],
                amount=integer(row.get('amount'), 'Cantidad'), note=domain.text(row.get('note', ''), 'Nota', 4000),
                automatic=flag(row.get('automatic', 0)), expected_amount=integer(row.get('expected_amount', row['amount']), 'Cantidad prevista')))
        for row in data.get('stock_movements', []):
            if row.get('medication_id') not in medications or (row.get('dose_id') is not None and row['dose_id'] not in doses):
                raise domain.Invalid('La copia contiene un movimiento sin medicamento o toma.')
            if row.get('dose_id') is not None:
                owner = db.execute('SELECT medication_id FROM doses WHERE id=?', (doses[row['dose_id']],)).fetchone()[0]
                if owner != medications[row['medication_id']]:
                    raise domain.Invalid('El movimiento no corresponde a su toma.')
            instant(row.get('recorded_at'))
            price = row.get('price_cents')
            if price is not None:
                integer(price, 'Precio', 0, 10**12)
            service.insert(db, 'stock_movements', dict(medication_id=medications[row['medication_id']],
                dose_id=doses.get(row.get('dose_id')), amount=integer(row.get('amount'), 'Movimiento', -10**12),
                kind=domain.text(row.get('kind', ''), 'Movimiento', 50, True), recorded_at=row['recorded_at'],
                note=domain.text(row.get('note', ''), 'Nota', 4000), price_cents=price))
        from .medicine_info import registry, national_code, vademecum_url
        linked = set()
        for row in data.get('medicine_links', []):
            old = row.get('medication_id')
            if old not in medications or old in linked:
                raise domain.Invalid('La copia contiene una vinculación no válida.')
            linked.add(old)
            service.insert(db, 'medicine_links', dict(medication_id=medications[old],
                nregistro=registry(row.get('nregistro', '')), cn=national_code(row.get('cn', '')),
                vademecum_url=vademecum_url(row.get('vademecum_url', '')),
                cima_name=domain.text(row.get('cima_name', ''), 'Nombre CIMA', 500, True),
                presentation_name=domain.text(row.get('presentation_name', ''), 'Envase', 1000)))
        db.execute('INSERT INTO android_imports VALUES(?,?)', (digest, now))
        db.commit()
        return dict(medications=len(medications), prescriptions=len(recipes), doses=len(doses))
    except Exception:
        db.rollback()
        raise
