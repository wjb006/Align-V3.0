"""Owner-managed app structure, with private records in each user's database."""
import hmac
import json
import math
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.request
import bill_calculations
import builder_finance
import builder_workflow
import appearance_settings
import sqlite3
from sqlite_support import connect as sqlite_connect, postgres_enabled
from datetime import date, datetime, timezone
from contextlib import contextmanager


class BuilderError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


BASE_STRUCTURE_VERSION = 1


def default_work_layout():
    """Optional Work form; Owners can change its fields in Management Studio."""
    return {
        'id': 'work', 'title': 'Work',
        'description': 'Keep the work details you choose, in your own private Work records.',
        'view': 'table', 'review_before_save': True, 'optional': True,
        'work_associations': {
            'location': 'work_location', 'area': 'shift_area', 'date': 'work_date',
            'start_time': 'start_time', 'end_time': 'end_time',
        },
        'fields': [
            dict(id='work_location', label='Work Location', type='text', required=True, help='Where you are working.', options=[]),
            dict(id='shift_area', label='Shift Area', type='text', required=False, help='Team, department, or area.', options=[]),
            dict(id='work_date', label='Work date', type='date', required=True, help='', options=[]),
            dict(id='start_time', label='Start time', type='text', required=True, help='For example, 08:00.', options=[]),
            dict(id='end_time', label='End time', type='text', required=True, help='For example, 16:00.', options=[]),
            dict(id='work_notes', label='Notes', type='textarea', required=False, help='', options=[]),
        ],
    }


@contextmanager
def connect(path):
    c = sqlite_connect(path)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()


def ensure(c):
    if postgres_enabled():
        c.execute('SELECT id, revision, published_revision, draft, published FROM builder_config LIMIT 0')
        c.execute('SELECT id, layout_id, values_json, revision, archived, created_at, updated_at FROM builder_records LIMIT 0')
        c.execute('SELECT id, key, name, icon, colour, sort_order, active, revision, published_revision, layout_json FROM section_defs LIMIT 0')
        c.execute('SELECT id, section_id, field_key, label, type, required, options_json, validation_json, formula, sort_order FROM section_fields LIMIT 0')
        return
    c.execute('CREATE TABLE IF NOT EXISTS builder_config (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, published_revision INTEGER NOT NULL, draft TEXT NOT NULL, published TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS builder_records (id TEXT PRIMARY KEY, layout_id TEXT NOT NULL, values_json TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE INDEX IF NOT EXISTS builder_records_layout ON builder_records(layout_id, archived, created_at)')


def defaults(c):
    menus = []
    for row in c.execute('SELECT * FROM parent_menu_branches ORDER BY sort_order,id'):
        menus.append(dict(id='menu_' + str(row['id']), parent_id='menu_' + str(row['parent_id']) if row['parent_id'] else '',
                          title=row['title'], description=row['description'], icon=row['icon'], colour=row['colour'],
                          destination=row['destination'], content=row['content'], active=bool(row['active']), layout_id=''))
    document = {'startup': {'title': 'Welcome to Align', 'description': 'Add your personal details. You can set up work and calendars later.', 'button': 'Open my planner',
                        'fields': [dict(id='user_name', label='Full name', type='text', required=True, help='', options=[]),
                                   dict(id='user_phone', label='Phone number', type='tel', required=False, help='', options=[]),
                                   dict(id='user_address', label='Address', type='textarea', required=False, help='', options=[]),
                                   dict(id='user_home_location', label='Home location', type='text', required=False, help='Use a home address or a place name for travel and local weather.', options=[]),
                                   dict(id='travel_bus', label='Use bus journeys', type='checkbox', required=False, help='', options=[]),
                                   dict(id='travel_rail', label='Use train journeys', type='checkbox', required=False, help='', options=[]),
                                   dict(id='travel_walk', label='Use walking journeys', type='checkbox', required=False, help='', options=[])]},
            'menus': menus, 'layouts': [default_work_layout()],
            'navigation': [dict(id='today', title='Today', icon='⌂', destination='today', active=True), dict(id='inbox', title='Inbox', icon='☑', destination='inbox', active=True), dict(id='sections', title='Sections', icon='◫', destination='sections', active=True), dict(id='more', title='More', icon='•••', destination='more', active=True)],
            'home_sections': [
                dict(id='today', title='Today at a glance', visible=True, sort_order=10,
                     content=dict(show_weather=True, show_schedule=True, show_quick_add=True)),
                dict(id='menus', title='Your sections', visible=True, sort_order=20, content={}),
                dict(id='upcoming', title='Upcoming Events', visible=True, sort_order=30,
                     content=dict(group_by_day=True)),
            ],
            'travel_results': dict(show_best_only=True, show_more=True, visibility=dict(
                leave_by=True, departure_arrival=True, duration=True, mode_provider=True,
                weather_adjustment=True, traffic_adjustment=True, actions=True)),
            'appearance': appearance_settings.DEFAULT_APPEARANCE,
            'appearance_permissions': appearance_settings.DEFAULT_PERMISSIONS}
    document['base_structure'] = base_structure(document)
    return document


def base_structure(document):
    return {'version': BASE_STRUCTURE_VERSION,
            'navigation': json.loads(json.dumps(document.get('navigation', []))),
            'home_sections': json.loads(json.dumps(document.get('home_sections', []))),
            'formatting': json.loads(json.dumps(document.get('formatting', formatting_validate({})))),
            'travel_results': json.loads(json.dumps(document.get('travel_results', travel_results_validate({})))),
            'weather': {'enabled': True, 'refresh_minutes': 15, 'show_last_updated': True,
                        'show_errors': True, 'views': ['today', 'hourly', 'daily']}}


def config(path):
    with connect(path) as c:
        ensure(c)
        if not c.execute('SELECT 1 FROM builder_config WHERE id=1').fetchone():
            text = json.dumps(defaults(c))
            c.execute('INSERT OR IGNORE INTO builder_config VALUES(1,1,1,?,?)', (text, text))
        row = c.execute('SELECT * FROM builder_config WHERE id=1').fetchone()
        draft=json.loads(row['draft']); published=json.loads(row['published']); baseline=defaults(c)
        changed=False
        for key in ('navigation','home_sections','travel_results','appearance','appearance_permissions'):
            if key not in draft:
                draft[key]=baseline[key]
                changed=True
            if key not in published:
                published[key]=baseline[key]
                changed=True
        for target in (draft, published):
            for key, normalise in (('appearance', appearance_settings.validate_appearance), ('appearance_permissions', appearance_settings.validate_permissions)):
                try:
                    fixed = normalise(target.get(key, {}))
                except ValueError:
                    continue
                if fixed != target.get(key):
                    target[key] = fixed
                    changed = True
            try:
                fixed_sections = validate_home_sections(target.get('home_sections', []))
            except BuilderError:
                fixed_sections = None
            if fixed_sections is not None:
                fixed_sections = [section for section in fixed_sections if section.get('id') not in ('stats','annual_leave')]
                for section in fixed_sections:
                    if section.get('id') == 'upcoming' and section.get('title') == 'Upcoming shifts':
                        section['title'] = 'Upcoming Events'
                        changed = True
                if fixed_sections != target.get('home_sections'):
                    target['home_sections'] = fixed_sections
                    changed = True
                    base = target.get('base_structure')
                    if isinstance(base, dict):
                        base['home_sections'] = json.loads(json.dumps(fixed_sections))
        for target in (draft, published):
            layouts = target.get('layouts')
            if isinstance(layouts, list) and not any(
                isinstance(layout, dict) and layout.get('id') == 'work'
                for layout in layouts
            ):
                # Add the optional Work database to existing installations too.
                # Users opt in themselves; this creates no Work records.
                layouts.append(default_work_layout())
                changed = True
            for layout in target.get('layouts', []):
                if (
                    isinstance(layout, dict)
                    and layout.get('finance')
                    and not layout.get('workflow')
                ):
                    layout['workflow'] = builder_finance.workflow()
                    changed = True
            navigation = target.get('navigation', [])
            # Preserve configurable Planner/Calendar destinations in saved builder documents.
            if len(navigation) < 2:
                target['navigation'] = json.loads(json.dumps(baseline['navigation']))
                target['base_structure'] = base_structure(target)
                changed = True
                continue
            legacy = target.get('base_structure')
            if not isinstance(legacy, dict) or legacy.get('version') != BASE_STRUCTURE_VERSION:
                target['base_structure'] = base_structure(target)
                changed = True
        if changed:
            c.execute('UPDATE builder_config SET draft=?,published=? WHERE id=1',(json.dumps(draft),json.dumps(published)))
        return {'revision':row['revision'],'published_revision':row['published_revision'],'draft':draft,'published':published}


def text(value, limit=200):
    if not isinstance(value, str) or len(value) > limit:
        raise BuilderError(f'Enter text no longer than {limit} characters.')
    return value.strip()


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,79}', value):
        raise BuilderError('Invalid item identifier.')
    return value


def fields_validate(fields):
    if not isinstance(fields, list) or not 1 <= len(fields) <= 50:
        raise BuilderError('Use between 1 and 50 fields per form.')
    seen = set()
    result = []
    for f in fields:
        if not isinstance(f, dict): raise BuilderError('Invalid field.')
        fid = identity(f.get('id'))
        if fid in seen: raise BuilderError('Field identifiers must be unique.')
        seen.add(fid)
        kind = f.get('type')
        if kind not in ('text', 'address', 'textarea', 'tel', 'email', 'number', 'date', 'select', 'checkbox', 'formula'):
            raise BuilderError('Unsupported field type.')
        label = text(f.get('label', ''), 80)
        if not label: raise BuilderError('Every field needs a label.')
        options = f.get('options', [])
        if not isinstance(options, list) or len(options) > 100: raise BuilderError('Use up to 100 dropdown choices.')
        options = [text(x, 100) for x in options]
        if len(options) != len(set(options)) or any(not x for x in options): raise BuilderError('Dropdown choices must be unique and non-empty.')
        if kind == 'select' and not options: raise BuilderError('Add choices to each dropdown.')
        result.append(dict(id=fid, label=label, type=kind, required=bool(f.get('required')), help=text(f.get('help', ''), 250), options=options, **({'formula': text(f.get('formula', ''), 500)} if kind == 'formula' else {})))
        result[-1]['allow_custom'] = kind == 'select' and bool(f.get('allow_custom'))
        conditions = f.get('show_when', {})
        if not isinstance(conditions, dict): raise BuilderError('Invalid field visibility rule.')
        for key, choices in conditions.items():
            if key not in seen or key == fid or not isinstance(choices, list) or not choices or any(type(v) not in (str, bool) for v in choices):
                raise BuilderError('Visibility rules must refer to an earlier field and list its allowed values.')
        result[-1]['show_when'] = conditions
    try: bill_calculations.validate(result)
    except ValueError as exc: raise BuilderError(str(exc)) from None
    return result


def database_flow_validate(value, fields):
    if not isinstance(value, dict):
        raise BuilderError('Invalid database flowchart.')
    edges = value.get('edges', [])
    if not isinstance(edges, list) or len(edges) > 500:
        raise BuilderError('Use up to 500 database flowchart connections.')
    field_map = {field['id']: field for field in fields}
    node_ids = set(field_map) | {'__flow_start__', '__flow_finish__'}
    seen = set()
    clean_edges = []
    adjacency = {node_id: [] for node_id in node_ids}
    for edge in edges:
        if not isinstance(edge, dict):
            raise BuilderError('Invalid database flowchart connection.')
        source = edge.get('from')
        target = edge.get('to')
        if not isinstance(source, str) or not isinstance(target, str) or source not in node_ids or target not in node_ids or source == target:
            raise BuilderError('Choose two different existing nodes for each flowchart connection.')
        pair = (source, target)
        if pair in seen:
            raise BuilderError('Database flowchart connections must be unique.')
        seen.add(pair)
        adjacency[source].append(target)
        cleaned = {'from': source, 'to': target}
        condition = edge.get('when')
        if condition is not None:
            if not isinstance(condition, dict):
                raise BuilderError('Invalid flowchart branch condition.')
            field_id = identity(condition.get('field'))
            field = field_map.get(field_id)
            equals = condition.get('equals')
            if not field or field['type'] not in ('select', 'checkbox'):
                raise BuilderError('Flowchart conditions must use a dropdown or checkbox field.')
            if field['type'] == 'checkbox':
                if type(equals) is not bool:
                    raise BuilderError('Checkbox flowchart conditions must be Yes or No.')
            elif not isinstance(equals, str) or equals not in field['options']:
                raise BuilderError('Choose a valid dropdown value for the flowchart condition.')
            cleaned['when'] = {'field': field_id, 'equals': equals}
        clean_edges.append(cleaned)
    visiting = set()
    visited = set()
    def visit(node_id):
        if node_id in visiting:
            raise BuilderError('Database flowchart connections cannot contain a loop.')
        if node_id in visited:
            return
        visiting.add(node_id)
        for next_id in adjacency[node_id]:
            visit(next_id)
        visiting.remove(node_id)
        visited.add(node_id)
    for node_id in node_ids:
        visit(node_id)
    return {'edges': clean_edges}

def formatting_validate(value):
    if not isinstance(value, dict): raise BuilderError('Invalid formatting settings.')
    result = {}
    for key, default in [('accent','#365ce6'),('background','#f5f7fb'),('surface','#ffffff'),('text','#1c2940')]:
        colour=value.get(key,default)
        if not isinstance(colour,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',colour): raise BuilderError('Choose a valid formatting colour.')
        result[key]=colour
    for key, choices, default in [('font',('system','serif','mono'),'system'),('size',('14','16','18','20'),'16'),('spacing',('compact','comfortable','roomy'),'comfortable'),('radius',('0','8','16','24'),'16'),('columns',('1','2'),'1'),('heading',('normal','bold'),'bold'),('align',('left','center'),'left')]:
        selected=value.get(key,default)
        if selected not in choices: raise BuilderError('Choose a valid formatting '+key+'.')
        result[key]=selected
    return result


def travel_results_validate(value):
    default = dict(show_best_only=True, show_more=True, visibility=dict(
        leave_by=True, departure_arrival=True, duration=True, mode_provider=True,
        weather_adjustment=True, traffic_adjustment=True, actions=True))
    if not isinstance(value, dict):
        value = {}
    visibility = value.get('visibility', {})
    if not isinstance(visibility, dict):
        visibility = {}
    return {
        'show_best_only': bool(value.get('show_best_only', default['show_best_only'])),
        'show_more': bool(value.get('show_more', default['show_more'])),
        'visibility': {key: bool(visibility.get(key, enabled))
                       for key, enabled in default['visibility'].items()},
    }


def base_structure_validate(value, source):
    if not isinstance(value, dict):
        value = {}
    weather = value.get('weather', {})
    if not isinstance(weather, dict):
        weather = {}
    refresh = weather.get('refresh_minutes', 15)
    if not isinstance(refresh, int) or refresh not in (5, 10, 15, 30, 60):
        raise BuilderError('Weather refresh must be 5, 10, 15, 30, or 60 minutes.')
    views = weather.get('views', ['today', 'hourly', 'daily'])
    if not isinstance(views, list) or not views or any(v not in ('today', 'hourly', 'daily') for v in views):
        raise BuilderError('Choose at least one supported weather view.')
    return {'version': BASE_STRUCTURE_VERSION,
            'navigation': validate_navigation(source.get('navigation', []), source.get('layouts', [])),
            'home_sections': validate_home_sections(source.get('home_sections', [])),
            'formatting': formatting_validate(source.get('formatting', {})),
            'travel_results': travel_results_validate(source.get('travel_results', {})),
            'weather': {'enabled': bool(weather.get('enabled', True)), 'refresh_minutes': refresh,
                        'show_last_updated': bool(weather.get('show_last_updated', True)),
                        'show_errors': bool(weather.get('show_errors', True)),
                        'views': list(dict.fromkeys(views))}}


def validate_navigation(navigation, layouts):
    if not isinstance(navigation, list) or not 2 <= len(navigation) <= 6:
        raise BuilderError('Use between 2 and 6 bottom navigation items.')
    layout_ids = {x['id'] for x in layouts}
    result = []
    for item in navigation:
        if not isinstance(item, dict): raise BuilderError('Invalid bottom navigation item.')
        destination = item.get('destination')
        if destination not in ('today','inbox','planner','sections','more','home','add','calendar','settings','profile','note','layout'):
            raise BuilderError('Choose a valid bottom navigation destination.')
        if destination == 'layout' and item.get('layout_id') not in layout_ids:
            raise BuilderError('Choose an existing database layout for navigation.')
        result.append(dict(id=identity(item.get('id')), title=text(item.get('title',''),40),
                           icon=text(item.get('icon','○'),4), destination=destination,
                           layout_id=item.get('layout_id','') if destination == 'layout' else '',
                           active=bool(item.get('active', True))))
    if not any(x['destination'] in ('today','home') and x['active'] for x in result):
        raise BuilderError('Keep an active Today item in bottom navigation.')
    return result


HOME_SECTION_CONTENT = {
    'today': {'show_weather': True, 'show_schedule': True, 'show_quick_add': True},
    'stats': {},
    'menus': {},
    'upcoming': {'group_by_day': True},
    'calendar': {'show_upcoming': True},
    'annual_leave': {},
}


def validate_home_section_content(section_id, content):
    defaults = HOME_SECTION_CONTENT.get(section_id, {})
    raw = content if isinstance(content, dict) else {}
    return {key: bool(raw.get(key, default)) for key, default in defaults.items()}


def validate_home_sections(sections):
    allowed = set(HOME_SECTION_CONTENT)
    if not isinstance(sections, list) or len(sections) > 20: raise BuilderError('Use up to 20 home sections.')
    seen = set(); result = []
    for item in sections:
        if not isinstance(item, dict) or item.get('id') not in allowed or item['id'] in seen:
            raise BuilderError('Invalid home section.')
        seen.add(item['id'])
        result.append(dict(
            id=item['id'],
            title=text(item.get('title', ''), 80),
            visible=bool(item.get('visible', True)),
            sort_order=int(item.get('sort_order', 100)),
            content=validate_home_section_content(item['id'], item.get('content')),
        ))
    return result


def validate(doc, previous=None):
    if not isinstance(doc, dict):
        raise BuilderError('Invalid builder document.')

    startup = doc.get('startup', {})
    if not isinstance(startup, dict):
        raise BuilderError('Invalid startup form.')

    startup = dict(
        title=text(startup.get('title', ''), 100),
        description=text(startup.get('description', ''), 500),
        button=text(startup.get('button', ''), 60),
        fields=fields_validate(startup.get('fields'))
    )

    if not startup['title'] or not startup['button']:
        raise BuilderError('Startup title and button text are required.')

    name = next(
        (f for f in startup['fields'] if f['id'] == 'user_name'),
        None
    )
    if not name or name['type'] != 'text' or not name['required']:
        raise BuilderError(
            'Keep the required name field so users can complete setup.'
        )

    layouts = doc.get('layouts')
    menus = doc.get('menus')

    if not isinstance(layouts, list) or len(layouts) > 100:
        raise BuilderError('Use up to 100 database layouts.')

    if not isinstance(menus, list) or len(menus) > 200:
        raise BuilderError('Use up to 200 menu items.')

    layout_ids = set()
    clean_layouts = []

    for layout in layouts:
        if not isinstance(layout, dict):
            raise BuilderError('Invalid database layout.')

        lid = identity(layout.get('id'))

        if lid in layout_ids:
            raise BuilderError('Duplicate layout identifier.')

        layout_ids.add(lid)

        title = text(layout.get('title', ''), 100)
        if not title:
            raise BuilderError('Database layouts need a name.')

        if layout.get('view') not in ('table', 'cards'):
            raise BuilderError('Choose table or cards.')

        # Work is an optional database, configured through the same Studio
        # matrix. Keep stable association keys so downstream work tools can
        # interpret the selected location, area, and time fields.
        work_associations = layout.get('work_associations', {})
        if lid == 'work':
            if not isinstance(work_associations, dict):
                raise BuilderError('Choose valid Work field associations.')
            work_fields = fields_validate(layout.get('fields'))
            work_by_id = {field['id']: field for field in work_fields}
            cleaned_associations = {}
            expected_types = {'location': ('text', 'textarea', 'select'), 'area': ('text', 'textarea', 'select'), 'date': ('date',), 'start_time': ('text', 'select'), 'end_time': ('text', 'select')}
            for role, allowed_types in expected_types.items():
                field_id = work_associations.get(role, '')
                if not field_id:
                    cleaned_associations[role] = ''
                    continue
                if field_id not in work_by_id or work_by_id[field_id]['type'] not in allowed_types:
                    raise BuilderError(f'Choose a valid {role.replace("_", " ")} field for Work.')
                cleaned_associations[role] = field_id
        else:
            work_fields = fields_validate(layout.get('fields'))
            cleaned_associations = {}

        clean_layouts.append(
            dict(
                id=lid,
                title=title,
                description=text(layout.get('description', ''), 500),
                view=layout['view'],
                fields=work_fields
            )
        )

        clean_layout = clean_layouts[-1]

        clean_layout['review_before_save'] = bool(
            layout.get('review_before_save')
        )
        clean_layout['finance'] = bool(layout.get('finance'))
        clean_layout['optional'] = bool(layout.get('optional'))
        if lid == 'work':
            clean_layout['optional'] = True
            clean_layout['work_associations'] = cleaned_associations

        if layout.get('finance'):
            try:
                builder_finance.validate_fields(clean_layout['fields'])
            except ValueError as exc:
                raise BuilderError(str(exc)) from None

        workflow = layout.get('workflow')

        if layout.get('finance') and not workflow:
            workflow = builder_finance.workflow()

        try:
            workflow = builder_workflow.validate(
                workflow,
                clean_layout['fields']
            )
        except ValueError as exc:
            raise BuilderError(str(exc)) from None

        if workflow:
            clean_layout['workflow'] = workflow

        database_flow = layout.get('database_flow')
        if database_flow is not None:
            clean_layout['database_flow'] = database_flow_validate(
                database_flow,
                clean_layout['fields']
            )

    clean_menus = []
    menu_ids = set()

    for m in menus:
        if not isinstance(m, dict):
            raise BuilderError('Invalid menu item.')

        mid = identity(m.get('id'))

        if mid in menu_ids:
            raise BuilderError('Duplicate menu identifier.')

        menu_ids.add(mid)

        destination = m.get('destination')

        if destination not in (
            'add',
            'calendar',
            'settings',
            'note',
            'submenu',
            'layout',
            'profile'
        ):
            raise BuilderError('Choose a valid menu destination.')

        title = text(m.get('title', ''), 100)

        if not title:
            raise BuilderError('Every menu item needs a title.')

        colour = m.get('colour', '#365CE6')

        if not isinstance(colour, str) or not re.fullmatch(
            r'#[0-9a-fA-F]{6}',
            colour
        ):
            raise BuilderError('Invalid colour.')

        lid = m.get('layout_id', '') if destination == 'layout' else ''

        if destination == 'layout' and lid not in layout_ids:
            raise BuilderError(
                'Choose an existing database layout for each database menu item.'
            )

        clean_menus.append(
            dict(
                id=mid,
                parent_id=m.get('parent_id') or '',
                title=title,
                description=text(m.get('description', ''), 250),
                icon=text(m.get('icon', '○'), 12),
                colour=colour,
                destination=destination,
                layout_id=lid,
                content=text(m.get('content', ''), 10000),
                active=bool(m.get('active', True))
            )
        )

    lookup = {m['id']: m for m in clean_menus}

    for m in clean_menus:
        parent = m['parent_id']
        seen = {m['id']}

        while parent:
            if (
                not isinstance(parent, str)
                or parent not in lookup
                or lookup[parent]['destination'] != 'submenu'
            ):
                raise BuilderError(
                    'Menu items must be placed inside an existing folder.'
                )

            if parent in seen:
                raise BuilderError('This move would create a menu loop.')

            seen.add(parent)

            if len(seen) > 12:
                raise BuilderError('Use at most 12 menu levels.')

            parent = lookup[parent]['parent_id']

    navigation = doc.get(
        'navigation',
        [
            dict(
                id='today',
                title='Today',
                icon='⌂',
                destination='today',
                active=True
            ),
            dict(
                id='inbox',
                title='Inbox',
                icon='☑',
                destination='inbox',
                active=True
            ),
            dict(
                id='planner',
                title='Planner',
                icon='▦',
                destination='planner',
                active=True
            ),
            dict(
                id='sections',
                title='Sections',
                icon='◫',
                destination='sections',
                active=True
            ),
            dict(
                id='more',
                title='More',
                icon='•••',
                destination='more',
                active=True
            )
        ]
    )

    if not isinstance(navigation, list) or not 2 <= len(navigation) <= 6:
        raise BuilderError('Use between 2 and 6 bottom navigation items.')

    nav_ids = set()
    clean_nav = []

    for item in navigation:
        if not isinstance(item, dict):
            raise BuilderError('Invalid bottom navigation item.')

        nid = identity(item.get('id'))
        destination = item.get('destination')

        if nid in nav_ids:
            raise BuilderError(
                'Bottom navigation identifiers must be unique.'
            )

        if destination not in (
            'today',
            'inbox',
            'planner',
            'sections',
            'more',
            'home',
            'add',
            'calendar',
            'settings',
            'profile',
            'note',
            'layout'
        ):
            raise BuilderError(
                'Choose a valid bottom navigation destination.'
            )

        if (
            destination == 'layout'
            and item.get('layout_id') not in layout_ids
        ):
            raise BuilderError(
                'Choose an existing database layout for navigation.'
            )

        nav_ids.add(nid)

        clean_nav.append(
            dict(
                id=nid,
                title=text(item.get('title', ''), 40),
                icon=text(item.get('icon', '○'), 4),
                destination=destination,
                layout_id=(
                    item.get('layout_id', '')
                    if destination == 'layout'
                    else ''
                ),
                active=bool(item.get('active', True))
            )
        )

    if not any(
        x['destination'] in ('today', 'home') and x['active']
        for x in clean_nav
    ):
        raise BuilderError(
            'Keep an active Today item in bottom navigation.'
        )

    clean_sections = validate_home_sections(doc.get('home_sections', [
        dict(id='today', title='Today at a glance', visible=True, sort_order=10),
        dict(id='stats', title='Week summary', visible=True, sort_order=15),
        dict(id='menus', title='Your sections', visible=True, sort_order=20),
        dict(id='upcoming', title='Upcoming Events', visible=True, sort_order=30),
        dict(id='annual_leave', title='Annual leave', visible=True, sort_order=40),
    ]))

    clean = dict(
        formatting=formatting_validate(doc.get('formatting', {})),
        startup=startup,
        menus=clean_menus,
        layouts=clean_layouts,
        navigation=clean_nav,
        home_sections=clean_sections,
        travel_results=travel_results_validate(
            doc.get('travel_results', {})
        )
    )

    try:
        clean['appearance'] = appearance_settings.validate_appearance(doc.get('appearance', {}))
        clean['appearance_permissions'] = appearance_settings.validate_permissions(doc.get('appearance_permissions', {}))
    except ValueError as exc:
        raise BuilderError(str(exc)) from None

    clean['base_structure'] = base_structure_validate(
        doc.get('base_structure', {}),
        clean
    )

    # Stable field IDs keep data attached when labels or positions change.
    if previous:
        old_forms = {
            'startup': previous['startup']['fields'],
            **{
                x['id']: x['fields']
                for x in previous['layouts']
            }
        }

        new_forms = {
            'startup': startup['fields'],
            **{
                x['id']: x['fields']
                for x in clean_layouts
            }
        }

        for key, fields in new_forms.items():
            old = {
                x['id']: x['type']
                for x in old_forms.get(key, [])
            }

            for field in fields:
                if (
                    field['id'] in old
                    and old[field['id']] != field['type']
                ):
                    raise BuilderError(
                        'To change a published field type, add a new field. '
                        'Existing values are kept with the original field.'
                    )

    return clean


HISTORY_LIMIT = 10


def _history_read(c):
    row = c.execute("SELECT setting_value FROM settings WHERE setting_key='builder_history'").fetchone()
    try:
        data = json.loads(row['setting_value']) if row else []
    except (ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def _history_record(c, revision, document):
    # History must never block a publish.
    try:
        entries = _history_read(c)
        entries.insert(0, {
            'revision': revision,
            'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'appearance': document.get('appearance', {}),
            'appearance_permissions': document.get('appearance_permissions', {}),
        })
        c.execute("INSERT INTO settings VALUES('builder_history',?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value", (json.dumps(entries[:HISTORY_LIMIT]),))
    except Exception:
        pass


def history(path):
    with connect(path) as c:
        entries = _history_read(c)
    return {'history': [{'index': i, 'revision': e.get('revision'), 'at': e.get('at')} for i, e in enumerate(entries)]}


def restore_history(path, body):
    index = body.get('index')
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise BuilderError('Choose a saved design to restore.')
    with connect(path) as c:
        entries = _history_read(c)
    if index >= len(entries):
        raise BuilderError('That saved design is no longer available.', 404)
    current = config(path)
    entry = entries[index]
    doc = json.loads(json.dumps(current['draft']))
    doc['appearance'] = appearance_settings.validate_appearance(entry.get('appearance', {}))
    doc['appearance_permissions'] = appearance_settings.validate_permissions(entry.get('appearance_permissions', {}))
    return save_config(path, {'revision': current['revision'], 'document': doc})


HOSTED_PUBLISH_URL = os.environ.get('ALIGN_PUBLISH_URL', 'https://getalign.co.uk').rstrip('/')


def publish_key_matches(given):
    expected = os.environ.get('ALIGN_PUBLISH_KEY', '').strip()
    if not isinstance(given, str) or not given or not expected:
        return False
    given_b = given.encode()
    expected_b = expected.encode()
    if len(given_b) != len(expected_b):
        return False
    return hmac.compare_digest(given_b, expected_b)


def local_publish_key():
    env = os.environ.get('ALIGN_PUBLISH_KEY', '').strip()
    if env:
        return env
    from pathlib import Path
    key_path = Path(__file__).resolve().parent / '.align' / 'publish.key'
    if not key_path.is_file():
        return ''
    return key_path.read_text(encoding='utf-8').strip()


def request_is_local(handler):
    host = (handler.headers.get('Host') or '').split(',')[0].strip().lower()
    if host.startswith('['):
        name = host.split(']', 1)[0].removeprefix('[')
    else:
        name = host.rsplit(':', 1)[0] if host.count(':') == 1 else host
    client = ''
    if getattr(handler, 'client_address', None):
        client = str(handler.client_address[0]).lower()
    return name in ('127.0.0.1', 'localhost', '::1') and client in ('127.0.0.1', '::1', 'localhost')


def publish_document(path, document):
    current = config(path)
    return save_config(path, {'revision': current['revision'], 'document': document}, publish=True)


def publish_to_everyone(path, body, handler, app):
    if getattr(app, 'BETA_MODE', False):
        raise BuilderError('Publish to everyone runs from this PC.', 403)
    if not request_is_local(handler):
        raise BuilderError('Publish to everyone is only available on this PC.', 403)
    key = local_publish_key()
    if not key:
        raise BuilderError('This PC has no publish key, so the website was not updated.', 409)
    saved = save_config(path, body, publish=True)
    payload = json.dumps({'document': body.get('document')}).encode()
    request = urllib.request.Request(
        HOSTED_PUBLISH_URL + '/api/builder/accept-publish',
        data=payload,
        headers={'Content-Type': 'application/json', 'X-Align-Publish-Key': key},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            response.read()
    except urllib.error.HTTPError as error:
        detail = ''
        try:
            parsed = json.loads(error.read().decode('utf-8', 'replace'))
            detail = parsed.get('error') or ''
        except (OSError, ValueError, AttributeError):
            detail = ''
        message = 'This PC is updated. The website was not.'
        if detail:
            message = f'{message} {detail}'
        raise BuilderError(message, 502) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise BuilderError('This PC is updated. The website could not be reached.', 502) from None
    return saved


def save_config(path, body, publish=False):
    current = config(path)
    clean = validate(body.get('document'), current['published'])
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT revision FROM builder_config WHERE id=1').fetchone()
        if body.get('revision') != row['revision']:
            raise BuilderError('Someone changed this builder. Reload before saving your changes.', 409)
        revision = row['revision'] + 1
        raw = json.dumps(clean)
        if publish:
            c.execute('UPDATE builder_config SET revision=?, published_revision=?, draft=?, published=? WHERE id=1', (revision, revision, raw, raw))
            sync_published_sections(c, clean, revision)
            _history_record(c, revision, clean)
            try:
                from pathlib import Path
                from datetime import datetime
                base = Path(path).resolve().parent
                version = str(clean.get('version') or '2.0').strip().replace(' ', '-')
                build = str(clean.get('build') or revision).strip().replace(' ', '-')
                stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                report_dir = base / 'Build_Achive' / f'Version-{version}_Build-{build}_{stamp[:8]}'
                report_dir.mkdir(parents=True, exist_ok=True)
                report = report_dir / f'Publish-Report_Version-{version}_Build-{build}_{stamp}.md'
                report.write_text(
                    '# Align Publish Report\n\n'
                    f'- Version: {version}\n'
                    f'- Build: {build}\n'
                    f'- Published: {datetime.now().isoformat(timespec="seconds")}\n'
                    f'- Revision: {revision}\n'
                    '- Destination: Align App\n'
                    '- Status: Published\n',
                    encoding='utf-8'
                )
            except OSError:
                pass
        else:
            c.execute('UPDATE builder_config SET revision=?, draft=? WHERE id=1', (revision, raw))
    return config(path)


SECTION_FIELD_TYPES = {
    'text': 'text', 'textarea': 'textarea', 'tel': 'tel', 'number': 'number',
    'date': 'date', 'select': 'select', 'checkbox': 'checkbox',
    'formula': 'calculated', 'email': 'text',
}


def sync_published_sections(c, document, revision):
    """Materialise the published builder layouts as section definitions."""
    layouts = document.get('layouts', [])
    keys = [layout['id'] for layout in layouts]
    if keys:
        placeholders = ','.join('?' for _ in keys)
        c.execute(f'UPDATE section_defs SET active=0,revision=?,published_revision=? WHERE key NOT IN ({placeholders})',
                  (revision, revision, *keys))
    else:
        c.execute('UPDATE section_defs SET active=0,revision=?,published_revision=?', (revision, revision))
    for order, layout in enumerate(layouts, start=1):
        menu = next((item for item in document.get('menus', [])
                     if item.get('destination') == 'layout' and item.get('layout_id') == layout['id']), {})
        c.execute("""INSERT INTO section_defs
            (key,name,icon,colour,sort_order,active,revision,published_revision,layout_json)
            VALUES(?,?,?,?,?,1,?,?,?) ON CONFLICT(key) DO UPDATE SET
            name=excluded.name,icon=excluded.icon,colour=excluded.colour,sort_order=excluded.sort_order,
            active=1,revision=excluded.revision,published_revision=excluded.published_revision,layout_json=excluded.layout_json""",
            (layout['id'], layout['title'], menu.get('icon', '◫'), menu.get('colour', '#365CE6'), order * 10, revision, revision, json.dumps(layout)))
        section = c.execute('SELECT id FROM section_defs WHERE key=?', (layout['id'],)).fetchone()
        section_id = section['id']
        c.execute('DELETE FROM section_fields WHERE section_id=?', (section_id,))
        for field_order, field in enumerate(layout.get('fields', []), start=1):
            kind = SECTION_FIELD_TYPES.get(field['type'])
            if not kind:
                raise BuilderError('A section contains a field type that cannot be published.')
            validation = {key: field[key] for key in ('show_when', 'allow_custom') if key in field}
            c.execute("""INSERT INTO section_fields
                (section_id,field_key,label,type,required,options_json,validation_json,formula,sort_order)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (section_id, field['id'], field['label'], kind, int(field['required']),
                 json.dumps(field.get('options', [])), json.dumps(validation), field.get('formula', ''), field_order * 10))


def section_layouts(c, published_only=True):
    where = 'WHERE active=1 AND published_revision=revision' if published_only else 'WHERE active=1'
    layouts = []
    for row in c.execute(f'SELECT * FROM section_defs {where} ORDER BY sort_order,name'):
        fields = []
        for field in c.execute('SELECT * FROM section_fields WHERE section_id=? ORDER BY sort_order,id', (row['id'],)):
            validation = json.loads(field['validation_json'] or '{}')
            fields.append({
                'id': field['field_key'], 'label': field['label'],
                'type': 'formula' if field['type'] == 'calculated' else field['type'],
                'required': bool(field['required']), 'options': json.loads(field['options_json'] or '[]'),
                'formula': field['formula'], 'show_when': validation.get('show_when', {}),
                'allow_custom': bool(validation.get('allow_custom')),
            })
        layout = json.loads(row['layout_json'] or '{}')
        layout.update({'id': row['key'], 'title': row['name'], 'fields': fields})
        layouts.append(layout)
    return layouts


def published_layouts(owner_path):
    """Read global published section definitions from the Owner schema."""
    with connect(owner_path) as c:
        ensure(c)
        layouts = section_layouts(c)
    published_config = config(owner_path)['published'].get('layouts', [])
    configured = layouts or published_config
    # Older databases can already have materialised other sections without a
    # Work definition. Keep the new optional Work section visible in that case.
    if layouts and not any(layout.get('id') == 'work' for layout in configured):
        configured = [*configured, *(layout for layout in published_config if layout.get('id') == 'work')]
    # Work is an optional, user-owned database template. It is materialized
    # only after the owner publishes it and users may edit its form through
    # the same private section-record flow as other databases.
    for layout in configured:
        if layout.get('id') == 'work':
            layout['optional'] = True
            layout.setdefault('description', 'Work locations, areas, and times you choose to track.')
    return configured


def values_validate(fields, values):
    if not isinstance(values, dict): raise BuilderError('Invalid form values.')
    out = {}
    for f in fields:
        if f['type'] == 'formula': continue
        if not all(out.get(key, False if False in choices else '') in choices for key, choices in f.get('show_when', {}).items()):
            out[f['id']] = False if f['type'] == 'checkbox' else ''
            continue
        v = values.get(f['id'], False if f['type'] == 'checkbox' else '')
        if f['type'] == 'address':
            if isinstance(v, str):
                v = {'label': v, 'postcode': '', 'town': '', 'country': '', 'latitude': None, 'longitude': None, 'place_id': ''}
            if v in ('', None):
                if f['required']:
                    raise BuilderError(f"{f['label']} is required.")
                out[f['id']] = ''
                continue
            if not isinstance(v, dict):
                raise BuilderError(f"Enter a valid address for {f['label']}.")
            label = text(v.get('label', ''), 500)
            if not label:
                if f['required']:
                    raise BuilderError(f"{f['label']} is required.")
                out[f['id']] = ''
                continue
            address = {
                'label': label,
                'postcode': text(v.get('postcode', ''), 30),
                'town': text(v.get('town', ''), 120),
                'country': text(v.get('country', ''), 80),
                'place_id': text(str(v.get('place_id', '')), 80),
                'latitude': None,
                'longitude': None,
            }
            for coordinate, lower, upper in (('latitude', -90, 90), ('longitude', -180, 180)):
                raw = v.get(coordinate)
                if raw not in (None, ''):
                    try:
                        number = float(raw)
                    except (ValueError, TypeError):
                        raise BuilderError(f"Invalid address coordinates for {f['label']}.")
                    if not math.isfinite(number) or not lower <= number <= upper:
                        raise BuilderError(f"Invalid address coordinates for {f['label']}.")
                    address[coordinate] = number
            out[f['id']] = address
            continue
        if f['required'] and (v is None or v == '' or (f['type'] == 'checkbox' and v is not True)):
            raise BuilderError(f"{f['label']} is required.")
        if v in ('', None) and f['type'] != 'checkbox':
            out[f['id']] = ''
            continue
        if f['type'] == 'checkbox':
            if not isinstance(v, bool): raise BuilderError(f"Choose yes or no for {f['label']}.")
        elif f['type'] == 'number':
            try: v = float(v)
            except (ValueError, TypeError): raise BuilderError(f"Enter a number for {f['label']}.")
            if not math.isfinite(v): raise BuilderError('Numbers must be finite.')
        else:
            v = text(v, 10000 if f['type'] == 'textarea' else 500)
            if f['required'] and not v: raise BuilderError(f"{f['label']} is required.")
            if f['type'] == 'email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', v): raise BuilderError(f"Enter a valid email for {f['label']}.")
            if f['type'] == 'date':
                try: date.fromisoformat(v)
                except ValueError: raise BuilderError(f"Enter a valid date for {f['label']}.")
            if f['type'] == 'select' and not f.get('allow_custom') and v not in f['options']: raise BuilderError(f"Choose a listed option for {f['label']}.")
        out[f['id']] = v
    try: return bill_calculations.calculate(fields, out)
    except ValueError as exc: raise BuilderError(str(exc)) from None


def record_values(layout, values):
    values = values_validate(layout['fields'], values)
    if layout.get('finance'):
        try: values = builder_finance.calculate(values)
        except ValueError as exc: raise BuilderError(str(exc)) from None
    return values


def profile(c):
    row = c.execute("SELECT setting_value FROM settings WHERE setting_key='builder_profile'").fetchone()
    saved = json.loads(row['setting_value']) if row else {}
    for row in c.execute("SELECT * FROM settings WHERE setting_key IN ('user_name','user_address','user_phone','user_home_location','travel_bus','travel_rail','travel_walk')"):
        key = row['setting_key']
        saved[key] = row['setting_value'].lower() == 'true' if key in ('travel_bus', 'travel_rail', 'travel_walk') else row['setting_value']
    return saved


def bootstrap(owner_path, c):
    current = config(owner_path)
    document = current['published']
    saved = c.execute(
        "SELECT setting_value FROM settings WHERE setting_key='user_appearance'"
    ).fetchone()
    personal = json.loads(saved['setting_value']) if saved else {}
    permissions = document.get('appearance_permissions', appearance_settings.DEFAULT_PERMISSIONS)
    return dict(
        document=document,
        revision=current['published_revision'],
        profile=profile(c),
        appearance=appearance_settings.resolve_appearance(
            document.get('appearance', {}),
            personal,
            permissions,
        ),
        appearance_permissions=permissions,
        personal_appearance=personal,
    )


_ADDRESS_SEARCH_LOCK = threading.Lock()
_ADDRESS_SEARCH_LAST = 0.0
_ADDRESS_SEARCH_CACHE = {}


def handle(handler, app, method):
    """Called before legacy handlers. Existing owner/session checks stay authoritative."""
    from urllib.parse import urlparse, parse_qs
    path = urlparse(handler.path).path
    owner_pages = (
        '/studio', '/studio.html',
        '/beta-admin', '/beta-admin.html',
        '/owner-builder', '/owner-builder.html',
        '/management-studio', '/management-studio.html',
    )
    studio_deploy_paths = ('/api/studio/deploy-info', '/api/studio/deploy')
    if path.startswith('/api/builder/') or path == '/api/user-appearance' or path == '/api/studio/update' or path in studio_deploy_paths or path in owner_pages:
        # Consume bounded request bodies before an authorization response. Closing
        # a Windows socket with unread input can discard the intended 401/403.
        try:
            length = int(handler.headers.get('Content-Length', '0'))
            if length < 0 or length > 1_000_000:
                handler.send_json(413, {'error': 'Request is too large.'})
                return True
            previous_timeout = handler.connection.gettimeout()
            try:
                handler.connection.settimeout(5)
                handler._builder_body = handler.rfile.read(length)
            finally:
                handler.connection.settimeout(previous_timeout)
        except (ValueError, TimeoutError, OSError):
            handler.close_connection = True
            handler.send_json(400, {'error': 'Invalid request body.'})
            return True
    if path == '/api/studio/update':
        if method != 'POST':
            handler.send_json(405, {'error': 'Unsupported action.'})
            return True
        if handler.client_address[0] not in ('127.0.0.1', '::1'):
            handler.send_json(403, {'error': 'Update is only available on this PC.'})
            return True
        if not handler.require_admin():
            return True
        if app.BETA_MODE:
            handler.send_json(403, {'error': 'Update from GitHub is for the local Management Studio.'})
            return True
        origin = handler.headers.get('Origin')
        host = handler.headers.get('Host', '')
        try:
            local_host = urlparse('//' + host).hostname
        except ValueError:
            local_host = None
        if local_host not in ('127.0.0.1', 'localhost', '::1'):
            handler.send_json(403, {'error': 'Use the local Align site on this PC.'})
            return True
        if origin not in (None, 'http://' + host):
            handler.send_json(403, {'error': 'Use the current Align site.'})
            return True
        try:
            import studio_update
            handler.send_json(200, studio_update.update_from_github(app.initialise_database))
        except (OSError, RuntimeError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
            handler.send_json(400, {'error': str(exc)})
        return True
    if path in ('/api/studio/deploy-info', '/api/studio/deploy'):
        expected_method = 'GET' if path.endswith('-info') else 'POST'
        if method != expected_method:
            handler.send_json(405, {'error': 'Unsupported action.'})
            return True
        if handler.client_address[0] not in ('127.0.0.1', '::1'):
            handler.send_json(403, {'error': 'Code releases are only available on this PC.'})
            return True
        if not handler.require_admin():
            return True
        if app.BETA_MODE:
            handler.send_json(403, {'error': 'Code releases are only available from the local Management Studio.'})
            return True
        origin = handler.headers.get('Origin')
        host = handler.headers.get('Host', '')
        try:
            local_host = urlparse('//' + host).hostname
        except ValueError:
            local_host = None
        if local_host not in ('127.0.0.1', 'localhost', '::1'):
            handler.send_json(403, {'error': 'Use the local Align site on this PC.'})
            return True
        if origin not in (None, 'http://' + host):
            handler.send_json(403, {'error': 'Use the current Align site.'})
            return True
        try:
            import studio_deploy
            if method == 'GET':
                result = studio_deploy.availability()
                result.update({
                    'default_ref': studio_deploy.DEFAULT_REF,
                    'workflow_url': studio_deploy.WORKFLOW_URL,
                })
                handler.send_json(200, result)
            else:
                body = json.loads(handler._builder_body or b'{}')
                if not isinstance(body, dict) or set(body) != {'ref', 'target'}:
                    raise ValueError('Choose a source branch and release target.')
                handler.send_json(202, studio_deploy.dispatch_release(body['ref'], body['target']))
        except (OSError, RuntimeError, ValueError) as exc:
            handler.send_json(400, {'error': str(exc)})
        return True
    if path in owner_pages:
        if method != 'GET': return False
        if not handler.require_admin(): return True
        handler.path = '/management-studio.html' if path in ('/studio', '/studio.html', '/beta-admin', '/beta-admin.html') or path.startswith('/management-studio') else '/owner-builder.html'
        from http.server import SimpleHTTPRequestHandler
        SimpleHTTPRequestHandler.do_GET(handler)
        return True
    if path == '/api/user-appearance':
        try:
            if method not in ('GET', 'PUT'):
                raise BuilderError('Unsupported action.', 405)
            if app.BETA_MODE and not handler.require_beta_user():
                return True
            if method == 'PUT':
                if app.BETA_MODE:
                    if not handler.beta_same_origin(): return True
                elif handler.headers.get('Origin') not in (None, 'http://' + handler.headers.get('Host', '')):
                    raise BuilderError('Use the current Align site.', 403)
            document = config(app.DATABASE)['published']
            permissions = appearance_settings.validate_permissions(
                document.get('appearance_permissions', {})
            )
            with app.db_connection() as c:
                ensure(c)
                row = c.execute(
                    "SELECT setting_value FROM settings WHERE setting_key='user_appearance'"
                ).fetchone()
                personal = json.loads(row['setting_value']) if row else {}
                if method == 'PUT':
                    body = json.loads(handler._builder_body or b'{}')
                    if not isinstance(body, dict) or set(body) - {'reset', 'appearance'}:
                        raise BuilderError('Invalid appearance request.')
                    if 'reset' in body and not isinstance(body['reset'], bool):
                        raise BuilderError('Invalid appearance reset option.')
                    if body.get('reset') is True:
                        if 'appearance' in body:
                            raise BuilderError('Choose reset or appearance changes, not both.')
                        personal = {}
                    else:
                        if not isinstance(body.get('appearance'), dict):
                            raise BuilderError('Appearance settings must be an object.')
                        personal = appearance_settings.validate_user_overrides(
                            body.get('appearance', {}),
                            permissions,
                        )
                    c.execute(
                        """INSERT INTO settings(setting_key,setting_value)
                           VALUES('user_appearance',?)
                           ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value""",
                        (json.dumps(personal),),
                    )
                    c.commit()
                effective = appearance_settings.resolve_appearance(
                    document.get('appearance', {}),
                    personal,
                    permissions,
                )
            handler.send_json(200, {
                'appearance': effective,
                'personal_appearance': personal,
                'appearance_permissions': permissions,
            })
            return True
        except (BuilderError, ValueError, sqlite3.Error) as exc:
            status = exc.status if isinstance(exc, BuilderError) else 400
            handler.send_json(status, {'error': str(exc)})
            return True
    if path == '/api/builder/accept-publish':
        try:
            if method != 'POST':
                raise BuilderError('Unsupported action.', 405)
            if not publish_key_matches(handler.headers.get('X-Align-Publish-Key', '')):
                handler.send_json(403, {'error': 'Publish key was not accepted.'})
                return True
            body = json.loads(handler._builder_body or b'{}')
            handler.send_json(200, publish_document(app.DATABASE, body.get('document')))
        except (BuilderError, ValueError, sqlite3.Error) as exc:
            status = exc.status if isinstance(exc, BuilderError) else 400
            handler.send_json(status, {'error': str(exc)})
        return True
    if path == '/api/studio/status':
        if method != 'GET':
            handler.send_json(405, {'error': 'Unsupported action.'})
            return True
        if not handler.require_admin():
            return True
        names = (
            'ALIGN_TRANSPORT_ENABLED', 'ALIGN_JOURNEY_PROVIDER',
            'ALIGN_HERE_ROUTING_KEY', 'ALIGN_HERE_TRANSIT_ENABLED',
            'ALIGN_GOOGLE_ROUTES_KEY', 'ALIGN_OTP_URL', 'ALIGN_NAPTAN_CSV',
            'ALIGN_BODS_LIVE_URL', 'ALIGN_BODS_TOKEN', 'ALIGN_DARWIN_LIVE_URL',
            'ALIGN_DARWIN_TOKEN', 'ALIGN_CREDENTIAL_KEY', 'DATABASE_URL',
            'AWS_ENDPOINT_URL_S3', 'AWS_REGION', 'AWS_ACCESS_KEY_ID',
            'AWS_SECRET_ACCESS_KEY', 'ALIGN_ASSET_BUCKET',
        )
        try:
            import here_quota
            quota = here_quota.usage_status()
        except Exception:
            quota = {'available': False, 'used': None, 'limit': 1000, 'remaining': None, 'next_available_at': None}
        try:
            with app.db_connection() as c:
                cloud = c.execute('SELECT account_hash,target_url,read_urls FROM icloud_config WHERE id=1').fetchone()
            icloud_status = 'Configured' if cloud and (cloud['account_hash'] or cloud['target_url'] or cloud['read_urls'] not in ('', '[]')) else 'Not configured'
        except (sqlite3.Error, RuntimeError):
            icloud_status = 'Status unavailable'
        handler.send_json(200, {
            'integrations': {name: bool(os.environ.get(name, '').strip()) for name in names},
            'here_quota': quota,
            'weather': config(app.DATABASE)['published'].get('base_structure', {}).get('weather', {}),
            'icloud': icloud_status,
            'icloud_privacy': 'Each tester’s calendar details remain private; account connection state is shown in Accounts.',
        })
        return True
    if path == '/api/sections/definitions':
        if method != 'GET':
            handler.send_json(405, {'error': 'Unsupported action.'})
            return True
        if app.BETA_MODE and not handler.require_beta_user():
            return True
        try:
            layouts = published_layouts(app.DATABASE)
            # Resolve optional-section state in the signed-in user's database.
            # Published definitions remain in the Owner database.
            if app.BETA_MODE:
                handler.activate_beta_database()
            with app.db_connection() as c:
                ensure(c)
                result = []
                # Published schema is global, but the user's private database
                # may not have had its section tables materialized yet.
                sync_published_sections(c, {'layouts': layouts}, max((layout.get('revision', 1) for layout in layouts), default=1))
                for layout in layouts:
                    definition = c.execute('SELECT icon,colour,sort_order,revision,published_revision FROM section_defs WHERE key=?', (layout['id'],)).fetchone()
                    opted_in = bool(c.execute("SELECT 1 FROM settings WHERE setting_key=?", ('section_opt_in_' + layout['id'],)).fetchone())
            result.append({
                        'key': layout['id'], 'name': layout['title'], 'icon': definition['icon'],
                        'colour': definition['colour'], 'sort_order': definition['sort_order'],
                        'revision': definition['revision'], 'published_revision': definition['published_revision'],
                        'description': layout.get('description', ''), 'view': layout.get('view', 'cards'),
                        'optional': bool(layout.get('optional')), 'enabled': opted_in if layout.get('optional') else True,
                        'fields': layout['fields'], 'finance': bool(layout.get('finance')),
                        'work_associations': layout.get('work_associations', {}) if layout['id'] == 'work' else {},
                    })
            handler.send_json(200, {'sections': result})
        except (BuilderError, ValueError, sqlite3.Error) as exc:
            handler.send_json(400, {'error': 'Section definitions could not be loaded.'})
        return True
    if not path.startswith('/api/builder/'):
        return False
    try:
        owner_action = path in ('/api/builder/config', '/api/builder/publish', '/api/builder/publish-everyone', '/api/builder/history', '/api/builder/restore')
        if owner_action:
            if not handler.require_admin(): return True
        elif app.BETA_MODE and not handler.require_beta_user(): return True
        if method != 'GET':
            if app.BETA_MODE:
                if not handler.beta_same_origin(): return True
            elif handler.headers.get('Origin') not in (None, 'http://' + handler.headers.get('Host', '')):
                raise BuilderError('Use the current Align site.', 403)
        if path == '/api/builder/address-search':
            if method != 'GET':
                raise BuilderError('Address search only supports GET.', 405)
            query = (parse_qs(urlparse(handler.path).query).get('q') or [''])[0].strip()
            if len(query) < 3:
                handler.send_json(200, {'results': []})
                return True
            if len(query) > 120:
                raise BuilderError('Search text is too long.', 400)
            cache_key = query.casefold()
            global _ADDRESS_SEARCH_LAST
            with _ADDRESS_SEARCH_LOCK:
                cached = _ADDRESS_SEARCH_CACHE.get(cache_key)
                if cached is not None:
                    results = cached
                else:
                    delay = 1.0 - (time.monotonic() - _ADDRESS_SEARCH_LAST)
                    if delay > 0:
                        time.sleep(delay)
                    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode({
                        'q': query,
                        'format': 'jsonv2',
                        'addressdetails': 1,
                        'limit': 5,
                        'countrycodes': 'gb',
                    })
                    request = urllib.request.Request(url, headers={
                        'User-Agent': 'Align-V3.0/1.0 address-autocomplete',
                        'Accept': 'application/json',
                    })
                    try:
                        with urllib.request.urlopen(request, timeout=5) as response:
                            payload = json.loads(response.read(500_000).decode('utf-8'))
                    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                        raise BuilderError('Address suggestions are temporarily unavailable. Enter the address manually.', 503) from exc
                    _ADDRESS_SEARCH_LAST = time.monotonic()
                    results = []
                    for item in payload if isinstance(payload, list) else []:
                        address = item.get('address') or {}
                        town = address.get('town') or address.get('city') or address.get('village') or address.get('hamlet') or address.get('suburb') or ''
                        results.append({
                            'label': text(item.get('display_name', ''), 500),
                            'postcode': text(address.get('postcode', ''), 30),
                            'town': text(town, 120),
                            'country': text(address.get('country', ''), 80),
                            'latitude': float(item['lat']) if item.get('lat') else None,
                            'longitude': float(item['lon']) if item.get('lon') else None,
                            'place_id': text(str(item.get('osm_type', '')) + ':' + str(item.get('osm_id', '')), 80),
                        })
                    _ADDRESS_SEARCH_CACHE[cache_key] = results
                    if len(_ADDRESS_SEARCH_CACHE) > 100:
                        _ADDRESS_SEARCH_CACHE.pop(next(iter(_ADDRESS_SEARCH_CACHE)))
            handler.send_json(200, {'results': results})
            return True
        if owner_action:
            if method == 'GET' and path.endswith('/history'):
                handler.send_json(200, history(app.DATABASE))
            elif method == 'POST' and path.endswith('/restore'):
                handler.send_json(200, restore_history(app.DATABASE, json.loads(handler._builder_body or b'{}')))
            elif method == 'GET' and path.endswith('/config'):
                handler.send_json(200, config(app.DATABASE))
            elif method == 'POST' and path == '/api/builder/publish-everyone':
                handler.send_json(200, publish_to_everyone(app.DATABASE, json.loads(handler._builder_body or b'{}'), handler, app))
            elif method == 'PUT' and path.endswith('/config') or method == 'POST' and path == '/api/builder/publish':
                handler.send_json(200, save_config(app.DATABASE, json.loads(handler._builder_body or b'{}'), publish=path.endswith('/publish')))
            else: raise BuilderError('Unsupported action.', 405)
            return True
        doc = config(app.DATABASE)['published']
        # User database records, including optional Work opt-in, are private to
        # the authenticated account. Route through that account before opening
        # any builder_records/settings tables.
        if app.BETA_MODE:
            handler.activate_beta_database()
        with app.db_connection() as c:
            ensure(c)
            if path == '/api/builder/profile' and method == 'PUT':
                values = values_validate(doc['startup']['fields'], handler.read_json().get('values'))
                values = {**profile(c), **values}
                c.execute("INSERT INTO settings VALUES('builder_profile',?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value", (json.dumps(values),))
                for key in ('user_name', 'user_address', 'user_phone', 'user_home_location', 'travel_bus', 'travel_rail', 'travel_walk'):
                    if key in values:
                        c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value', (key, json.dumps(values[key]) if isinstance(values[key], bool) else str(values[key])))
                modes = [mode for key, mode in (('travel_bus','bus'), ('travel_rail','rail'), ('travel_walk','walk')) if values.get(key) is True]
                c.execute("UPDATE transport_preferences SET modes=? WHERE id=1", (json.dumps(modes),))
                c.execute("""INSERT INTO settings(setting_key,setting_value)
                    VALUES('onboarding_completed','1')
                    ON CONFLICT(setting_key) DO UPDATE SET setting_value='1'""")
                # Persist before acknowledging success to an immediately reloading client.
                c.commit()
                handler.send_json(200, {'saved': True})
                return True
            match = re.fullmatch(r'/api/builder/records/([a-zA-Z][\w-]*)(?:/([a-zA-Z][\w-]*))?', path)
            if not match: raise BuilderError('Not found.', 404)
            lid, rid = match.groups()
            layout = next((x for x in published_layouts(app.DATABASE) if x['id'] == lid), None)
            if not layout: raise BuilderError('This layout is no longer available.', 404)
            opted_in = bool(c.execute("SELECT 1 FROM settings WHERE setting_key=?", ('section_opt_in_' + lid,)).fetchone())
            if layout.get('optional') and not opted_in and method == 'GET' and not rid:
                handler.send_json(403, {'error': 'Add this optional database to your account before opening it.'})
                return True
            if layout.get('optional') and method == 'POST' and rid == 'enable':
                c.execute("INSERT INTO settings(setting_key,setting_value) VALUES(?, '1') ON CONFLICT(setting_key) DO UPDATE SET setting_value='1'", ('section_opt_in_' + lid,))
                handler.send_json(200, {'enabled': True, 'layout': layout})
                return True
            if layout.get('optional') and not opted_in:
                raise BuilderError('Add this optional database to your account before opening it.', 403)
            if method == 'GET' and not rid:
                query = parse_qs(urlparse(handler.path).query)
                archived = int(query.get('archived', ['0'])[0] == '1')
                result = []
                for row in c.execute('SELECT * FROM builder_records WHERE layout_id=? AND archived=? ORDER BY created_at DESC,id', (lid, archived)):
                    item = dict(row)
                    item['values'] = json.loads(item.pop('values_json'))
                    try:
                        item['values'] = bill_calculations.calculate(layout['fields'], item['values'])
                        if layout.get('finance'): item['values'] = builder_finance.calculate(item['values'])
                    except ValueError as exc:
                        item['calculation_error'] = str(exc)
                        if layout.get('finance'):
                            item['values']['payment_amount'] = ''
                            item['values']['monthly_amount'] = ''
                        for field in layout['fields']:
                            if field['type'] == 'formula': item['values'][field['id']] = ''
                    result.append(item)
                handler.send_json(200, {'records': result, 'layout': layout})
            elif method in ('POST', 'PUT'):
                body = handler.read_json()
                if method == 'POST' and rid == 'preview':
                    values = record_values(layout, body.get('values'))
                    handler.send_json(200, {'values': values})
                    return True
                if method == 'POST' and rid or method == 'PUT' and not rid: raise BuilderError('Unsupported action.', 405)
                old = c.execute('SELECT * FROM builder_records WHERE id=? AND layout_id=?', (rid, lid)).fetchone() if rid else None
                if rid and not old: raise BuilderError('Record not found.', 404)
                if old and body.get('revision') != old['revision']: raise BuilderError('This record changed. Reload before editing.', 409)
                values = {**(json.loads(old['values_json']) if old else {}), **record_values(layout, body.get('values'))}
                if old:
                    updated = c.execute('UPDATE builder_records SET values_json=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND revision=?', (json.dumps(values), rid, old['revision']))
                    if not updated.rowcount: raise BuilderError('This record changed. Reload before editing.', 409)
                else:
                    rid = identity(body.get('id'))
                    existing = c.execute('SELECT * FROM builder_records WHERE id=?', (rid,)).fetchone()
                    if existing:
                        if existing['layout_id'] != lid or json.loads(existing['values_json']) != values: raise BuilderError('Record identifier already used.', 409)
                    else:
                        c.execute('INSERT INTO builder_records(id,layout_id,values_json) VALUES(?,?,?)', (rid, lid, json.dumps(values)))
                handler.send_json(200, {'id': rid})
            elif method == 'DELETE' and rid:
                body = handler.read_json()
                archived = 0 if body.get('restore') else 1
                updated = c.execute('UPDATE builder_records SET archived=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND layout_id=? AND revision=?', (archived, rid, lid, body.get('revision')))
                if not updated.rowcount: raise BuilderError('Record changed or no longer exists. Reload the list.', 409)
                handler.send_json(200, {'archived': bool(archived)})
            else: raise BuilderError('Unsupported action.', 405)
        return True
    except BuilderError as exc:
        handler.send_json(exc.status, {'error': str(exc)})
    except (ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        handler.send_json(400, {'error': 'Unable to save. Check the fields and try again.'})
    return True
