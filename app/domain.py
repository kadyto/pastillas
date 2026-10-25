"""Pautas y existencias. Cantidades en milésimas, fechas UTC y zona IANA."""
import json
import math
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
SCALE = 1000


class Invalid(ValueError):
    pass


def text(value, label, limit=200, required=False):
    if not isinstance(value, str):
        raise Invalid(f"{label}: introduce texto.")
    value = value.strip()
    if len(value) > limit or (required and not value):
        raise Invalid(f"{label}: obligatorio, máximo {limit} caracteres." if required else f"{label}: máximo {limit} caracteres.")
    return value


def quantity(value, label="Cantidad", positive=False):
    if isinstance(value, bool):
        raise Invalid(f"{label}: introduce un número.")
    try:
        number = Decimal(str(value))
        scaled = number * SCALE
        if not number.is_finite() or scaled != scaled.to_integral_value() or abs(scaled) > 10**12:
            raise Invalid(f"{label}: máximo 3 decimales y 1.000 millones de unidades.")
        result = int(scaled)
    except (InvalidOperation, ValueError, TypeError):
        raise Invalid(f"{label}: introduce un número válido.") from None
    if positive and result <= 0:
        raise Invalid(f"{label}: debe ser mayor que cero.")
    return result


def zone(value):
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise Invalid("Zona horaria no válida; utiliza una zona IANA, como Europe/Madrid.") from None


def timestamp(value, label="Fecha", optional=False):
    if optional and value in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError()
        if not 2000 <= dt.year <= 2100:
            raise ValueError()
        return int(dt.timestamp())
    except (ValueError, TypeError, OverflowError):
        raise Invalid(f"{label}: fecha válida con zona horaria, entre 2000 y 2100.") from None


def date(value, label="Fecha de renovación"):
    if value in (None, ""):
        return None
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        if not 2000 <= dt.year <= 2100:
            raise ValueError()
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        raise Invalid(f"{label} no válida.") from None


def local_timestamp(value, tz, label, optional=False):
    if optional and value in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None or not 2000 <= dt.year <= 2100:
            raise ValueError()
        local = dt.replace(tzinfo=zone(tz), fold=0)
        at = int(local.timestamp())
        if datetime.fromtimestamp(at, zone(tz)).replace(tzinfo=None) != dt:
            raise Invalid(f"{label}: esa hora no existe por el cambio de horario. Selecciona otra hora.")
        return at
    except Invalid:
        raise
    except (ValueError, TypeError):
        raise Invalid(f"{label}: fecha y hora local no válidas.") from None


def boolean(value, label):
    if not isinstance(value, bool):
        raise Invalid(f"{label}: valor no válido.")
    return int(value)


def medication_input(data, default_zone):
    tz = text(data.get("timezone", default_zone), "Zona horaria", 100, True)
    zone(tz)
    schedule = data.get("schedule", "interval")
    if schedule not in ("interval", "daily", "as_needed"):
        raise Invalid("Pauta no válida.")
    try:
        hours = float(data.get("interval_hours", 24))
    except (TypeError, ValueError):
        raise Invalid("Intervalo no válido.") from None
    if not math.isfinite(hours) or hours < 1 or hours > 720 or hours * 3600 != int(hours * 3600):
        raise Invalid("El intervalo debe ser de 1 a 720 horas.")
    times = data.get("times", [])
    if not isinstance(times, list) or len(times) > 24 or any(not isinstance(t, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in times):
        raise Invalid("Horas no válidas; utiliza HH:MM.")
    if schedule == "daily" and not times:
        raise Invalid("Indica al menos una hora de toma.")
    start = local_timestamp(data["start_local"], tz, "Primera toma") if "start_local" in data else timestamp(data.get("start_at"), "Primera toma")
    end = local_timestamp(data["end_local"], tz, "Fin del tratamiento", True) if "end_local" in data else timestamp(data.get("end_at"), "Fin del tratamiento", True)
    if end is not None and end < start:
        raise Invalid("El fin debe ser posterior al inicio.")
    try:
        warning = int(data.get("warning_days", 7))
    except (TypeError, ValueError):
        raise Invalid("Días de aviso no válidos.") from None
    if not 0 <= warning <= 365:
        raise Invalid("Los días de aviso deben estar entre 0 y 365.")
    prescription_id = data.get("prescription_id") or None
    if prescription_id is not None and (type(prescription_id) is not int or prescription_id < 1):
        raise Invalid("Receta no válida.")
    return dict(
        name=text(data.get("name", ""), "Nombre", required=True),
        brand=text(data.get("brand", ""), "Marca"),
        form=text(data.get("form", "Pastillas"), "Presentación", 100, True),
        strength=text(data.get("strength", ""), "Concentración", 100),
        unit=text(data.get("unit", "pastillas"), "Unidad de existencias", 50, True),
        dose=quantity(data.get("dose", 1), "Cantidad por toma", True),
        schedule=schedule, interval_hours=hours, times=json.dumps(sorted(set(times))),
        start_at=start, end_at=end, timezone=tz,
        active=boolean(data.get("active", True), "Activo"),
        reminders=boolean(data.get("reminders", True), "Avisos"), warning_days=warning,
        prescription_id=prescription_id,
        instructions=text(data.get("instructions", ""), "Indicaciones", 4000),
        expiry_date=date(data.get("expiry_date"), "Fecha de caducidad"),
    )


def prescription_input(data):
    return dict(title=text(data.get("title", ""), "Nombre de la receta", required=True),
                doctor=text(data.get("doctor", ""), "Profesional"),
                reference=text(data.get("reference", ""), "Referencia"),
                renewal_date=date(data.get("renewal_date")),
                notes=text(data.get("notes", ""), "Notas", 4000))


def occurrences(med, after, before, limit=1000):
    """24 h = un día local; otros intervalos = horas reales; horas fijas = reloj local."""
    if not med["active"] or med["schedule"] == "as_needed" or before < med["start_at"]:
        return []
    after = max(after, med["start_at"])
    if med["end_at"] is not None:
        before = min(before, med["end_at"])
    if after > before:
        return []
    daily_interval = med["schedule"] == "interval" and med["interval_hours"] == 24
    # El corte conserva la pauta antigua y sus registros anteriores a la actualización.
    daily_from = med["daily_from"] if "daily_from" in med.keys() else 0
    tz = zone(med["timezone"])
    anchor = datetime.fromtimestamp(med["start_at"], tz)
    # Una toma antigua de las 00:30 puede haberse adelantado al día anterior.
    # El corte corresponde al número de día de la pauta, no al instante desplazado.
    legacy_until = (med["start_at"] + (datetime.fromtimestamp(daily_from, tz).date() - anchor.date()).days * 86400
                    if daily_interval and daily_from else 0)
    result = []
    if med["schedule"] == "interval" and (not daily_interval or after < legacy_until):
        step = int(med["interval_hours"] * 3600)
        first = med["start_at"] + max(0, (after - med["start_at"] + step - 1) // step) * step
        end = min(before, legacy_until - 1) if daily_interval else before
        result = list(range(first, min(end + 1, first + step * limit), step))
        if not daily_interval or before < daily_from or len(result) >= limit:
            return result
    if daily_interval:
        after = max(after, daily_from)
    day = datetime.fromtimestamp(after, tz).date()
    last = datetime.fromtimestamp(before, tz).date()
    times = [anchor.strftime("%H:%M:%S")] if daily_interval else json.loads(med["times"])
    while day <= last and len(result) < limit:
        for clock in times:
            hour, minute, *seconds = map(int, clock.split(":"))
            local = datetime(day.year, day.month, day.day, hour, minute, seconds[0] if seconds else 0, tzinfo=tz)
            # Hora inexistente: se desplaza hacia delante al cambiar a horario de verano.
            at = med["start_at"] if daily_interval and day == anchor.date() else int(local.timestamp())
            if after <= at <= before and at not in result:
                result.append(at)
                if len(result) >= limit:
                    break
        day += timedelta(days=1)
    return sorted(result)


def nth_occurrence(med, after, index):
    if not med["active"] or med["schedule"] == "as_needed":
        return None
    daily_interval = med["schedule"] == "interval" and med["interval_hours"] == 24
    if med["schedule"] == "interval" and not daily_interval:
        first = occurrences(med, after, after + 720 * 3600, 1)
        at = first[0] + int(med["interval_hours"] * 3600) * index if first else None
        if at is not None and at > 4133980799:  # 2100-12-31 UTC
            return None
        return at if at is not None and (med["end_at"] is None or at <= med["end_at"]) else None
    # Se cuentan días locales para respetar los saltos de hora incluso en pautas múltiples.
    tz = zone(med["timezone"])
    day = datetime.fromtimestamp(max(after, med["start_at"]), tz).date()
    last_day = datetime.fromtimestamp(med["end_at"], tz).date() if med["end_at"] is not None else datetime(2100, 12, 31).date()
    max_per_day = 2 if daily_interval else len(json.loads(med["times"]))
    if index >= max(0, (last_day - day).days + 1) * max_per_day:
        return None
    while day.year <= 2100:
        day_start = int(datetime.combine(day, datetime.min.time(), tz).timestamp())
        if med["end_at"] is not None and day_start > med["end_at"]:
            return None
        day_end = int(datetime.combine(day + timedelta(days=1), datetime.min.time(), tz).timestamp()) - 1
        slots = occurrences(med, max(after, day_start), day_end, 24)
        if index < len(slots):
            return slots[index]
        index -= len(slots)
        day += timedelta(days=1)
    return None


def forecast(med, now, resolved=()):
    if not med["active"] or med["schedule"] == "as_needed":
        return dict(doses_left=med["stock"] // med["dose"], runs_out_at=None, days_left=None, stock_warning=False, enough_until_end=False)
    # Los registros adelantados se saltan, pues su consumo ya se descontó del stock.
    count = med["stock"] // med["dose"]
    missing = nth_occurrence(med, now, count)
    if resolved:
        for at in sorted(resolved):
            if at >= now and missing is not None and at <= missing:
                count += 1
                missing = nth_occurrence(med, now, count)
    days = max(0, (missing - now) / 86400) if missing is not None else None
    return dict(doses_left=med["stock"] // med["dose"], runs_out_at=missing,
                days_left=round(days, 2) if days is not None else None,
                stock_warning=days is not None and days <= med["warning_days"],
                enough_until_end=med["end_at"] is not None and missing is None)


def serialize_med(med, now, resolved=()):
    result = dict(med)
    result["dose"] /= SCALE
    result["stock"] /= SCALE
    result["times"] = json.loads(result["times"])
    result.update(forecast(med, now, resolved))
    return result
