-- Situation Room tables for cached external intelligence data

CREATE TABLE IF NOT EXISTS sitroom_news (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash  TEXT    UNIQUE,
    title         TEXT    NOT NULL,
    link          TEXT    DEFAULT '',
    description   TEXT    DEFAULT '',
    published     TEXT    DEFAULT '',
    source_name   TEXT    DEFAULT '',
    category      TEXT    DEFAULT '',
    source_type   TEXT    DEFAULT 'rss',
    cached_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sitroom_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT    UNIQUE,
    event_type    TEXT    NOT NULL,
    title         TEXT    DEFAULT '',
    magnitude     REAL,
    lat           REAL    DEFAULT 0,
    lng           REAL    DEFAULT 0,
    depth_km      REAL    DEFAULT 0,
    event_time    INTEGER DEFAULT 0,
    source_url    TEXT    DEFAULT '',
    detail_json   TEXT    DEFAULT '{}',
    cached_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sitroom_markets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT    NOT NULL,
    price         REAL    DEFAULT 0,
    change_24h    REAL    DEFAULT 0,
    market_type   TEXT    DEFAULT 'other',
    label         TEXT    DEFAULT '',
    cached_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sitroom_custom_feeds (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    url           TEXT    NOT NULL,
    category      TEXT    DEFAULT 'Custom',
    enabled       INTEGER DEFAULT 1,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sitroom_briefings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content       TEXT    NOT NULL,
    generated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_sitroom_news_category ON sitroom_news(category);
CREATE INDEX IF NOT EXISTS idx_sitroom_news_cached ON sitroom_news(cached_at DESC);
CREATE INDEX IF NOT EXISTS idx_sitroom_news_hash ON sitroom_news(content_hash);
CREATE INDEX IF NOT EXISTS idx_sitroom_events_type ON sitroom_events(event_type);
CREATE INDEX IF NOT EXISTS idx_sitroom_events_cached ON sitroom_events(cached_at DESC);
CREATE INDEX IF NOT EXISTS idx_sitroom_events_mag ON sitroom_events(magnitude DESC);
CREATE INDEX IF NOT EXISTS idx_sitroom_markets_type ON sitroom_markets(market_type);
CREATE INDEX IF NOT EXISTS idx_sitroom_briefings_date ON sitroom_briefings(generated_at DESC);
