import sqlite3
from pathlib import Path
from unittest.mock import patch

from app import alerts, domain, inventory, service
from app.db import connect, initialize
from test_pastillas import DatabaseTests


at = domain.timestamp


class DailyIntervalTests(DatabaseTests):
    def test_twentyfour_hours_keeps_original_clock_in_both_seasons(self):
        cases = [
            ('2026-10-24T21:30:00Z', ['2026-10-24T21:30:00Z', '2026-10-25T22:30:00Z', '2026-10-26T22:30:00Z'], 25),
            ('2026-03-28T22:30:00Z', ['2026-03-28T22:30:00Z', '2026-03-29T21:30:00Z', '2026-03-30T21:30:00Z'], 23),
            ('2026-10-24T06:00:00Z', ['2026-10-24T06:00:00Z', '2026-10-25T07:00:00Z', '2026-10-26T07:00:00Z'], 25),
            ('2026-03-28T07:00:00Z', ['2026-03-28T07:00:00Z', '2026-03-29T06:00:00Z', '2026-03-30T06:00:00Z'], 23),
        ]
        for start, expected, hours in cases:
            with self.subTest(start=start):
                med = self.med(interval_hours=24, start_at=start, dose=1, stock=2)
                expected = list(map(at, expected))
                self.assertEqual(domain.occurrences(med, expected[0], expected[-1]), expected)
                self.assertEqual(expected[1] - expected[0], hours * 3600)
                self.assertEqual([domain.nth_occurrence(med, expected[0], i) for i in range(3)], expected)
                self.assertEqual(domain.forecast(med, expected[0])['runs_out_at'], expected[2])
                self.assertEqual(domain.occurrences(med, expected[0], expected[-1], 1), expected[:1])
                self.assertEqual(domain.occurrences(med, expected[0]+1, expected[-1]), expected[1:])
                ended = dict(med, end_at=expected[1])
                self.assertIsNone(domain.nth_occurrence(ended, expected[0], 2))

    def test_other_intervals_still_count_elapsed_hours(self):
        for hours in (6, 8, 12, 48):
            with self.subTest(hours=hours):
                start = at('2026-10-24T21:30:00Z')
                med = self.med(interval_hours=hours, start_at='2026-10-24T21:30:00Z')
                expected = list(range(start, start + 96*3600+1, hours*3600))
                self.assertEqual(domain.occurrences(med, start, expected[-1]), expected)
                self.assertEqual(domain.nth_occurrence(med, start, len(expected)-1), expected[-1])

    def test_gap_and_repeated_hour_keep_one_dose_and_recover_original_clock(self):
        cases = [
            ['2026-03-28T01:30:00Z', '2026-03-29T01:30:00Z', '2026-03-30T00:30:00Z'],
            ['2026-10-24T00:30:00Z', '2026-10-25T00:30:00Z', '2026-10-26T01:30:00Z'],
            ['2026-10-25T01:30:00Z', '2026-10-26T01:30:00Z'],
        ]
        for values in cases:
            with self.subTest(values=values):
                med = self.med(interval_hours=24, start_at=values[0])
                expected = list(map(at, values))
                self.assertEqual(domain.occurrences(med, expected[0], expected[-1]), expected)
                self.assertEqual(domain.nth_occurrence(med, expected[0], len(values)-1), expected[-1])

    def test_clock_uses_medication_zone_and_preserves_seconds(self):
        med = self.med(interval_hours=24, timezone='Europe/Madrid', start_at='2026-10-24T21:30:45Z')
        self.assertEqual(domain.nth_occurrence(med, med['start_at'], 1), at('2026-10-25T22:30:45Z'))
        utc = dict(med, timezone='Etc/UTC')
        self.assertEqual(domain.nth_occurrence(utc, med['start_at'], 1), at('2026-10-25T21:30:45Z'))


class DailyUpgradeTests(DatabaseTests):
    def old_med(self):
        med = self.med(interval_hours=24, start_at='2026-10-24T21:30:00Z', dose=1, stock=10)
        # La pauta anterior contaba siempre segundos, incluso durante el cambio.
        self.db.execute('UPDATE medications SET daily_from=? WHERE id=?', (at('2100-01-01T00:00:00Z'), med['id']))
        self.db.commit()
        return med['id']

    def migrate(self, now):
        self.db.execute('ALTER TABLE medications DROP COLUMN daily_from')
        self.db.execute('PRAGMA user_version=5')
        self.db.commit()
        self.db.close()
        with patch('app.db.time.time', return_value=now):
            initialize(self.path)
        self.db = connect(self.path)

    def test_update_before_todays_dose_restores_original_time_and_reminder(self):
        ident = self.old_med()
        now = at('2026-10-25T20:00:00Z')
        inventory.sync_due(self.db, now)
        before = service.history(self.db, self.user_id, ident)
        self.migrate(now)
        med = service.owned(self.db, 'medications', ident, self.user_id)
        self.assertEqual(med['daily_from'], at('2026-10-24T22:00:00Z'))
        self.assertEqual(med['stock'], 9000)
        self.assertEqual(service.history(self.db, self.user_id, ident), before)
        early = at('2026-10-25T21:30:00Z')  # antiguo aviso a las 22:30
        alerts.generate(self.db, early)
        self.assertEqual(self.db.execute("SELECT count(*) FROM alerts WHERE kind='dose'").fetchone()[0], 0)
        self.assertEqual(service.owned(self.db, 'medications', ident, self.user_id)['stock'], 9000)
        corrected = at('2026-10-25T22:30:00Z')  # 23:30 locales
        alerts.generate(self.db, corrected)
        alerts.generate(self.db, corrected+30)
        row = self.db.execute("SELECT * FROM alerts WHERE kind='dose'").fetchone()
        self.assertTrue(row['message'].startswith('23:30'))
        self.assertEqual(self.db.execute("SELECT count(*) FROM alerts WHERE kind='dose'").fetchone()[0], 1)
        self.assertEqual(service.owned(self.db, 'medications', ident, self.user_id)['stock'], 8000)
        today = service.agenda(self.db, self.user, '2026-10-25', corrected)
        self.assertEqual([r['scheduled_at'] for r in today], [corrected])
        with sqlite3.connect(self.path + '.pre-v6.sqlite') as backup:
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 5)
            self.assertEqual(backup.execute('SELECT stock FROM medications').fetchone()[0], 9000)
        self.assertEqual(Path(self.path + '.pre-v6.sqlite').stat().st_mode & 0o777, 0o600)

    def test_update_after_todays_early_dose_does_not_charge_it_again(self):
        for status in ('taken', 'skipped'):
            with self.subTest(status=status):
                ident = self.old_med()
                early = at('2026-10-25T21:30:00Z')
                service.record_dose(self.db, self.user_id, ident, dict(scheduled_at=early, status=status), early)
                self.db.commit()
                before = service.history(self.db, self.user_id, ident)
                stock = service.owned(self.db, 'medications', ident, self.user_id)['stock']
                self.migrate(early+600)
                med = service.owned(self.db, 'medications', ident, self.user_id)
                self.assertEqual(med['daily_from'], at('2026-10-25T23:00:00Z'))
                alerts.generate(self.db, at('2026-10-25T22:30:00Z'))
                self.assertEqual(service.owned(self.db, 'medications', ident, self.user_id)['stock'], stock)
                self.assertEqual(service.history(self.db, self.user_id, ident), before)
                today = service.agenda(self.db, self.user, '2026-10-25', early+3600)
                self.assertEqual([r['scheduled_at'] for r in today if r['medication_id']==ident], [early])
                tomorrow = at('2026-10-26T22:30:00Z')
                self.assertEqual(domain.nth_occurrence(med, early+3600, 0), tomorrow)
                alerts.generate(self.db, tomorrow)
                self.assertEqual(service.owned(self.db, 'medications', ident, self.user_id)['stock'], stock-1000)
                before_restart = service.history(self.db, self.user_id, ident)
                initialize(self.path)
                inventory.sync_due(self.db, tomorrow+60)
                self.assertEqual(service.history(self.db, self.user_id, ident), before_restart)
                self.assertEqual(service.owned(self.db, 'medications', ident, self.user_id)['daily_from'], med['daily_from'])

    def test_offline_recovery_preserves_old_days_and_new_clock_after_upgrade(self):
        ident = self.old_med()
        self.migrate(at('2026-10-25T20:00:00Z'))
        inventory.sync_due(self.db, at('2026-10-26T22:30:00Z'))
        inventory.sync_due(self.db, at('2026-10-26T22:30:00Z'))
        rows = self.db.execute('SELECT scheduled_at FROM doses WHERE medication_id=? ORDER BY scheduled_at', (ident,)).fetchall()
        self.assertEqual([r[0] for r in rows], list(map(at, ['2026-10-24T21:30:00Z', '2026-10-25T22:30:00Z', '2026-10-26T22:30:00Z'])))
        self.assertEqual(service.owned(self.db, 'medications', ident, self.user_id)['stock'], 7000)
        self.assertEqual(self.db.execute('SELECT sum(amount) FROM stock_movements WHERE medication_id=?', (ident,)).fetchone()[0], 7000)

    def test_midnight_dose_does_not_repeat_its_shifted_occurrence_before_cutover(self):
        ident = self.med(interval_hours=24, start_at='2026-10-23T22:30:00Z', dose=1, stock=10)['id']
        self.db.execute('UPDATE medications SET daily_from=? WHERE id=?', (at('2100-01-01T00:00:00Z'), ident))
        self.db.commit()
        inventory.sync_due(self.db, at('2026-10-25T20:00:00Z'))
        self.migrate(at('2026-10-25T20:00:00Z'))
        inventory.sync_due(self.db, at('2026-10-25T22:30:00Z')) # antigua toma de mañana a las 23:30 de hoy
        self.assertEqual(service.owned(self.db, 'medications', ident, self.user_id)['stock'], 8000)
        inventory.sync_due(self.db, at('2026-10-25T23:30:00Z')) # nueva toma, a las 00:30 de mañana
        self.assertEqual(service.owned(self.db, 'medications', ident, self.user_id)['stock'], 7000)
        rows = self.db.execute('SELECT scheduled_at FROM doses WHERE medication_id=? ORDER BY scheduled_at', (ident,)).fetchall()
        self.assertEqual([r[0] for r in rows], list(map(at, ['2026-10-23T22:30:00Z', '2026-10-24T22:30:00Z', '2026-10-25T23:30:00Z'])))

    def test_already_shifted_tomorrow_dose_is_not_charged_again_after_midnight(self):
        ident = self.med(interval_hours=24, start_at='2026-10-23T22:30:00Z', dose=1, stock=10)['id']
        self.db.execute('UPDATE medications SET daily_from=? WHERE id=?', (at('2100-01-01T00:00:00Z'), ident))
        self.db.commit()
        inventory.sync_due(self.db, at('2026-10-25T22:40:00Z'))
        self.migrate(at('2026-10-25T22:40:00Z'))
        med = service.owned(self.db, 'medications', ident, self.user_id)
        self.assertEqual(domain.nth_occurrence(med, at('2026-10-25T22:40:00Z'), 0), at('2026-10-26T23:30:00Z'))
        inventory.sync_due(self.db, at('2026-10-25T23:30:00Z'))
        self.assertEqual(service.owned(self.db, 'medications', ident, self.user_id)['stock'], 7000)
