"""Situation Room — World Monitor-inspired global intelligence dashboard.

Aggregates RSS news, earthquakes, weather alerts, financial markets,
conflict data, and infrastructure status. All data is cached to SQLite
for offline access. Online sources are fetched in background threads.
"""

import json
import logging
import threading
import time
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests
from flask import Blueprint, request, jsonify
from db import get_db, db_session, log_activity

situation_room_bp = Blueprint('situation_room', __name__)
log = logging.getLogger('nomad.situation_room')

# ─── Background Fetch State ────────────────────────────────────────────
_fetch_lock = threading.Lock()
_last_fetch = {}  # source_key -> datetime
_fetch_running = False

# Minimum interval between fetches per source (seconds)
FETCH_COOLDOWN = {
    'rss': 300,         # 5 min
    'earthquakes': 120, # 2 min
    'weather_alerts': 300,
    'markets': 300,
    'conflicts': 600,
    'power_outages': 600,
    'cyber': 600,
}

# ─── RSS Feed Sources (curated, categorized) ──────────────────────────
RSS_FEEDS = {
    'world_news': [
        {'name': 'Reuters World', 'url': 'https://feeds.reuters.com/Reuters/worldNews', 'category': 'World'},
        {'name': 'AP Top Headlines', 'url': 'https://rsshub.app/apnews/topics/apf-topnews', 'category': 'World'},
        {'name': 'BBC World', 'url': 'https://feeds.bbci.co.uk/news/world/rss.xml', 'category': 'World'},
        {'name': 'Al Jazeera', 'url': 'https://www.aljazeera.com/xml/rss/all.xml', 'category': 'World'},
    ],
    'us_news': [
        {'name': 'Reuters US', 'url': 'https://feeds.reuters.com/Reuters/domesticNews', 'category': 'US'},
        {'name': 'NPR Headlines', 'url': 'https://feeds.npr.org/1001/rss.xml', 'category': 'US'},
        {'name': 'PBS NewsHour', 'url': 'https://www.pbs.org/newshour/feeds/rss/headlines', 'category': 'US'},
    ],
    'technology': [
        {'name': 'Ars Technica', 'url': 'https://feeds.arstechnica.com/arstechnica/technology-lab', 'category': 'Tech'},
        {'name': 'Hacker News', 'url': 'https://hnrss.org/frontpage', 'category': 'Tech'},
        {'name': 'The Verge', 'url': 'https://www.theverge.com/rss/index.xml', 'category': 'Tech'},
        {'name': 'TechCrunch', 'url': 'https://techcrunch.com/feed/', 'category': 'Tech'},
    ],
    'science': [
        {'name': 'Nature News', 'url': 'https://www.nature.com/nature.rss', 'category': 'Science'},
        {'name': 'NASA Breaking', 'url': 'https://www.nasa.gov/rss/dyn/breaking_news.rss', 'category': 'Science'},
        {'name': 'Science Daily', 'url': 'https://www.sciencedaily.com/rss/all.xml', 'category': 'Science'},
    ],
    'security': [
        {'name': 'Krebs on Security', 'url': 'https://krebsonsecurity.com/feed/', 'category': 'Cyber'},
        {'name': 'The Hacker News', 'url': 'https://feeds.feedburner.com/TheHackersNews', 'category': 'Cyber'},
        {'name': 'BleepingComputer', 'url': 'https://www.bleepingcomputer.com/feed/', 'category': 'Cyber'},
        {'name': 'Dark Reading', 'url': 'https://www.darkreading.com/rss_simple.asp', 'category': 'Cyber'},
    ],
    'military_defense': [
        {'name': 'Defense One', 'url': 'https://www.defenseone.com/rss/', 'category': 'Defense'},
        {'name': 'War on the Rocks', 'url': 'https://warontherocks.com/feed/', 'category': 'Defense'},
        {'name': 'Breaking Defense', 'url': 'https://breakingdefense.com/feed/', 'category': 'Defense'},
        {'name': 'The Drive - War Zone', 'url': 'https://www.thedrive.com/the-war-zone/feed', 'category': 'Defense'},
    ],
    'disasters': [
        {'name': 'GDACS Alerts', 'url': 'https://www.gdacs.org/xml/rss.xml', 'category': 'Disaster'},
        {'name': 'ReliefWeb Updates', 'url': 'https://reliefweb.int/updates/rss.xml', 'category': 'Disaster'},
        {'name': 'FEMA', 'url': 'https://www.fema.gov/feeds/disasters-702-702all.xml', 'category': 'Disaster'},
    ],
    'finance': [
        {'name': 'MarketWatch Top', 'url': 'https://feeds.content.dowjones.io/public/rss/mw_topstories', 'category': 'Finance'},
        {'name': 'CNBC Top News', 'url': 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114', 'category': 'Finance'},
        {'name': 'Bloomberg Markets', 'url': 'https://feeds.bloomberg.com/markets/news.rss', 'category': 'Finance'},
    ],
    'energy': [
        {'name': 'EIA Today in Energy', 'url': 'https://www.eia.gov/rss/todayinenergy.xml', 'category': 'Energy'},
        {'name': 'OilPrice.com', 'url': 'https://oilprice.com/rss/main', 'category': 'Energy'},
    ],
    'health': [
        {'name': 'WHO Disease Outbreaks', 'url': 'https://www.who.int/feeds/entity/don/en/rss.xml', 'category': 'Health'},
        {'name': 'CDC MMWR', 'url': 'https://tools.cdc.gov/api/v2/resources/media/316422.rss', 'category': 'Health'},
        {'name': 'CIDRAP News', 'url': 'https://www.cidrap.umn.edu/news/rss.xml', 'category': 'Health'},
    ],
    'geopolitics': [
        {'name': 'Foreign Affairs', 'url': 'https://www.foreignaffairs.com/rss.xml', 'category': 'Geopolitics'},
        {'name': 'The Diplomat', 'url': 'https://thediplomat.com/feed/', 'category': 'Geopolitics'},
    ],
}

# All feeds flattened for iteration
ALL_FEEDS = []
for _cat_feeds in RSS_FEEDS.values():
    ALL_FEEDS.extend(_cat_feeds)

# Feed categories for UI filtering
FEED_CATEGORIES = sorted(set(f['category'] for f in ALL_FEEDS))


# ─── Helper: Parse RSS/Atom XML ────────────────────────────────────────
def _parse_feed(xml_text, feed_name, feed_category):
    """Parse RSS or Atom feed XML into a list of article dicts."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    ns = {'atom': 'http://www.w3.org/2005/Atom'}

    # RSS 2.0
    for item in root.findall('.//item'):
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        desc = (item.findtext('description') or '').strip()
        pub = (item.findtext('pubDate') or '').strip()
        if title:
            items.append({
                'title': title[:500],
                'link': link[:2000],
                'description': desc[:1000],
                'published': pub[:100],
                'source': feed_name,
                'category': feed_category,
            })

    # Atom
    if not items:
        for entry in root.findall('.//atom:entry', ns) or root.findall('.//entry'):
            title = ''
            link = ''
            desc = ''
            pub = ''
            t = entry.find('atom:title', ns) or entry.find('title')
            if t is not None:
                title = (t.text or '').strip()
            l = entry.find('atom:link', ns) or entry.find('link')
            if l is not None:
                link = l.get('href', '') or (l.text or '')
            s = entry.find('atom:summary', ns) or entry.find('summary') or entry.find('atom:content', ns) or entry.find('content')
            if s is not None:
                desc = (s.text or '').strip()
            p = entry.find('atom:updated', ns) or entry.find('updated') or entry.find('atom:published', ns) or entry.find('published')
            if p is not None:
                pub = (p.text or '').strip()
            if title:
                items.append({
                    'title': title[:500],
                    'link': link[:2000],
                    'description': desc[:1000],
                    'published': pub[:100],
                    'source': feed_name,
                    'category': feed_category,
                })

    return items[:50]  # Cap per feed


# ─── Background Fetch Worker ──────────────────────────────────────────

def _can_fetch(source_key):
    cooldown = FETCH_COOLDOWN.get(source_key, 300)
    last = _last_fetch.get(source_key)
    if last and (datetime.now() - last).total_seconds() < cooldown:
        return False
    return True


def _fetch_rss_feeds():
    """Fetch all RSS feeds and cache to DB."""
    if not _can_fetch('rss'):
        return
    _last_fetch['rss'] = datetime.now()

    articles = []
    for feed in ALL_FEEDS:
        try:
            resp = requests.get(feed['url'], timeout=10, headers={
                'User-Agent': 'NOMAD-SitRoom/1.0',
                'Accept': 'application/rss+xml, application/xml, text/xml',
            })
            if resp.ok:
                articles.extend(_parse_feed(resp.text, feed['name'], feed['category']))
        except Exception as e:
            log.debug(f"RSS fetch failed for {feed['name']}: {e}")

    if not articles:
        return

    with db_session() as db:
        db.execute('DELETE FROM sitroom_news WHERE source_type = ?', ('rss',))
        for a in articles:
            content_hash = hashlib.md5((a['title'] + a['link']).encode()).hexdigest()
            db.execute('''INSERT OR IGNORE INTO sitroom_news
                (content_hash, title, link, description, published, source_name, category, source_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (content_hash, a['title'], a['link'], a['description'],
                 a['published'], a['source'], a['category'], 'rss'))
        db.commit()
    log.info(f"Situation Room: cached {len(articles)} RSS articles")


def _fetch_earthquakes():
    """Fetch recent earthquakes from USGS."""
    if not _can_fetch('earthquakes'):
        return
    _last_fetch['earthquakes'] = datetime.now()

    try:
        resp = requests.get(
            'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson',
            timeout=15, headers={'User-Agent': 'NOMAD-SitRoom/1.0'}
        )
        if not resp.ok:
            return
        data = resp.json()
    except Exception as e:
        log.debug(f"Earthquake fetch failed: {e}")
        return

    features = data.get('features', [])[:100]
    with db_session() as db:
        db.execute("DELETE FROM sitroom_events WHERE event_type = 'earthquake'")
        for f in features:
            props = f.get('properties', {})
            geom = f.get('geometry', {})
            coords = geom.get('coordinates', [0, 0, 0])
            event_id = f.get('id', '')
            db.execute('''INSERT OR IGNORE INTO sitroom_events
                (event_id, event_type, title, magnitude, lat, lng, depth_km, event_time, source_url, detail_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (event_id, 'earthquake', props.get('place', ''),
                 props.get('mag'), coords[1] if len(coords) > 1 else 0,
                 coords[0] if coords else 0,
                 coords[2] if len(coords) > 2 else 0,
                 props.get('time', 0),
                 props.get('url', ''),
                 json.dumps({'tsunami': props.get('tsunami'), 'alert': props.get('alert'),
                             'felt': props.get('felt'), 'sig': props.get('sig')})))
        db.commit()
    log.info(f"Situation Room: cached {len(features)} earthquakes")


def _fetch_weather_alerts():
    """Fetch active US weather alerts from NWS."""
    if not _can_fetch('weather_alerts'):
        return
    _last_fetch['weather_alerts'] = datetime.now()

    try:
        resp = requests.get(
            'https://api.weather.gov/alerts/active?status=actual&severity=Extreme,Severe',
            timeout=15, headers={'User-Agent': 'NOMAD-SitRoom/1.0', 'Accept': 'application/geo+json'}
        )
        if not resp.ok:
            return
        data = resp.json()
    except Exception as e:
        log.debug(f"Weather alerts fetch failed: {e}")
        return

    features = data.get('features', [])[:200]
    with db_session() as db:
        db.execute("DELETE FROM sitroom_events WHERE event_type = 'weather_alert'")
        for f in features:
            props = f.get('properties', {})
            event_id = props.get('id', '')
            # NWS alerts may have polygon geometry or zone references
            geom = f.get('geometry')
            lat, lng = 0.0, 0.0
            if geom and geom.get('coordinates'):
                # Use centroid of first polygon
                try:
                    coords = geom['coordinates'][0] if geom['type'] == 'Polygon' else geom['coordinates'][0][0]
                    lat = sum(c[1] for c in coords) / len(coords)
                    lng = sum(c[0] for c in coords) / len(coords)
                except (IndexError, TypeError, ZeroDivisionError):
                    pass
            db.execute('''INSERT OR IGNORE INTO sitroom_events
                (event_id, event_type, title, lat, lng, event_time, source_url, detail_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (event_id, 'weather_alert',
                 f"{props.get('event', '')} - {props.get('areaDesc', '')}",
                 lat, lng,
                 int(datetime.fromisoformat(props.get('onset', '2000-01-01T00:00:00+00:00').replace('Z', '+00:00')).timestamp() * 1000) if props.get('onset') else 0,
                 props.get('id', ''),
                 json.dumps({
                     'severity': props.get('severity'),
                     'certainty': props.get('certainty'),
                     'urgency': props.get('urgency'),
                     'headline': props.get('headline', ''),
                     'description': (props.get('description', '') or '')[:2000],
                     'instruction': (props.get('instruction', '') or '')[:1000],
                     'sender': props.get('senderName', ''),
                     'expires': props.get('expires', ''),
                 })))
        db.commit()
    log.info(f"Situation Room: cached {len(features)} weather alerts")


def _fetch_market_data():
    """Fetch key market indices from free APIs."""
    if not _can_fetch('markets'):
        return
    _last_fetch['markets'] = datetime.now()

    markets = []

    # Crypto prices (CoinGecko free API — bitcoin, ethereum, solana)
    try:
        resp = requests.get(
            'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true',
            timeout=10, headers={'User-Agent': 'NOMAD-SitRoom/1.0'}
        )
        if resp.ok:
            data = resp.json()
            display_names = {'bitcoin': 'BTC', 'ethereum': 'ETH', 'solana': 'SOL'}
            for coin, vals in data.items():
                markets.append({
                    'symbol': display_names.get(coin, coin.upper()),
                    'price': vals.get('usd', 0),
                    'change_24h': vals.get('usd_24h_change') or 0,
                    'market_type': 'crypto',
                })
    except Exception as e:
        log.debug(f"CoinGecko fetch failed: {e}")

    # Gold & Oil via metals.dev free tier (no key needed for basic)
    try:
        resp = requests.get(
            'https://api.metals.dev/v1/latest?api_key=demo&currency=USD&unit=toz',
            timeout=10, headers={'User-Agent': 'NOMAD-SitRoom/1.0'}
        )
        if resp.ok:
            data = resp.json()
            metals = data.get('metals', {})
            if 'gold' in metals:
                markets.append({
                    'symbol': 'GOLD',
                    'price': metals['gold'],
                    'change_24h': 0,
                    'market_type': 'commodity',
                })
            if 'silver' in metals:
                markets.append({
                    'symbol': 'SILVER',
                    'price': metals['silver'],
                    'change_24h': 0,
                    'market_type': 'commodity',
                })
    except Exception as e:
        log.debug(f"Metals fetch failed: {e}")

    # WTI Crude Oil price
    try:
        resp = requests.get(
            'https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key=DEMO_KEY&frequency=daily&data[0]=value&facets[product][]=EPCBRENT&sort[0][column]=period&sort[0][direction]=desc&length=1',
            timeout=10, headers={'User-Agent': 'NOMAD-SitRoom/1.0'}
        )
        if resp.ok:
            data = resp.json()
            rows = data.get('response', {}).get('data', [])
            if rows:
                markets.append({
                    'symbol': 'OIL (BRENT)',
                    'price': float(rows[0].get('value', 0)),
                    'change_24h': 0,
                    'market_type': 'commodity',
                })
    except Exception as e:
        log.debug(f"EIA oil fetch failed: {e}")

    # Fear & Greed Index
    try:
        resp = requests.get(
            'https://api.alternative.me/fng/?limit=1',
            timeout=10, headers={'User-Agent': 'NOMAD-SitRoom/1.0'}
        )
        if resp.ok:
            fg = resp.json().get('data', [{}])[0]
            markets.append({
                'symbol': 'FEAR_GREED',
                'price': int(fg.get('value', 50)),
                'change_24h': 0,
                'market_type': 'sentiment',
                'label': fg.get('value_classification', 'Neutral'),
            })
    except Exception as e:
        log.debug(f"Fear/Greed fetch failed: {e}")

    if not markets:
        return

    with db_session() as db:
        db.execute('DELETE FROM sitroom_markets')
        for m in markets:
            db.execute('''INSERT INTO sitroom_markets
                (symbol, price, change_24h, market_type, label)
                VALUES (?, ?, ?, ?, ?)''',
                (m['symbol'], m['price'], m.get('change_24h', 0),
                 m.get('market_type', 'other'), m.get('label', '')))
        db.commit()
    log.info(f"Situation Room: cached {len(markets)} market entries")


def _fetch_conflict_data():
    """Fetch recent conflict/crisis data from ACLED or GDACS."""
    if not _can_fetch('conflicts'):
        return
    _last_fetch['conflicts'] = datetime.now()

    # GDACS events (earthquakes, floods, cyclones, volcanoes — already partially covered)
    try:
        resp = requests.get(
            'https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?alertlevel=Orange;Red&eventlist=EQ;TC;FL;VO;DR&from=2024-01-01',
            timeout=15, headers={'User-Agent': 'NOMAD-SitRoom/1.0', 'Accept': 'application/json'}
        )
        if resp.ok:
            data = resp.json()
            features = data.get('features', [])[:50]
            with db_session() as db:
                db.execute("DELETE FROM sitroom_events WHERE event_type = 'conflict'")
                for f in features:
                    props = f.get('properties', {})
                    geom = f.get('geometry', {})
                    coords = geom.get('coordinates', [0, 0])
                    eid = props.get('eventid', str(hash(json.dumps(props)))[:12])
                    db.execute('''INSERT OR IGNORE INTO sitroom_events
                        (event_id, event_type, title, magnitude, lat, lng, event_time, source_url, detail_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (str(eid), 'conflict',
                         props.get('name', props.get('eventtype', 'Unknown event')),
                         props.get('severity', {}).get('severity_value') if isinstance(props.get('severity'), dict) else None,
                         coords[1] if len(coords) > 1 else 0,
                         coords[0] if coords else 0,
                         0,
                         props.get('url', {}).get('report', '') if isinstance(props.get('url'), dict) else '',
                         json.dumps({
                             'alert_level': props.get('alertlevel', ''),
                             'event_type': props.get('eventtype', ''),
                             'country': props.get('country', ''),
                             'description': (props.get('description', '') or '')[:2000],
                         })))
                db.commit()
            log.info(f"Situation Room: cached {len(features)} GDACS events")
    except Exception as e:
        log.debug(f"GDACS fetch failed: {e}")


def refresh_all_feeds():
    """Fetch all external data sources in a background thread."""
    global _fetch_running
    with _fetch_lock:
        if _fetch_running:
            return False
        _fetch_running = True

    def _worker():
        global _fetch_running
        try:
            _fetch_rss_feeds()
            _fetch_earthquakes()
            _fetch_weather_alerts()
            _fetch_market_data()
            _fetch_conflict_data()
        except Exception as e:
            log.exception(f"Situation Room refresh error: {e}")
        finally:
            with _fetch_lock:
                _fetch_running = False

    threading.Thread(target=_worker, daemon=True).start()
    return True


# ─── API Routes ────────────────────────────────────────────────────────

@situation_room_bp.route('/api/sitroom/refresh', methods=['POST'])
def api_sitroom_refresh():
    """Trigger a background refresh of all external feeds."""
    started = refresh_all_feeds()
    return jsonify({'started': started, 'message': 'Refresh started' if started else 'Already refreshing'})


@situation_room_bp.route('/api/sitroom/status')
def api_sitroom_status():
    """Return fetch status and last update times."""
    with _fetch_lock:
        running = _fetch_running
    return jsonify({
        'refreshing': running,
        'last_fetch': {k: v.isoformat() if v else None for k, v in _last_fetch.items()},
        'feed_categories': FEED_CATEGORIES,
        'feed_count': len(ALL_FEEDS),
    })


@situation_room_bp.route('/api/sitroom/news')
def api_sitroom_news():
    """Return cached news articles with optional category filter."""
    category = request.args.get('category', '')
    limit = min(request.args.get('limit', 100, type=int), 500)
    offset = request.args.get('offset', 0, type=int)

    with db_session() as db:
        if category:
            rows = db.execute(
                'SELECT * FROM sitroom_news WHERE category = ? ORDER BY cached_at DESC LIMIT ? OFFSET ?',
                (category, limit, offset)).fetchall()
        else:
            rows = db.execute(
                'SELECT * FROM sitroom_news ORDER BY cached_at DESC LIMIT ? OFFSET ?',
                (limit, offset)).fetchall()
        total = db.execute('SELECT COUNT(*) FROM sitroom_news').fetchone()[0]
    return jsonify({'articles': [dict(r) for r in rows], 'total': total})


@situation_room_bp.route('/api/sitroom/events')
def api_sitroom_events():
    """Return cached geospatial events (earthquakes, weather, conflicts)."""
    event_type = request.args.get('type', '')
    limit = min(request.args.get('limit', 200, type=int), 500)

    with db_session() as db:
        if event_type:
            rows = db.execute(
                'SELECT * FROM sitroom_events WHERE event_type = ? ORDER BY cached_at DESC LIMIT ?',
                (event_type, limit)).fetchall()
        else:
            rows = db.execute(
                'SELECT * FROM sitroom_events ORDER BY cached_at DESC LIMIT ?',
                (limit,)).fetchall()
    return jsonify({'events': [dict(r) for r in rows]})


@situation_room_bp.route('/api/sitroom/earthquakes')
def api_sitroom_earthquakes():
    """Return cached earthquake data."""
    min_mag = request.args.get('min_magnitude', 0, type=float)
    with db_session() as db:
        rows = db.execute(
            "SELECT * FROM sitroom_events WHERE event_type = 'earthquake' AND (magnitude IS NULL OR magnitude >= ?) ORDER BY event_time DESC LIMIT 100",
            (min_mag,)).fetchall()
    return jsonify({'earthquakes': [dict(r) for r in rows]})


@situation_room_bp.route('/api/sitroom/weather-alerts')
def api_sitroom_weather_alerts():
    """Return cached severe weather alerts."""
    with db_session() as db:
        rows = db.execute(
            "SELECT * FROM sitroom_events WHERE event_type = 'weather_alert' ORDER BY cached_at DESC LIMIT 100"
        ).fetchall()
    return jsonify({'alerts': [dict(r) for r in rows]})


@situation_room_bp.route('/api/sitroom/markets')
def api_sitroom_markets():
    """Return cached market data."""
    with db_session() as db:
        rows = db.execute('SELECT * FROM sitroom_markets ORDER BY market_type, symbol').fetchall()
    return jsonify({'markets': [dict(r) for r in rows]})


@situation_room_bp.route('/api/sitroom/summary')
def api_sitroom_summary():
    """Return a high-level summary for the Situation Room dashboard."""
    with db_session() as db:
        news_count = db.execute('SELECT COUNT(*) FROM sitroom_news').fetchone()[0]
        quake_count = db.execute("SELECT COUNT(*) FROM sitroom_events WHERE event_type = 'earthquake'").fetchone()[0]
        weather_count = db.execute("SELECT COUNT(*) FROM sitroom_events WHERE event_type = 'weather_alert'").fetchone()[0]
        conflict_count = db.execute("SELECT COUNT(*) FROM sitroom_events WHERE event_type = 'conflict'").fetchone()[0]
        market_count = db.execute('SELECT COUNT(*) FROM sitroom_markets').fetchone()[0]

        # Top 5 significant earthquakes
        top_quakes = db.execute(
            "SELECT title, magnitude, lat, lng FROM sitroom_events WHERE event_type = 'earthquake' AND magnitude IS NOT NULL ORDER BY magnitude DESC LIMIT 5"
        ).fetchall()

        # Latest headline per category
        cats = db.execute(
            'SELECT DISTINCT category FROM sitroom_news ORDER BY category'
        ).fetchall()
        latest_by_cat = {}
        for c in cats:
            row = db.execute(
                'SELECT title, source_name, cached_at FROM sitroom_news WHERE category = ? ORDER BY cached_at DESC LIMIT 1',
                (c['category'],)).fetchone()
            if row:
                latest_by_cat[c['category']] = dict(row)

        # Market snapshot
        market_rows = db.execute('SELECT * FROM sitroom_markets ORDER BY market_type').fetchall()

        # Custom feeds
        custom_count = db.execute('SELECT COUNT(*) FROM sitroom_custom_feeds').fetchone()[0]

    return jsonify({
        'news_count': news_count,
        'earthquake_count': quake_count,
        'weather_alert_count': weather_count,
        'conflict_count': conflict_count,
        'market_count': market_count,
        'custom_feed_count': custom_count,
        'top_earthquakes': [dict(r) for r in top_quakes],
        'latest_by_category': latest_by_cat,
        'markets': [dict(r) for r in market_rows],
        'refreshing': _fetch_running,
        'last_fetch': {k: v.isoformat() if v else None for k, v in _last_fetch.items()},
    })


# ─── Custom Feed Management ───────────────────────────────────────────

@situation_room_bp.route('/api/sitroom/feeds')
def api_sitroom_feeds():
    """Return list of all feeds (built-in + custom)."""
    with db_session() as db:
        custom = db.execute('SELECT * FROM sitroom_custom_feeds ORDER BY category, name').fetchall()
    return jsonify({
        'builtin': [{'name': f['name'], 'url': f['url'], 'category': f['category']} for f in ALL_FEEDS],
        'custom': [dict(r) for r in custom],
        'categories': FEED_CATEGORIES,
    })


@situation_room_bp.route('/api/sitroom/feeds', methods=['POST'])
def api_sitroom_add_feed():
    """Add a custom RSS feed."""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()[:200]
    url = (data.get('url') or '').strip()[:2000]
    category = (data.get('category') or 'Custom').strip()[:100]
    if not name or not url:
        return jsonify({'error': 'Name and URL required'}), 400

    with db_session() as db:
        cur = db.execute(
            'INSERT INTO sitroom_custom_feeds (name, url, category) VALUES (?, ?, ?)',
            (name, url, category))
        db.commit()
        row = db.execute('SELECT * FROM sitroom_custom_feeds WHERE id = ?', (cur.lastrowid,)).fetchone()
    log_activity('Custom feed added', 'situation_room', name)
    return jsonify(dict(row)), 201


@situation_room_bp.route('/api/sitroom/feeds/<int:feed_id>', methods=['DELETE'])
def api_sitroom_delete_feed(feed_id):
    """Delete a custom RSS feed."""
    with db_session() as db:
        db.execute('DELETE FROM sitroom_custom_feeds WHERE id = ?', (feed_id,))
        db.commit()
    return jsonify({'deleted': True})


# ─── AI Briefing ───────────────────────────────────────────────────────

@situation_room_bp.route('/api/sitroom/ai-briefing', methods=['POST'])
def api_sitroom_ai_briefing():
    """Generate an AI-powered intelligence briefing from cached data."""
    try:
        from services import ollama
    except ImportError:
        return jsonify({'error': 'AI service not available'}), 503

    with db_session() as db:
        # Gather recent data for context
        news = db.execute('SELECT title, category, source_name FROM sitroom_news ORDER BY cached_at DESC LIMIT 30').fetchall()
        quakes = db.execute("SELECT title, magnitude FROM sitroom_events WHERE event_type = 'earthquake' AND magnitude >= 4.0 ORDER BY magnitude DESC LIMIT 10").fetchall()
        weather = db.execute("SELECT title FROM sitroom_events WHERE event_type = 'weather_alert' ORDER BY cached_at DESC LIMIT 10").fetchall()
        markets = db.execute('SELECT symbol, price, change_24h, market_type FROM sitroom_markets').fetchall()

    # Build context
    context_parts = ['You are a concise intelligence analyst. Generate a brief situation report based on the following real-time data.\n']

    if news:
        context_parts.append('--- TOP HEADLINES ---')
        for n in news:
            context_parts.append(f"[{n['category']}] {n['title']} ({n['source_name']})")

    if quakes:
        context_parts.append('\n--- SEISMIC ACTIVITY ---')
        for q in quakes:
            context_parts.append(f"M{q['magnitude']} - {q['title']}")

    if weather:
        context_parts.append('\n--- SEVERE WEATHER ---')
        for w in weather:
            context_parts.append(f"- {w['title']}")

    if markets:
        context_parts.append('\n--- MARKETS ---')
        for m in markets:
            direction = '+' if m['change_24h'] >= 0 else ''
            context_parts.append(f"{m['symbol']}: ${m['price']:,.2f} ({direction}{m['change_24h']:.1f}%)")

    context_parts.append('\nProvide a concise 3-5 paragraph intelligence briefing covering: (1) Key global developments, (2) Natural hazards/weather, (3) Market sentiment. Use professional military-style briefing format. Start with "SITUATION REPORT" header and current date/time.')

    prompt = '\n'.join(context_parts)

    try:
        result = ollama.chat(prompt, model=None, stream=False)
        if isinstance(result, dict):
            briefing = result.get('message', {}).get('content', '') or result.get('response', '')
        else:
            briefing = str(result)
    except Exception as e:
        return jsonify({'error': f'AI briefing failed: {str(e)}'}), 503

    # Cache the briefing
    with db_session() as db:
        db.execute('INSERT INTO sitroom_briefings (content, generated_at) VALUES (?, CURRENT_TIMESTAMP)', (briefing,))
        db.commit()

    return jsonify({'briefing': briefing})


@situation_room_bp.route('/api/sitroom/briefings')
def api_sitroom_briefings():
    """Return past AI briefings."""
    limit = min(request.args.get('limit', 10, type=int), 50)
    with db_session() as db:
        rows = db.execute('SELECT * FROM sitroom_briefings ORDER BY generated_at DESC LIMIT ?', (limit,)).fetchall()
    return jsonify({'briefings': [dict(r) for r in rows]})
