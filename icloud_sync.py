"""Opt-in iCloud CalDAV bridge. Credentials live in memory, never in SQLite.

Only stable, installation-owned UIDs are writable. ETags protect cloud edits.
No background access occurs before local Admin explicitly selects calendars.
"""
import travel_calendar
import travel_reminders
import hashlib
import json
import logging
import secrets
import threading
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse, urljoin
from zoneinfo import ZoneInfo


class CloudError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def apple_url(value):
    value = str(value)
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not (parsed.hostname == 'icloud.com' or (parsed.hostname or '').endswith('.icloud.com')) or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.query or parsed.fragment:
        raise CloudError('iCloud returned an unexpected calendar address. Connection stopped.')
    return value


class AppleClient:
    def __init__(self, username, password):
        try:
            import caldav
        except ImportError:
            raise CloudError('Install iCloud support on the PC first, then restart Align.') from None
        # Never emit request bodies, auth negotiations or account URLs to logs.
        logging.getLogger('caldav').setLevel(logging.CRITICAL)
        self.client = caldav.DAVClient(url='https://caldav.icloud.com/', username=username,
            password=password, timeout=25, ssl_verify_cert=True, enable_rfc6764=False)
        # Validate each redirect before following it. iCloud can move discovery
        # to a regional HTTPS host; credentials must never leave Apple's domain.
        original = self.client.session.request
        def guarded(method, url, **kwargs):
            kwargs['allow_redirects'] = False
            for _ in range(5):
                apple_url(url)
                response = original(method, url, **kwargs)
                if response.status_code not in (301,302,303,307,308): return response
                url = apple_url(urljoin(str(url),response.headers.get('Location','')))
            raise CloudError('iCloud returned too many redirects. Connection stopped.')
        self.client.session.request = guarded
        self.calendars = {}

    def discover(self):
        calendars = self.client.get_principal().calendars()
        self.calendars = {apple_url(c.url): c for c in calendars}
        return [{'id':digest(url), 'name':c.get_display_name() or 'iCloud Calendar'} for url,c in self.calendars.items()]

    def create_calendar(self, name):
        calendar = self.client.get_principal().make_calendar(name=name)
        url = apple_url(calendar.url)
        self.calendars[url] = calendar
        return {'id': digest(url), 'name': calendar.get_display_name() or name, 'url': url}

    def get(self, url):
        response = self.client.request(apple_url(url), 'GET')
        if response.status == 404:
            return None
        if response.status != 200:
            raise CloudError('Could not read an iCloud event. Nothing was overwritten.')
        return response.raw, response.headers.get('ETag', '')

    def put(self, url, payload, etag=None):
        headers = {'Content-Type':'text/calendar; charset=utf-8', 'If-Match':etag} if etag else {'Content-Type':'text/calendar; charset=utf-8', 'If-None-Match':'*'}
        response = self.client.request(apple_url(url), 'PUT', payload, headers)
        if response.status == 412:
            raise CloudError('An Align event changed in iCloud. It was not overwritten. Restore it in iCloud or reconnect after reviewing the conflict.')
        if response.status not in (200,201,204):
            raise CloudError('iCloud did not accept the event. Check calendar write permission.')
        return response.headers.get('ETag','')

    def delete(self, url, etag):
        if not etag:
            raise CloudError('Cannot safely remove an iCloud event without its revision.')
        response = self.client.request(apple_url(url), 'DELETE', headers={'If-Match':etag})
        if response.status not in (200,204,404):
            raise CloudError('An iCloud event changed or could not be removed. It was left untouched.')

    def events(self, url, start, end):
        return [event.get_icalendar_component() for event in self.calendars[url].search(event=True, start=start, end=end, expand=True)]

    def close(self):
        self.client.close()


def event_content(component):
    """Compare semantic content, excluding server-managed timestamp fields."""
    import copy
    component = copy.deepcopy(component)
    for key in ('DTSTAMP','LAST-MODIFIED','CREATED','SEQUENCE'):
        component.pop(key, None)
    return digest(component.to_ical().decode())


def read_owned(raw, uid):
    from icalendar import Calendar
    events = list(Calendar.from_ical(raw).walk('VEVENT'))
    if len(events) != 1 or str(events[0].get('UID','')) != uid:
        raise CloudError('An event does not match Align’s saved identifier. It was left untouched.')
    return event_content(events[0])


def owned_component(raw, uid):
    from icalendar import Calendar
    events = list(Calendar.from_ical(raw).walk('VEVENT'))
    if len(events) != 1 or str(events[0].get('UID','')) != uid:
        raise CloudError('An event does not match Align’s saved identifier. It was left untouched.')
    return events[0]


def local_times(component):
    """Return (start, end, all_day) as naive Europe/London datetimes or dates."""
    zone = ZoneInfo('Europe/London')
    start = component.decoded('DTSTART')
    all_day = not isinstance(start, datetime)
    if component.get('DTEND'):
        end = component.decoded('DTEND')
    else:
        end = start + (component.decoded('DURATION') if component.get('DURATION') else timedelta(days=1 if all_day else 0))
    def local(value):
        if not isinstance(value, datetime):
            return value
        return value.astimezone(zone).replace(tzinfo=None) if value.tzinfo else value
    return local(start), local(end), all_day


def travel_block(event, uid, rules):
    """Build an optional travel block for a timed Section event."""
    from icalendar import Alarm, Calendar, Event
    if rules is None:
        return None
    zone = ZoneInfo('Europe/London')
    if event.get('all_day'):
        return None
    start = datetime.fromisoformat(event['start_at'])
    journey = travel_calendar.plan(event.get('notes'), start)
    if not journey or journey[0] >= start:
        return None
    item = Event()
    item.add('uid', uid)
    item.add('dtstamp', datetime.now(timezone.utc))
    item.add('dtstart', journey[0].replace(tzinfo=zone).astimezone(timezone.utc))
    item.add('dtend', start.replace(tzinfo=zone).astimezone(timezone.utc))
    destination = event.get('location') or event.get('title') or 'event'
    item.add('summary', 'Travel to ' + destination)
    item.add('description', f"Leave at {journey[0].strftime('%H:%M')} (about {journey[1]} minutes). Planned in Align.")
    item.add('transp', 'TRANSPARENT')
    item.add('status', 'CONFIRMED')
    alarm = Alarm()
    alarm.add('action', 'DISPLAY')
    alarm.add('description', travel_calendar.leave_alert_title(journey[0], destination))
    alarm.add('trigger', timedelta(0))
    item.add_component(alarm)
    calendar = Calendar(); calendar.add('version','2.0'); calendar.add('prodid','-//Align//iCloud Calendar//EN'); calendar.add_component(item)
    return calendar.to_ical(), event_content(item)


def organiser_event(event, uid):
    from icalendar import Calendar, Event, Alarm, vText
    zone = ZoneInfo('Europe/London')
    item = Event()
    item.add('uid', uid)
    item.add('dtstamp', datetime.now(timezone.utc))
    if event.get('all_day'):
        start = datetime.fromisoformat(event['start_at']).date()
        end = datetime.fromisoformat(event['end_at']).date()
        item.add('dtstart', start)
        item.add('dtend', end)
    else:
        start = datetime.fromisoformat(event['start_at']).replace(tzinfo=zone)
        end = datetime.fromisoformat(event['end_at']).replace(tzinfo=zone)
        item.add('dtstart', start.astimezone(timezone.utc))
        item.add('dtend', end.astimezone(timezone.utc))
    item.add('summary', event['title'])
    if event.get('location'):
        item.add('location', event['location'])
    item.add('description', travel_calendar.calendar_description(event.get('notes')))
    item.add('status', 'CONFIRMED')
    if not event.get('all_day'):
        rules = travel_reminders.rules(event.get('notes'))
        journey = travel_calendar.plan(event.get('notes'), start.replace(tzinfo=None))
        if journey:
            lead = int((start.replace(tzinfo=None) - journey[0]).total_seconds() // 60)
            duration = vText(f'PT{journey[1]}M'); duration.params['VALUE'] = 'DURATION'; item.add('x-apple-travel-duration', duration)
            title = travel_calendar.leave_alert_title(journey[0], event.get('title') or 'Event')
            if not any(r['minutes_before'] == lead for r in rules):
                rules.append({'title': title, 'minutes_before': lead})
        for rule in rules:
            alarm = Alarm(); alarm.add('action', 'DISPLAY'); alarm.add('description', rule['title'])
            alarm.add('trigger', timedelta(minutes=-rule['minutes_before'])); item.add_component(alarm)
    calendar = Calendar(); calendar.add('version','2.0'); calendar.add('prodid','-//Align//iCloud Calendar//EN'); calendar.add_component(item)
    return calendar.to_ical(), event_content(item)


def busy_event(event, owned_prefix):
    if str(event.get('UID','')).startswith(owned_prefix) or str(event.get('STATUS','')).upper() == 'CANCELLED' or str(event.get('TRANSP','')).upper() == 'TRANSPARENT':
        return None
    if not event.get('DTSTART'):
        return None
    start = event.decoded('DTSTART')
    all_day = not isinstance(start, datetime)
    end = event.decoded('DTEND') if event.get('DTEND') else start + (event.decoded('DURATION') if event.get('DURATION') else timedelta(days=1) if all_day else timedelta())
    zone = ZoneInfo('Europe/London')
    def local(value):
        if not isinstance(value,datetime):
            return datetime.combine(value,datetime.min.time())
        return value.astimezone(zone).replace(tzinfo=None) if value.tzinfo else value
    start, end = local(start), local(end)
    if end <= start:
        return None
    return (str(event.get('UID','')) + ':' + start.isoformat(), start.isoformat(),end.isoformat(),str(event.get('SUMMARY','iCloud event')),int(all_day),str(event.get('LOCATION',''))[:1000])


class ICloudSync:
    def __init__(self, app, factory=AppleClient):
        self.app, self.factory = app, factory
        self.lock = threading.RLock()
        self.client = None; self.options = []; self.account = ''; self.enabled = False
        self.last_sync = None; self.last_attempt = None; self.last_error = None
        self.consecutive_failures = 0; self.calendar_status = {}
        self.conflicts = []
        self.message = 'Not connected'; self.busy = False
        self.wake = threading.Event(); self.worker = None

    def status(self, private=False):
        retry_in = min(60 * (2 ** max(0, self.consecutive_failures - 1)), 900)
        result = {
            'connected': self.client is not None, 'enabled':self.enabled,
            'last_sync':self.last_sync, 'last_attempt':self.last_attempt,
            'last_error':self.last_error, 'retry_in_seconds':retry_in if self.last_error else None,
            'message':self.message, 'busy':self.busy,
            'conflicts':list(self.conflicts),
        }
        if private:
            result['calendars'] = self.options
            with self.app.db_connection() as c:
                row = c.execute('SELECT * FROM icloud_config WHERE id=1').fetchone()
                result['target'] = digest(row['target_url']) if row['target_url'] else ''
                result['read_ids'] = [digest(url) for url in json.loads(row['read_urls'])]
                selected = set(result['read_ids'])
                if result['target']:
                    selected.add(result['target'])
            result['calendars'] = [
                {**calendar, 'selected_for_sync': calendar['id'] in selected,
                 **self.calendar_status.get(calendar['id'], {'status':'not_checked','last_success':None,'event_count':None,'error':None})}
                for calendar in self.options
            ]
        return result

    def discover(self, username, password):
        if not isinstance(username,str) or '@' not in username or len(username)>254 or not isinstance(password,str) or not password or len(password)>256:
            raise CloudError('Enter your Apple Account email and an app-specific password.')
        with self.lock:
            if self.enabled:
                raise CloudError('Disconnect the current iCloud connection before signing in again.')
            client = self.factory(username.strip(),password)
            try:
                options = client.discover()
                account = digest(username.strip().casefold())
                with self.app.db_connection() as c:
                    old = c.execute('SELECT account_hash FROM icloud_config WHERE id=1').fetchone()[0]
                    if old and old != account and c.execute('SELECT 1 FROM icloud_items LIMIT 1').fetchone():
                        raise CloudError('This installation already syncs a different Align calendar. Reconnect the same iCloud account.')
                if self.client: self.client.close()
                self.client, self.options, self.account = client, options, account
                self.calendar_status = {}; self.last_error = None; self.consecutive_failures = 0
                self.message = 'Choose calendars and enable sync. No events have been changed.'
            except CloudError:
                client.close(); raise
            except Exception:
                client.close(); raise CloudError('iCloud sign-in failed. Check the Apple Account email, app-specific password, internet connection and iCloud Calendar access.') from None
        return self.status(True)

    def resume(self, username, password):
        """Reconnect an already-configured account after a beta server restart."""
        self.discover(username, password)
        with self.app.db_connection() as c:
            row = c.execute('SELECT target_url,read_urls,account_hash FROM icloud_config WHERE id=1').fetchone()
            target_url = row['target_url'] if row else ''
            read_urls = json.loads(row['read_urls']) if row and row['read_urls'] else []
        if not target_url:
            return self.status(True)
        urls = {digest(url): url for url in self.client.calendars}
        target_id = digest(target_url)
        read_ids = [digest(url) for url in read_urls if digest(url) in urls]
        if target_id not in urls:
            raise CloudError('The saved iCloud destination calendar is no longer available.')
        return self.configure(target_id, read_ids)

    def create_calendar(self, name):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
            raise CloudError('Give the calendar a name of up to 80 characters.')
        name = name.strip()
        with self.lock:
            if not self.client: raise CloudError('Connect iCloud first.')
            # Rediscover before creation so retrying a lost response reuses the calendar.
            self.options = self.client.discover()
            existing = [c for c in self.options if c['name'].casefold() == name.casefold()]
            if existing:
                created = existing[0]
            else:
                try:
                    created = self.client.create_calendar(name)
                    self.options.append(created)
                except Exception:
                    raise CloudError('Calendar creation could not be confirmed. Check connection and retry the same name; Align will reuse it if it exists.') from None
            self.message = 'Calendar ready. Select it as a destination or link it to an event category.'
            return {**self.status(True), 'created_calendar': created}

    def resolve_calendar(self, calendar_id):
        with self.lock:
            if not self.client:
                raise CloudError('Reconnect iCloud on the PC before linking a section.')
            urls = {digest(url):(url, self.client.calendars[url].get_display_name() or 'iCloud Calendar') for url in self.client.calendars}
            if calendar_id not in urls:
                raise CloudError('Choose a calendar from the currently connected iCloud account.')
            return urls[calendar_id]

    def configure(self, target_id, read_ids):
        with self.lock:
            if not self.client: raise CloudError('Connect your Apple Account on this PC first.')
            urls = {digest(url):url for url in self.client.calendars}
            if target_id not in urls or not isinstance(read_ids,list) or any(i not in urls for i in read_ids):
                raise CloudError('Select calendars from the current account.')
            with self.app.db_connection() as c:
                old = c.execute('SELECT target_url FROM icloud_config WHERE id=1').fetchone()[0]
                if old and old != urls[target_id] and c.execute('SELECT 1 FROM icloud_items LIMIT 1').fetchone():
                    raise CloudError('Align already manages events in its previous calendar. Keep that destination to avoid duplicates; moving linked events is not supported yet.')
                c.execute('UPDATE icloud_config SET account_hash=?,target_url=?,read_urls=? WHERE id=1', (self.account,urls[target_id],json.dumps([urls[i] for i in dict.fromkeys(read_ids)])))
            self.enabled = True; self.message = 'Sync starting…'
            self.last_error = None; self.consecutive_failures = 0
            if not self.worker or not self.worker.is_alive():
                self.worker = threading.Thread(target=self.run,daemon=True); self.worker.start()
            self.wake.set()
        return self.status(True)

    def disconnect(self):
        with self.lock:
            self.enabled = False
            if self.client: self.client.close()
            self.client = None; self.options = []; self.account = ''
            self.calendar_status = {}; self.last_error = None; self.consecutive_failures = 0
            self.message = 'Disconnected. Existing iCloud calendar copies are kept.'
            with self.app.db_connection() as c:
                c.execute("DELETE FROM calendar_sources WHERE source_kind='icloud'")
        return self.status(True)

    def run(self):
        while True:
            retry_in = min(60 * (2 ** max(0, self.consecutive_failures - 1)), 900)
            self.wake.wait(retry_in); self.wake.clear()
            if self.enabled: self.sync()

    def sync(self):
        if not self.lock.acquire(blocking=False): return
        active_calendar_id = None
        try:
            if not self.enabled or not self.client: return
            self.busy = True
            self.last_attempt = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
            with self.app.db_connection() as c:
                config = dict(c.execute('SELECT * FROM icloud_config WHERE id=1').fetchone())
                notifications = bool(self.app.get_settings(c)['notifications'])
                rules = []
                mappings = {r['local_key']:dict(r) for r in c.execute('SELECT * FROM icloud_items')}
                sections = [dict(r) for r in c.execute("""SELECT s.id,s.active,l.calendar_url,l.calendar_name,
                    l.import_enabled,l.export_enabled FROM organiser_sections s JOIN calendar_links l
                      ON l.target_kind='organiser_section' AND l.target_key=CAST(s.id AS TEXT)
                    WHERE s.active=1""")]
                organiser_events = [dict(r) for r in c.execute(
                    """SELECT e.*,s.id AS section_id,l.calendar_url,l.calendar_name,l.export_enabled
                         FROM organiser_events e JOIN organiser_sections s ON s.id=e.section_id
                         JOIN calendar_links l ON l.target_kind='organiser_section' AND l.target_key=CAST(s.id AS TEXT)
                         WHERE s.active=1"""
                )]
            prefix = 'align-' + config['instance_id'] + '-'
            conflicts = []

            def sync_owned_item(key, uid, url, payload, content_hash, saved):
                try:
                    self._sync_owned_item(key, uid, url, payload, content_hash, saved)
                except CloudError as error:
                    message = str(error)
                    if 'edited in iCloud' in message or 'changed in iCloud' in message or 'edited in both' in message:
                        conflicts.append({'local_key':str(key), 'message':message})
                        return
                    raise

            # Read the normal clash calendars plus every section calendar that has
            # imports enabled. Each iCloud calendar gets its own source row so the
            # Home section can display only the events that belong to it.
            section_by_url = {row['calendar_url']: row for row in sections if row['import_enabled']}
            read_urls = list(dict.fromkeys(json.loads(config['read_urls']) + list(section_by_url)))
            events_by_url = {}
            start = datetime.now(timezone.utc)-timedelta(days=31)
            end = datetime.now(timezone.utc)+timedelta(days=730)
            total_read = 0
            for url in read_urls:
                active_calendar_id = digest(url)
                previous = self.calendar_status.get(active_calendar_id, {})
                self.calendar_status[active_calendar_id] = {
                    'status':'syncing', 'last_success':previous.get('last_success'),
                    'event_count':previous.get('event_count'), 'error':None,
                }
                calendar_events = []
                for event in self.client.events(url,start,end):
                    parsed = busy_event(event,prefix)
                    if parsed: calendar_events.append(parsed)
                    total_read += 1
                    if total_read>20000: raise CloudError('Too many iCloud events. Select fewer calendars.')
                events_by_url[url] = calendar_events
                self.calendar_status[active_calendar_id] = {
                    'status':'ok', 'last_success':self.last_attempt,
                    'event_count':len(calendar_events), 'error':None,
                }
            active_calendar_id = None
            with self.app.db_connection() as c:
                c.execute("DELETE FROM calendar_sources WHERE source_kind='icloud'")
                for url, items in events_by_url.items():
                    section = section_by_url.get(url)
                    name = section['calendar_name'] if section else 'iCloud · clash calendar'
                    source = c.execute(
                        """INSERT INTO calendar_sources(name,source_kind,section_id,target_kind,target_key,source_key)
                           VALUES(?, 'icloud', ?, ?, ?, ?)""",
                        (name, section['id'] if section else None,
                         'organiser_section' if section else '', str(section['id']) if section else '', digest(url)),
                    ).lastrowid
                    c.executemany(
                        'INSERT OR IGNORE INTO calendar_events(source_id,event_uid,start_at,end_at,title,all_day,location) VALUES(?,?,?,?,?,?,?)',
                        [(source, digest(url)+':'+item[0], *item[1:]) for item in items],
                    )

            wanted = set()
            # V3 only manages Section events. Numeric legacy shift mappings and
            # their travel entries are intentionally left untouched, including
            # their iCloud copies, so this transition cannot delete user data.
            for event in organiser_events:
                if not event['export_enabled']:
                    continue
                key = 'event:' + str(event['id']); wanted.add(key)
                uid = prefix + 'event-' + str(event['id']) + '@align.local'
                url = event['calendar_url'].rstrip('/') + '/' + uid + '.ics'
                payload, content_hash = organiser_event(event,uid)
                sync_owned_item(key, uid, url, payload, content_hash, mappings.get(key))
                tuid = prefix + 'travel-event-' + str(event['id']) + '@align.local'
                block = travel_block(event, tuid, rules if notifications else None)
                if block:
                    tkey = 'travel:event:' + str(event['id']); wanted.add(tkey)
                    sync_owned_item(tkey, tuid, event['calendar_url'].rstrip('/') + '/' + tuid + '.ics', block[0], block[1], mappings.get(tkey))

            for key,saved in mappings.items():
                if key in wanted:
                    continue
                # Preserve legacy/non-Section mappings without querying retired
                # shift tables. Only Section-event mappings are reconciled here.
                if str(key).isdigit() or str(key).startswith(('shift:', 'travel:')):
                    continue
                if not str(key).startswith('event:'):
                    continue
                with self.app.db_connection() as c:
                    exists = c.execute(
                        'SELECT 1 FROM organiser_events WHERE id=?',
                        (str(key).split(':',1)[1],)
                    ).fetchone()
                    if exists:
                        continue
                remote = self.client.get(saved['url'])
                if remote:
                    raw, etag = remote
                    if read_owned(raw,saved['uid']) != saved['content_hash']:
                        conflicts.append({
                            'local_key':str(key),
                            'message':'A removed Align event was changed in iCloud. Its cloud copy was not deleted.'
                        })
                        continue
                    self.client.delete(saved['url'],etag)
                with self.app.db_connection() as c: c.execute('DELETE FROM icloud_items WHERE local_key=?',(key,))
            self.last_sync = datetime.now().isoformat(timespec='seconds')
            self.last_error = None; self.consecutive_failures = 0
            self.conflicts = conflicts
            if conflicts:
                self.message = (
                    f'Synced {sum(1 for e in organiser_events if e["export_enabled"])} Section events. '
                    f'Read {sum(len(v) for v in events_by_url.values())} iCloud events. '
                    f'{len(conflicts)} Align event{"s" if len(conflicts) != 1 else ""} need review '
                    'after edits in both Align and iCloud. Other events continued syncing both ways.'
                )
            else:
                self.message = (
                    f'Two-way sync complete: {sum(1 for e in organiser_events if e["export_enabled"])} Section events. '
                    f'Read {sum(len(v) for v in events_by_url.values())} iCloud events.'
                )
        except CloudError as error:
            self.conflicts = conflicts
            self.message = str(error)
            self.last_error = self.message
            self.consecutive_failures += 1
            if active_calendar_id:
                previous = self.calendar_status.get(active_calendar_id, {})
                self.calendar_status[active_calendar_id] = {
                    'status':'error', 'last_success':previous.get('last_success'),
                    'event_count':previous.get('event_count'), 'error':self.message,
                }
        except Exception:
            self.conflicts = conflicts
            self.message = 'iCloud sync failed. Check your connection, app-specific password and calendar permissions. Cached events may be out of date; no unverified overwrite was attempted.'
            self.last_error = self.message
            self.consecutive_failures += 1
            if active_calendar_id:
                previous = self.calendar_status.get(active_calendar_id, {})
                self.calendar_status[active_calendar_id] = {
                    'status':'error', 'last_success':previous.get('last_success'),
                    'event_count':previous.get('event_count'), 'error':self.message,
                }
        finally:
            self.busy = False; self.lock.release()

    def _apply_inbound(self, key, raw, uid):
        """Pull an iCloud edit of an Align-owned event back into Align (2-way sync)."""
        if str(key).startswith('travel:') or not str(key).startswith('event:'):
            return False
        component = owned_component(raw, uid)
        start, end, all_day = local_times(component)
        summary = str(component.get('SUMMARY') or '').strip()[:200]
        location = str(component.get('LOCATION') or '').strip()[:1000]
        description = str(component.get('DESCRIPTION') or '').strip()[:20000]
        with self.app.db_connection() as c:
            if str(key).startswith('event:'):
                event_id = int(str(key).split(':', 1)[1])
                row = c.execute('SELECT id FROM organiser_events WHERE id=?', (event_id,)).fetchone()
                if not row:
                    return False
                if all_day:
                    start_at = start.isoformat() if isinstance(start, datetime) else start.isoformat()
                    end_at = end.isoformat() if isinstance(end, datetime) else end.isoformat()
                    if isinstance(start, datetime):
                        start_at = start.date().isoformat()
                    if isinstance(end, datetime):
                        end_at = end.date().isoformat()
                    # Store all-day as midnight-local ISO dates used elsewhere.
                    start_at = f"{start_at}T00:00" if 'T' not in start_at else start_at
                    end_at = f"{end_at}T00:00" if 'T' not in end_at else end_at
                else:
                    if not isinstance(start, datetime) or not isinstance(end, datetime):
                        return False
                    start_at = start.isoformat(timespec='minutes')
                    end_at = end.isoformat(timespec='minutes')
                c.execute(
                    "UPDATE organiser_events SET title=?,start_at=?,end_at=?,all_day=?,location=?,notes=? WHERE id=?",
                    (summary or 'Event', start_at, end_at, 1 if all_day else 0, location, description, event_id),
                )
                return True
            return False

    def _sync_owned_item(self, key, uid, url, payload, content_hash, saved):
        # Conflict-safe two-way sync for Section events.
        # Two-way: when Align is unchanged and iCloud changed, pull the edit in.
        if not saved:
            with self.app.db_connection() as c:
                c.execute('INSERT INTO icloud_items(local_key,uid,url,etag,content_hash) VALUES(?,?,?,?,?)',(key,uid,url,'',content_hash))
            saved = {'uid':uid,'url':url,'etag':'','content_hash':content_hash}
        elif saved['url'] != url:
            # Moving a linked event between calendars is deliberately conservative:
            # remove the old owned copy only when it has not been edited remotely.
            remote = self.client.get(saved['url'])
            if remote:
                raw, etag = remote
                if read_owned(raw,saved['uid']) != saved['content_hash']:
                    raise CloudError('An Align event was edited in iCloud. It was not moved to another calendar.')
                self.client.delete(saved['url'],etag)
            with self.app.db_connection() as c:
                c.execute('UPDATE icloud_items SET url=?,etag=?,content_hash=? WHERE local_key=?',(url,'',content_hash,key))
            saved = {'uid':uid,'url':url,'etag':'','content_hash':content_hash}
        remote = self.client.get(saved['url'])
        if remote:
            raw, etag = remote
            remote_hash = read_owned(raw,uid)
            if remote_hash == content_hash:
                with self.app.db_connection() as c: c.execute('UPDATE icloud_items SET etag=?,content_hash=? WHERE local_key=?',(etag,content_hash,key))
                return
            if remote_hash != saved['content_hash'] or not etag:
                # Align unchanged since last sync → import the iCloud edit.
                if content_hash == saved['content_hash'] and self._apply_inbound(key, raw, uid):
                    with self.app.db_connection() as c:
                        c.execute('UPDATE icloud_items SET etag=?,content_hash=? WHERE local_key=?',(etag, remote_hash, key))
                    return
                raise CloudError('An Align event was edited in both Align and iCloud. Sync paused for this event. Keep one version and use Sync now.')
        else: etag = None
        new_etag = self.client.put(saved['url'],payload,etag)
        with self.app.db_connection() as c: c.execute('UPDATE icloud_items SET etag=?,content_hash=? WHERE local_key=?',(new_etag,content_hash,key))
