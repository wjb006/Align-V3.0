-- Fresh Align V3.0 SQLite schema for local/offline development. No legacy schedule tables.

-- Existing SQLite files containing the legacy shifts table use the compatibility initializer and are never truncated.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS menu_branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '○',
    branch_type TEXT NOT NULL DEFAULT 'note',
    content TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS parent_menu_branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '○',
    destination TEXT NOT NULL DEFAULT 'note',
    content TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 100,
    parent_id INTEGER REFERENCES parent_menu_branches(id) ON DELETE SET NULL,
    colour TEXT NOT NULL DEFAULT '#365CE6',
    locked INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1)),
    optional INTEGER NOT NULL DEFAULT 1 CHECK (optional IN (0, 1))
);

CREATE TABLE IF NOT EXISTS organiser_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '•',
    colour TEXT NOT NULL DEFAULT '#365CE6',
    calendar_url TEXT NOT NULL DEFAULT '',
    calendar_name TEXT NOT NULL DEFAULT '',
    import_enabled INTEGER NOT NULL DEFAULT 1 CHECK (import_enabled IN (0, 1)),
    export_enabled INTEGER NOT NULL DEFAULT 1 CHECK (export_enabled IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 100,
    parent_branch_id INTEGER REFERENCES parent_menu_branches(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS calendar_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_kind TEXT NOT NULL,
    target_key TEXT NOT NULL,
    calendar_url TEXT NOT NULL,
    calendar_name TEXT NOT NULL DEFAULT '',
    import_enabled INTEGER NOT NULL DEFAULT 1 CHECK (import_enabled IN (0, 1)),
    export_enabled INTEGER NOT NULL DEFAULT 1 CHECK (export_enabled IN (0, 1)),
    UNIQUE(target_kind, target_key)
);

CREATE TABLE IF NOT EXISTS organiser_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL REFERENCES organiser_sections(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    all_day INTEGER NOT NULL DEFAULT 0 CHECK (all_day IN (0, 1)),
    location TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    request_id TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    address TEXT NOT NULL DEFAULT '',
    colour TEXT NOT NULL DEFAULT '#365CE6',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shift_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    colour TEXT NOT NULL DEFAULT '#3B82F6',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

-- Categories (for example Wards and Clinic) that are offered at each work
-- location.  Saved shift patterns then provide the actual AM/PM hours.
CREATE TABLE IF NOT EXISTS location_shift_types (
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE CASCADE,
    PRIMARY KEY (location_id, shift_type_id)
);

CREATE TABLE IF NOT EXISTS shift_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE RESTRICT,
    label TEXT NOT NULL,
    sub_shift_type TEXT NOT NULL DEFAULT '',
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    break_minutes INTEGER NOT NULL DEFAULT 0 CHECK (break_minutes >= 0),
    applicable_days TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    UNIQUE(location_id, label)
);

CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_date TEXT NOT NULL,
    template_id INTEGER REFERENCES shift_templates(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    shift_type_id INTEGER REFERENCES shift_types(id) ON DELETE SET NULL,
    location_name TEXT NOT NULL,
    shift_type_name TEXT NOT NULL,
    colour TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    break_minutes INTEGER NOT NULL DEFAULT 0,
    hours REAL NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_shifts_date ON shifts(work_date);
CREATE INDEX IF NOT EXISTS idx_shifts_template ON shifts(template_id);

-- A repeated Confirm request must not create the week twice after a timeout.
CREATE TABLE IF NOT EXISTS shift_batches (
    request_id TEXT PRIMARY KEY,
    payload_hash TEXT NOT NULL,
    result_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annual_leave (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leave_date TEXT NOT NULL UNIQUE,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_leave_date ON annual_leave(leave_date);


CREATE TABLE IF NOT EXISTS calendar_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_kind TEXT NOT NULL DEFAULT 'ics_import',
    section_id INTEGER REFERENCES organiser_sections(id) ON DELETE CASCADE,
    target_kind TEXT NOT NULL DEFAULT '',
    target_key TEXT NOT NULL DEFAULT '',
    source_key TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES calendar_sources(id) ON DELETE CASCADE,
    event_uid TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    all_day INTEGER NOT NULL DEFAULT 0 CHECK (all_day IN (0, 1)),
    UNIQUE(source_id, event_uid)
);

CREATE TABLE IF NOT EXISTS icloud_config (
    id INTEGER PRIMARY KEY CHECK(id=1), instance_id TEXT NOT NULL DEFAULT '',
    account_hash TEXT NOT NULL DEFAULT '', target_url TEXT NOT NULL DEFAULT '',
    read_urls TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS icloud_items (
    local_key TEXT PRIMARY KEY, uid TEXT NOT NULL UNIQUE, url TEXT NOT NULL,
    etag TEXT NOT NULL, content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_sync_state (
    id INTEGER PRIMARY KEY CHECK (id=1),
    revision INTEGER NOT NULL DEFAULT 0,
    modified_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_menu_branches_order ON menu_branches(active, sort_order, title);

CREATE INDEX IF NOT EXISTS idx_parent_menu_order ON parent_menu_branches(active, parent_id, sort_order, title);

CREATE INDEX IF NOT EXISTS idx_organiser_sections_order ON organiser_sections(active, sort_order, name);

CREATE INDEX IF NOT EXISTS idx_calendar_links_target ON calendar_links(target_kind, target_key);

CREATE INDEX IF NOT EXISTS idx_organiser_events_section_time ON organiser_events(section_id, start_at, end_at);

CREATE INDEX IF NOT EXISTS idx_calendar_events_start ON calendar_events(start_at, end_at);


CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS personal_items (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    due_at TEXT NOT NULL DEFAULT '',
    done INTEGER NOT NULL DEFAULT 0,
    calendar_id TEXT NOT NULL DEFAULT '',
    calendar_event_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS builder_config (
    id INTEGER PRIMARY KEY CHECK(id=1),
    revision INTEGER NOT NULL,
    published_revision INTEGER NOT NULL,
    draft TEXT NOT NULL,
    published TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS builder_records (
    id TEXT PRIMARY KEY,
    layout_id TEXT NOT NULL,
    values_json TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- Executed statement-by-statement inside the migration runner's transaction.
CREATE TABLE IF NOT EXISTS assets (
 asset_id INTEGER PRIMARY KEY AUTOINCREMENT, asset_key TEXT NOT NULL UNIQUE CHECK(length(asset_key) BETWEEN 1 AND 80 AND asset_key NOT GLOB '*[^a-z0-9_]*'), display_name TEXT NOT NULL CHECK(length(trim(display_name)) BETWEEN 1 AND 60),
 asset_type TEXT NOT NULL CHECK(asset_type IN ('emoji','place','workplace','event_type','travel','section','general_image','other')), category_id INTEGER NULL REFERENCES asset_categories(category_id) ON DELETE SET NULL,
 style TEXT NOT NULL DEFAULT 'align_emoji' CHECK(style IN ('align_emoji','simple_icon','illustration','photo','custom')), direction TEXT NULL CHECK(direction IS NULL OR direction IN ('outbound','return')), travel_mode TEXT NULL CHECK(travel_mode IS NULL OR travel_mode IN ('bus','rail','walk','drive','cycle','other')),
 original_filename TEXT NOT NULL, original_mime_type TEXT NOT NULL CHECK(original_mime_type IN ('image/png','image/jpeg','image/webp')), original_width INTEGER CHECK(original_width IS NULL OR original_width BETWEEN 1 AND 8192), original_height INTEGER CHECK(original_height IS NULL OR original_height BETWEEN 1 AND 8192), original_file_size INTEGER CHECK(original_file_size IS NULL OR original_file_size BETWEEN 0 AND 10485760), content_sha256 TEXT CHECK(content_sha256 IS NULL OR (length(content_sha256)=64 AND content_sha256 NOT GLOB '*[^0-9A-Fa-f]*')),
 background_mode TEXT NOT NULL DEFAULT 'keep' CHECK(background_mode IN ('keep','transparent','solid')), background_colour TEXT, crop_mode TEXT NOT NULL DEFAULT 'fit' CHECK(crop_mode IN ('fit','square','centre_crop','custom')), crop_x REAL, crop_y REAL, crop_width REAL, crop_height REAL,
 alignment_horizontal TEXT NOT NULL DEFAULT 'centre' CHECK(alignment_horizontal IN ('left','centre','right')), alignment_vertical TEXT NOT NULL DEFAULT 'centre' CHECK(alignment_vertical IN ('top','centre','bottom')), padding_percent INTEGER NOT NULL DEFAULT 10 CHECK(padding_percent BETWEEN 0 AND 30), match_align_sizing INTEGER NOT NULL DEFAULT 1 CHECK(match_align_sizing IN (0,1)), status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','processing','active','inactive','error')), processing_error TEXT, active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0,1)), version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1), created_by TEXT NOT NULL, updated_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 CHECK((status='active' AND active=1) OR (status<>'active' AND active=0)), CHECK((asset_type='travel') OR (direction IS NULL AND travel_mode IS NULL)), CHECK(background_mode<>'solid' OR (background_colour IS NOT NULL AND background_colour GLOB '#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]')), CHECK(crop_mode<>'custom' OR (crop_x IS NOT NULL AND crop_y IS NOT NULL AND crop_width IS NOT NULL AND crop_height IS NOT NULL AND crop_x>=0 AND crop_y>=0 AND crop_width>0 AND crop_height>0))
);
CREATE TABLE IF NOT EXISTS asset_categories (
 category_id INTEGER PRIMARY KEY AUTOINCREMENT, category_group TEXT NOT NULL CHECK(category_group IN ('place','workplace','event_type','travel','section','other')), category_key TEXT NOT NULL CHECK(length(category_key) BETWEEN 1 AND 80 AND category_key NOT GLOB '*[^a-z0-9_]*'), display_name TEXT NOT NULL CHECK(length(trim(display_name)) BETWEEN 1 AND 60), default_asset_id INTEGER NULL REFERENCES assets(asset_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED, sort_order INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), built_in INTEGER NOT NULL DEFAULT 0 CHECK(built_in IN (0,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(category_group,category_key)
);
CREATE TABLE IF NOT EXISTS asset_variants (variant_id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id INTEGER NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE, variant_type TEXT NOT NULL CHECK(variant_type IN ('original','small','medium','large')), width INTEGER NOT NULL CHECK(width BETWEEN 1 AND 8192), height INTEGER NOT NULL CHECK(height BETWEEN 1 AND 8192), mime_type TEXT NOT NULL CHECK(mime_type IN ('image/png','image/jpeg','image/webp')), stored_filename TEXT NOT NULL, storage_path TEXT NOT NULL UNIQUE, file_size INTEGER NOT NULL CHECK(file_size BETWEEN 0 AND 10485760), content_sha256 TEXT CHECK(content_sha256 IS NULL OR (length(content_sha256)=64 AND content_sha256 NOT GLOB '*[^0-9A-Fa-f]*')), created_at TEXT NOT NULL, UNIQUE(asset_id,variant_type));
CREATE TABLE IF NOT EXISTS asset_usage_rules (asset_id INTEGER NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE, usage_area TEXT NOT NULL CHECK(usage_area IN ('today','planner','event_editor','workplace_selector','saved_places','sections','travel')), enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)), PRIMARY KEY(asset_id,usage_area));
CREATE TABLE IF NOT EXISTS asset_audit_log (audit_id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id INTEGER NULL REFERENCES assets(asset_id) ON DELETE SET NULL, action TEXT NOT NULL CHECK(action IN ('created','updated','processed','activated','deactivated','replaced','deleted','category_changed')), actor_user_id TEXT NOT NULL, details_json TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_assets_type_status ON assets(asset_type,status); CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category_id); CREATE INDEX IF NOT EXISTS idx_assets_active_type ON assets(asset_type,active); CREATE INDEX IF NOT EXISTS idx_assets_display_name ON assets(display_name COLLATE NOCASE); CREATE INDEX IF NOT EXISTS idx_assets_content_sha256 ON assets(content_sha256) WHERE content_sha256 IS NOT NULL; CREATE INDEX IF NOT EXISTS idx_asset_variants_asset ON asset_variants(asset_id); CREATE INDEX IF NOT EXISTS idx_asset_variants_hash ON asset_variants(content_sha256) WHERE content_sha256 IS NOT NULL; CREATE INDEX IF NOT EXISTS idx_asset_usage_enabled ON asset_usage_rules(usage_area,enabled,asset_id); CREATE INDEX IF NOT EXISTS idx_asset_categories_group ON asset_categories(category_group,active,sort_order); CREATE INDEX IF NOT EXISTS idx_asset_categories_display_name ON asset_categories(display_name COLLATE NOCASE); CREATE INDEX IF NOT EXISTS idx_asset_audit_asset_date ON asset_audit_log(asset_id,created_at DESC); CREATE INDEX IF NOT EXISTS idx_asset_audit_actor_date ON asset_audit_log(actor_user_id,created_at DESC);
CREATE TRIGGER IF NOT EXISTS asset_category_default_active_insert BEFORE INSERT ON asset_categories WHEN NEW.default_asset_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM assets WHERE asset_id=NEW.default_asset_id AND active=1) BEGIN SELECT RAISE(ABORT,'category default asset must exist and be active'); END;
CREATE TRIGGER IF NOT EXISTS asset_category_default_active_update BEFORE UPDATE OF default_asset_id ON asset_categories WHEN NEW.default_asset_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM assets WHERE asset_id=NEW.default_asset_id AND active=1) BEGIN SELECT RAISE(ABORT,'category default asset must exist and be active'); END;
CREATE TRIGGER IF NOT EXISTS asset_activation_insert BEFORE INSERT ON assets WHEN NEW.active=1 BEGIN SELECT RAISE(ABORT,'Create a draft, add a processed variant and enabled usage, then activate'); END;
CREATE TRIGGER IF NOT EXISTS asset_activation_update BEFORE UPDATE ON assets BEGIN
 SELECT CASE WHEN NEW.active=1 AND NOT EXISTS(SELECT 1 FROM asset_variants WHERE asset_id=NEW.asset_id AND variant_type IN ('small','medium','large')) THEN RAISE(ABORT,'active asset requires processed variant') END;
 SELECT CASE WHEN NEW.active=1 AND NOT EXISTS(SELECT 1 FROM asset_usage_rules WHERE asset_id=NEW.asset_id AND enabled=1) THEN RAISE(ABORT,'active asset requires enabled usage') END;
 SELECT CASE WHEN NEW.active=0 AND EXISTS(SELECT 1 FROM asset_categories WHERE default_asset_id=OLD.asset_id) THEN RAISE(ABORT,'Clear category default before deactivation') END;
END;
INSERT OR IGNORE INTO asset_categories(category_group,category_key,display_name,sort_order,built_in,created_at,updated_at) VALUES
 ('workplace','home_remote','Home / Remote',10,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),('workplace','healthcare','Healthcare',20,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),('workplace','office','Office / Administration',30,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),('workplace','trades','Trades / Maintenance',40,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),('workplace','utilities','Utilities / Technical',50,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),('workplace','hospitality','Hospitality / Food',60,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),('workplace','retail','Retail',70,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),('workplace','school','School / Education',80,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),('workplace','university','University / Higher Education',90,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),('workplace','warehouse','Warehouse / Logistics',100,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),('workplace','construction','Construction / Site Work',110,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),('workplace','other','Other',999,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO asset_categories(category_group,category_key,display_name,built_in,created_at,updated_at) SELECT 'event_type',value,replace(value,'_',' '),1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM json_each('["shift","clinic","ward","office","meeting","training","appointment","site_visit","call_out","maintenance","delivery_collection","retail_shift","hospitality_shift","construction_shift","warehouse_shift","remote_work","personal","health","social","travel","errand","shopping","exercise","study","meal","other"]');
INSERT OR IGNORE INTO asset_categories(category_group,category_key,display_name,built_in,created_at,updated_at) SELECT 'place',value,value,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM json_each('["home","work","healthcare","education","shopping","other"]');
INSERT OR IGNORE INTO asset_categories(category_group,category_key,display_name,built_in,created_at,updated_at) SELECT 'travel',value,value,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM json_each('["walk","bus","rail","drive","cycle","other"]');
-- The runner writes the marker only after all migration statements succeed.



CREATE TABLE IF NOT EXISTS transport_preferences (id INTEGER PRIMARY KEY CHECK(id=1), arrival_buffer INTEGER NOT NULL DEFAULT 10 CHECK(arrival_buffer BETWEEN 0 AND 120), modes TEXT NOT NULL DEFAULT '["bus","rail","walk"]', home_lat REAL, home_lon REAL);
INSERT OR IGNORE INTO transport_preferences(id) VALUES(1);
-- Build 146 shipped a different transport_cache schema. Keep that table and
-- its rows intact; Build 149 journey payloads use their own table.
CREATE TABLE IF NOT EXISTS transport_journey_cache (event_key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_transport_journey_cache_expiry ON transport_journey_cache(expires_at);


CREATE TABLE IF NOT EXISTS calendar_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_kind TEXT NOT NULL,
    target_key TEXT NOT NULL,
    calendar_url TEXT NOT NULL,
    calendar_name TEXT NOT NULL DEFAULT '',
    import_enabled INTEGER NOT NULL DEFAULT 1 CHECK (import_enabled IN (0, 1)),
    export_enabled INTEGER NOT NULL DEFAULT 1 CHECK (export_enabled IN (0, 1)),
    UNIQUE(target_kind, target_key)
);
CREATE INDEX IF NOT EXISTS idx_calendar_links_target
    ON calendar_links(target_kind, target_key);


CREATE TABLE IF NOT EXISTS section_defs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT '◫',
    colour TEXT NOT NULL DEFAULT '#365CE6',
    sort_order INTEGER NOT NULL DEFAULT 100,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    revision INTEGER NOT NULL DEFAULT 1,
    published_revision INTEGER NOT NULL DEFAULT 0,
    layout_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_section_defs_published
    ON section_defs(active, published_revision, revision, sort_order);
CREATE TABLE IF NOT EXISTS section_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL REFERENCES section_defs(id) ON DELETE CASCADE,
    field_key TEXT NOT NULL,
    label TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('text','number','date','select','checkbox','tel','textarea','calculated')),
    required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1)),
    options_json TEXT NOT NULL DEFAULT '[]',
    validation_json TEXT NOT NULL DEFAULT '{}',
    formula TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 100,
    UNIQUE(section_id, field_key)
);
CREATE INDEX IF NOT EXISTS idx_section_fields_order ON section_fields(section_id, sort_order, id);


CREATE TRIGGER IF NOT EXISTS sync_organiser_events_insert AFTER INSERT ON organiser_events BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_organiser_events_update AFTER UPDATE ON organiser_events BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_organiser_events_delete AFTER DELETE ON organiser_events BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_organiser_sections_insert AFTER INSERT ON organiser_sections BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_organiser_sections_update AFTER UPDATE ON organiser_sections BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_organiser_sections_delete AFTER DELETE ON organiser_sections BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_calendar_sources_insert AFTER INSERT ON calendar_sources BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_calendar_sources_update AFTER UPDATE ON calendar_sources BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_calendar_sources_delete AFTER DELETE ON calendar_sources BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_calendar_events_insert AFTER INSERT ON calendar_events BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_calendar_events_update AFTER UPDATE ON calendar_events BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_calendar_events_delete AFTER DELETE ON calendar_events BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_calendar_links_insert AFTER INSERT ON calendar_links BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_calendar_links_update AFTER UPDATE ON calendar_links BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_calendar_links_delete AFTER DELETE ON calendar_links BEGIN
    UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
  END;

CREATE TRIGGER IF NOT EXISTS sync_calendar_settings AFTER UPDATE ON settings
WHEN NEW.setting_key IN ('notifications','default_calendar') BEGIN
  UPDATE calendar_sync_state SET revision=revision+1, modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1;
END;

INSERT OR IGNORE INTO icloud_config(id) VALUES(1);

INSERT OR IGNORE INTO calendar_sync_state(id,modified_at) VALUES(1,strftime('%Y%m%dT%H%M%SZ','now'));

CREATE TABLE IF NOT EXISTS user_favourites (
    id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL, entity_key TEXT NOT NULL,
    label TEXT NOT NULL, value TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(entity_type, entity_key)
);
CREATE INDEX IF NOT EXISTS idx_user_favourites_type_updated ON user_favourites(entity_type, updated_at DESC);
CREATE TABLE IF NOT EXISTS align_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, address TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, UNIQUE(name,address,phone)
);
INSERT OR IGNORE INTO schema_migrations(migration_id,applied_at) VALUES ('149_asset_studio',CURRENT_TIMESTAMP),('149_transport',CURRENT_TIMESTAMP),('150_calendar_links',CURRENT_TIMESTAMP),('151_sections',CURRENT_TIMESTAMP),('152_personal_item_calendars',CURRENT_TIMESTAMP),('154_user_favourites_contacts',CURRENT_TIMESTAMP);
