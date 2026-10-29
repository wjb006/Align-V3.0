"""iCloud connection routes."""
from __future__ import annotations


def handle_get(handler, app, parsed, row) -> bool:
    self = handler
    if parsed.path == '/api/icloud/status':
        self.send_json(200, self.request_icloud_manager(row).status())
        return True
    if parsed.path == '/api/icloud/manage':
        if self.require_local_icloud_admin(): self.send_json(200, self.request_icloud_manager(row).status(True))
        return True
    return False


def handle_post(handler, app, path, row, payload) -> bool:
    self = handler
    BETA_MODE = app.BETA_MODE
    beta_store = app.beta_store
    if path.startswith('/api/icloud/') and path not in {'/api/icloud/create-event-calendar','/api/icloud/select-calendars'} and not self.require_local_icloud_admin(): return True
    if path.startswith('/api/icloud/'):
        manager = self.request_icloud_manager(row,False)
        if path == '/api/icloud/connect':
            if BETA_MODE:
                username=beta_store().decrypt_browser(payload.get('username_box')); password=beta_store().decrypt_browser(payload.get('password_box'))
            else:
                username=payload.get('username'); password=payload.get('password')
            result=manager.discover(username,password)
            if BETA_MODE: beta_store().store_icloud(row,username,password)
        elif path == '/api/icloud/create-calendar':
            result = manager.create_calendar(payload.get('name'))
            created = result.get('created_calendar') or {}
            if created.get('url'):
                with app.db_connection() as connection:
                    connection.execute("""INSERT INTO calendar_links
                        (target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
                        VALUES('icloud_calendar',?,?,?,1,1)
                        ON CONFLICT(target_kind,target_key) DO UPDATE SET
                        calendar_url=excluded.calendar_url,calendar_name=excluded.calendar_name""",
                        (created['id'], created['url'], created['name']))
                    from organiser_api import event_section_for_calendar
                    event_section_for_calendar(connection, created['id'])
            result['created_calendar'] = {key:value for key,value in created.items() if key != 'url'}
        elif path == '/api/icloud/create-event-calendar':
            result = manager.create_calendar(payload.get('name'))
            created = result.get('created_calendar') or {}
            if created.get('url'):
                with app.db_connection() as connection:
                    connection.execute("""INSERT INTO calendar_links
                        (target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
                        VALUES('icloud_calendar',?,?,?,1,1)
                        ON CONFLICT(target_kind,target_key) DO UPDATE SET
                        calendar_url=excluded.calendar_url,calendar_name=excluded.calendar_name""",
                        (created['id'], created['url'], created['name']))
                    from organiser_api import event_section_for_calendar
                    event_section_for_calendar(connection, created['id'])
                    result['event_calendars'] = app.icloud_event_calendars(connection)
            result['created_calendar'] = {key:value for key,value in created.items() if key != 'url'}
        elif path == '/api/icloud/enable':
            if payload.get('consent') is not True: raise ValueError('Confirm reading the selected calendars and syncing Align events.')
            result = manager.configure(payload.get('target'), payload.get('read_ids'))
        elif path == '/api/icloud/select-calendars':
            result = app.save_icloud_event_calendars(payload.get('calendar_ids', []), self.request_icloud_manager(row, False))
        elif path == '/api/icloud/disconnect':
            result = manager.disconnect()
            if BETA_MODE: beta_store().clear_icloud(row)
        elif path == '/api/icloud/sync':
            if not manager.enabled: raise ValueError('Connect iCloud and select calendars first.')
            manager.wake.set(); result = manager.status(True)
        else:
            self.send_json(404, {'error':'Not found'}); return True
        self.send_json(200, result); return True
    return False
