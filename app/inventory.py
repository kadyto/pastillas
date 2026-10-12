"""Descuentos de tomas previstas. Una estimación de stock, no prueba de ingesta."""
import time

from .domain import occurrences


def sync_due(db, now=None, user_id=None, medication_id=None):
    """Recupera tomas vencidas una sola vez, también después de apagar el NAS.

    El cursor persistente impide consumir períodos anteriores al alta/migración
    o repetir descuentos después de omitir una toma, contar el stock o reiniciar.
    Toda la actualización comparte el bloqueo de compras y correcciones.
    """
    now = int(time.time()) if now is None else now
    own_transaction = not db.in_transaction
    if own_transaction:
        db.execute('BEGIN IMMEDIATE')
    try:
        clauses = ['active=1', "schedule<>'as_needed'", 'auto_cursor<?']
        params = [now]
        if user_id is not None:
            clauses.append('user_id=?');params.append(user_id)
        if medication_id is not None:
            clauses.append('id=?');params.append(medication_id)
        meds = db.execute('SELECT * FROM medications WHERE ' + ' AND '.join(clauses),params).fetchall()
        for med in meds:
            cursor, stock = med['auto_cursor'], med['stock']
            while True:
                slots = occurrences(med,cursor+1,now,1000)
                if not slots:
                    break
                for at in slots:
                    if db.execute('SELECT 1 FROM doses WHERE medication_id=? AND scheduled_at=?',(med['id'],at)).fetchone():
                        continue
                    amount = min(stock,med['dose'])
                    dose_id = db.execute("INSERT INTO doses(medication_id,scheduled_at,recorded_at,status,amount,note,automatic,expected_amount) "
                                         "VALUES(?,?,?,'taken',?,'Toma asumida según la pauta',1,?)",
                                         (med['id'],at,now,amount,med['dose'])).lastrowid
                    db.execute("INSERT INTO stock_movements(medication_id,amount,kind,recorded_at,note,dose_id) VALUES(?,?,'automatic_dose',?,?,?)",
                               (med['id'],-amount,now,'Descuento automático' if amount == med['dose'] else 'Stock registrado insuficiente para la toma prevista',dose_id))
                    stock -= amount
                cursor = slots[-1]
                if len(slots) < 1000:
                    break
            db.execute('UPDATE medications SET stock=?,auto_cursor=? WHERE id=?',(stock,now,med['id']))
        if own_transaction:
            db.commit()
    except Exception:
        if own_transaction:
            db.rollback()
        raise
