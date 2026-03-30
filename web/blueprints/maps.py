"""Maps, waypoints, geocoding, atlas, and offline map management routes."""

import json
import os
import sys
import time
import math
import threading
import subprocess
import shutil
import logging
from html import escape as esc

from flask import Blueprint, request, jsonify, Response
from werkzeug.utils import secure_filename

from db import get_db, log_activity
from services.manager import format_size, get_services_dir
from config import get_data_dir
from web.print_templates import render_print_document
from web.state import _map_downloads
import web.state as _state

log = logging.getLogger('nomad.web')

_CREATION_FLAGS = {'creationflags': 0x08000000} if sys.platform == 'win32' else {}

_state_lock = threading.Lock()

maps_bp = Blueprint('maps', __name__)


def _validate_download_url(url):
    import ipaddress
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ('https', 'http'):
        raise ValueError(f'Unsupported URL scheme: {parsed.scheme}')
    hostname = parsed.hostname or ''
    if hostname in ('localhost', '') or hostname.endswith('.local'):
        raise ValueError('URLs pointing to internal hosts are not allowed')
    try:
        import socket
        resolved = socket.getaddrinfo(hostname, None)
        for _family, _type, _proto, _canonname, sockaddr in resolved:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError(f'URL resolves to a private/internal IP: {ip}')
    except (socket.gaierror, OSError):
        raise ValueError(f'Cannot resolve hostname: {hostname}')
    return url


# ─── Maps API ──────────────────────────────────────────────────────

MAPS_DIR_NAME = 'maps'

def get_maps_dir():
    path = os.path.join(get_data_dir(), MAPS_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path

MAP_REGIONS = [
    # US Regions — bbox = [west, south, east, north]
    {'id': 'us-pacific', 'name': 'US Pacific', 'states': 'AK, CA, HI, OR, WA', 'bbox': [-180, 18, -100, 72]},
    {'id': 'us-mountain', 'name': 'US Mountain', 'states': 'AZ, CO, ID, MT, NV, NM, UT, WY', 'bbox': [-117, 31, -102, 49]},
    {'id': 'us-west-north-central', 'name': 'US West North Central', 'states': 'IA, KS, MN, MO, NE, ND, SD', 'bbox': [-104.1, 36, -89.1, 49]},
    {'id': 'us-east-north-central', 'name': 'US East North Central', 'states': 'IL, IN, MI, OH, WI', 'bbox': [-91.5, 36.9, -80.5, 48.3]},
    {'id': 'us-west-south-central', 'name': 'US West South Central', 'states': 'AR, LA, OK, TX', 'bbox': [-106.7, 25.8, -88.8, 37]},
    {'id': 'us-east-south-central', 'name': 'US East South Central', 'states': 'AL, KY, MS, TN', 'bbox': [-91.7, 30, -81.9, 39.2]},
    {'id': 'us-south-atlantic', 'name': 'US South Atlantic', 'states': 'DE, FL, GA, MD, NC, SC, VA, DC, WV', 'bbox': [-84.4, 24.4, -75, 39.8]},
    {'id': 'us-middle-atlantic', 'name': 'US Middle Atlantic', 'states': 'NJ, NY, PA', 'bbox': [-80.6, 38.8, -71.8, 45.1]},
    {'id': 'us-new-england', 'name': 'US New England', 'states': 'CT, ME, MA, NH, RI, VT', 'bbox': [-73.8, 40.9, -66.9, 47.5]},
    # International Regions
    {'id': 'eu-western', 'name': 'Western Europe', 'states': 'UK, France, Germany, Netherlands, Belgium', 'bbox': [-11, 42, 15, 61]},
    {'id': 'eu-eastern', 'name': 'Eastern Europe', 'states': 'Poland, Czech, Romania, Hungary, Ukraine', 'bbox': [14, 43, 41, 55]},
    {'id': 'eu-southern', 'name': 'Southern Europe', 'states': 'Spain, Italy, Portugal, Greece, Turkey', 'bbox': [-10, 34, 45, 48]},
    {'id': 'eu-northern', 'name': 'Northern Europe', 'states': 'Sweden, Norway, Finland, Denmark, Iceland', 'bbox': [-25, 54, 32, 72]},
    {'id': 'canada', 'name': 'Canada', 'states': 'All provinces and territories', 'bbox': [-141, 41.7, -52, 84]},
    {'id': 'mexico-central', 'name': 'Mexico & Central America', 'states': 'Mexico, Guatemala, Belize, Honduras', 'bbox': [-118, 13, -82, 33]},
    {'id': 'south-america', 'name': 'South America', 'states': 'Brazil, Argentina, Colombia, Chile, Peru', 'bbox': [-82, -56, -34, 13]},
    {'id': 'east-asia', 'name': 'East Asia', 'states': 'Japan, South Korea, Taiwan', 'bbox': [120, 20, 154, 46]},
    {'id': 'southeast-asia', 'name': 'Southeast Asia', 'states': 'Philippines, Thailand, Vietnam, Indonesia', 'bbox': [92, -11, 141, 29]},
    {'id': 'oceania', 'name': 'Australia & New Zealand', 'states': 'Australia, New Zealand, Pacific Islands', 'bbox': [110, -48, 180, -9]},
    {'id': 'middle-east', 'name': 'Middle East', 'states': 'Israel, Jordan, UAE, Saudi Arabia, Iraq', 'bbox': [25, 12, 60, 42]},
    {'id': 'africa-north', 'name': 'North Africa', 'states': 'Egypt, Morocco, Tunisia, Libya, Algeria', 'bbox': [-18, 15, 37, 38]},
    {'id': 'africa-sub', 'name': 'Sub-Saharan Africa', 'states': 'South Africa, Kenya, Nigeria, Ethiopia', 'bbox': [-18, -35, 52, 15]},
]

# ─── Alternative Map Sources ─────────────────────────────────────
# Sources that can be downloaded for offline map usage
MAP_SOURCES = [
    # === PMTiles (native format — works directly with MapLibre viewer) ===
    {'id': 'protomaps-planet', 'name': 'Protomaps World Basemap', 'category': 'PMTiles',
     'url': 'https://data.source.coop/protomaps/openstreetmap/v4.pmtiles', 'format': 'pmtiles', 'est_size': '~120 GB',
     'desc': 'Full planet vector tiles (v4). Source Cooperative mirror. The definitive offline map source.', 'direct': True},
    {'id': 'openfreemap-planet', 'name': 'OpenFreeMap Planet', 'category': 'PMTiles',
     'url': 'https://openfreemap.com/', 'format': 'pmtiles', 'est_size': '~80 GB',
     'desc': 'Free, open-source planet tiles. Self-hostable.'},
    {'id': 'overture-maps', 'name': 'Overture Maps', 'category': 'PMTiles',
     'url': 'https://overturemaps.org/download/', 'format': 'pmtiles', 'est_size': 'Varies',
     'desc': 'Open map data from Meta, Microsoft, AWS, TomTom. Buildings, places, roads.'},
    {'id': 'source-coop', 'name': 'Source Cooperative Maps', 'category': 'PMTiles',
     'url': 'https://source.coop/', 'format': 'pmtiles', 'est_size': 'Varies',
     'desc': 'Community-hosted geospatial datasets in PMTiles and other formats.'},
    {'id': 'mapterhorn-terrain', 'name': 'Mapterhorn Terrain Tiles', 'category': 'PMTiles',
     'url': 'https://download.mapterhorn.com/planet.pmtiles', 'format': 'pmtiles', 'est_size': '~30 GB',
     'desc': 'Global terrain/elevation tiles in PMTiles format.', 'direct': True},

    # === OSM Extracts (PBF — need conversion to PMTiles via tilemaker or planetiler) ===
    {'id': 'geofabrik-na', 'name': 'Geofabrik: North America', 'category': 'OSM Extracts',
     'url': 'https://download.geofabrik.de/north-america-latest.osm.pbf', 'format': 'pbf', 'est_size': '~13 GB',
     'desc': 'Full North America OSM data. Requires conversion to PMTiles.', 'direct': True},
    {'id': 'geofabrik-us', 'name': 'Geofabrik: United States', 'category': 'OSM Extracts',
     'url': 'https://download.geofabrik.de/north-america/us-latest.osm.pbf', 'format': 'pbf', 'est_size': '~9 GB',
     'desc': 'Complete US OSM data. Updated daily.', 'direct': True},
    {'id': 'geofabrik-europe', 'name': 'Geofabrik: Europe', 'category': 'OSM Extracts',
     'url': 'https://download.geofabrik.de/europe-latest.osm.pbf', 'format': 'pbf', 'est_size': '~28 GB',
     'desc': 'Full Europe OSM data. Very detailed.', 'direct': True},
    {'id': 'geofabrik-asia', 'name': 'Geofabrik: Asia', 'category': 'OSM Extracts',
     'url': 'https://download.geofabrik.de/asia-latest.osm.pbf', 'format': 'pbf', 'est_size': '~12 GB',
     'desc': 'Full Asia OSM data.', 'direct': True},
    {'id': 'geofabrik-africa', 'name': 'Geofabrik: Africa', 'category': 'OSM Extracts',
     'url': 'https://download.geofabrik.de/africa-latest.osm.pbf', 'format': 'pbf', 'est_size': '~6 GB',
     'desc': 'Full Africa OSM data.', 'direct': True},
    {'id': 'geofabrik-sa', 'name': 'Geofabrik: South America', 'category': 'OSM Extracts',
     'url': 'https://download.geofabrik.de/south-america-latest.osm.pbf', 'format': 'pbf', 'est_size': '~3 GB',
     'desc': 'Full South America OSM data.', 'direct': True},
    {'id': 'geofabrik-oceania', 'name': 'Geofabrik: Australia & Oceania', 'category': 'OSM Extracts',
     'url': 'https://download.geofabrik.de/australia-oceania-latest.osm.pbf', 'format': 'pbf', 'est_size': '~1 GB',
     'desc': 'Australia, NZ, Pacific Islands OSM data.', 'direct': True},
    {'id': 'geofabrik-ca', 'name': 'Geofabrik: Central America', 'category': 'OSM Extracts',
     'url': 'https://download.geofabrik.de/central-america-latest.osm.pbf', 'format': 'pbf', 'est_size': '~600 MB',
     'desc': 'Central America and Caribbean OSM data.', 'direct': True},
    {'id': 'geofabrik-russia', 'name': 'Geofabrik: Russia', 'category': 'OSM Extracts',
     'url': 'https://download.geofabrik.de/russia-latest.osm.pbf', 'format': 'pbf', 'est_size': '~3 GB',
     'desc': 'Full Russia OSM data.', 'direct': True},
    {'id': 'geofabrik-canada', 'name': 'Geofabrik: Canada', 'category': 'OSM Extracts',
     'url': 'https://download.geofabrik.de/north-america/canada-latest.osm.pbf', 'format': 'pbf', 'est_size': '~3 GB',
     'desc': 'Complete Canada OSM data.', 'direct': True},
    {'id': 'geofabrik-planet', 'name': 'Geofabrik: Full Planet', 'category': 'OSM Extracts',
     'url': 'https://planet.openstreetmap.org/pbf/planet-latest.osm.pbf', 'format': 'pbf', 'est_size': '~70 GB',
     'desc': 'Complete OpenStreetMap planet data. Official source.', 'direct': True},

    # === Geofabrik US States ===
    {'id': 'geofabrik-us-california', 'name': 'Geofabrik: California', 'category': 'US States (OSM)',
     'url': 'https://download.geofabrik.de/north-america/us/california-latest.osm.pbf', 'format': 'pbf', 'est_size': '~1 GB',
     'desc': 'California OSM data.', 'direct': True},
    {'id': 'geofabrik-us-texas', 'name': 'Geofabrik: Texas', 'category': 'US States (OSM)',
     'url': 'https://download.geofabrik.de/north-america/us/texas-latest.osm.pbf', 'format': 'pbf', 'est_size': '~700 MB',
     'desc': 'Texas OSM data.', 'direct': True},
    {'id': 'geofabrik-us-florida', 'name': 'Geofabrik: Florida', 'category': 'US States (OSM)',
     'url': 'https://download.geofabrik.de/north-america/us/florida-latest.osm.pbf', 'format': 'pbf', 'est_size': '~400 MB',
     'desc': 'Florida OSM data.', 'direct': True},
    {'id': 'geofabrik-us-newyork', 'name': 'Geofabrik: New York', 'category': 'US States (OSM)',
     'url': 'https://download.geofabrik.de/north-america/us/new-york-latest.osm.pbf', 'format': 'pbf', 'est_size': '~400 MB',
     'desc': 'New York OSM data.', 'direct': True},
    {'id': 'geofabrik-us-pennsylvania', 'name': 'Geofabrik: Pennsylvania', 'category': 'US States (OSM)',
     'url': 'https://download.geofabrik.de/north-america/us/pennsylvania-latest.osm.pbf', 'format': 'pbf', 'est_size': '~350 MB',
     'desc': 'Pennsylvania OSM data.', 'direct': True},

    # === Topographic / Elevation Data ===
    {'id': 'usgs-national-map', 'name': 'USGS National Map', 'category': 'Topographic',
     'url': 'https://apps.nationalmap.gov/downloader/', 'format': 'various',
     'est_size': 'Varies', 'desc': 'US topographic maps, elevation, hydrography, boundaries.'},
    {'id': 'opentopo', 'name': 'OpenTopography', 'category': 'Topographic',
     'url': 'https://opentopography.org/', 'format': 'various',
     'est_size': 'Varies', 'desc': 'High-res topography data. LiDAR, DEMs, point clouds.'},
    {'id': 'viewfinderpanoramas', 'name': 'Viewfinder Panoramas DEMs', 'category': 'Topographic',
     'url': 'http://viewfinderpanoramas.org/dem3.html', 'format': 'hgt',
     'est_size': 'Varies', 'desc': '3 arc-second DEMs for the entire world. Great for terrain.'},
    {'id': 'srtm', 'name': 'SRTM Elevation (NASA)', 'category': 'Topographic',
     'url': 'https://dwtkns.com/srtm30m/', 'format': 'hgt',
     'est_size': 'Varies', 'desc': '30m resolution elevation data. Free with EarthData login.'},

    # === Natural Earth (small, low-detail reference maps) ===
    {'id': 'natural-earth-110m', 'name': 'Natural Earth 1:110m', 'category': 'Reference Maps',
     'url': 'https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip', 'format': 'shp', 'est_size': '~800 KB',
     'desc': 'World country boundaries. Very small, great for overview maps.', 'direct': True},
    {'id': 'natural-earth-50m', 'name': 'Natural Earth 1:50m', 'category': 'Reference Maps',
     'url': 'https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip', 'format': 'shp', 'est_size': '~5 MB',
     'desc': 'Medium-detail world boundaries and features.', 'direct': True},
    {'id': 'natural-earth-10m', 'name': 'Natural Earth 1:10m (Full)', 'category': 'Reference Maps',
     'url': 'https://naciscdn.org/naturalearth/packages/natural_earth_vector.gpkg.zip', 'format': 'gpkg', 'est_size': '~240 MB',
     'desc': 'Highest detail Natural Earth data in single GeoPackage.', 'direct': True},

    # === Humanitarian / Emergency Maps ===
    {'id': 'hot-export', 'name': 'HOT Export Tool', 'category': 'Humanitarian',
     'url': 'https://export.hotosm.org/', 'format': 'various',
     'est_size': 'Varies', 'desc': 'Humanitarian OpenStreetMap Team. Custom area exports for disaster response.'},
    {'id': 'hdx', 'name': 'Humanitarian Data Exchange', 'category': 'Humanitarian',
     'url': 'https://data.humdata.org/', 'format': 'various',
     'est_size': 'Varies', 'desc': 'UN OCHA humanitarian datasets. Population, infrastructure, health facilities.'},
    {'id': 'fieldpapers', 'name': 'Field Papers', 'category': 'Humanitarian',
     'url': 'http://fieldpapers.org/', 'format': 'pdf',
     'est_size': 'Varies', 'desc': 'Printable map atlases for field surveys. Works completely offline.'},

    # === BBBike City Extracts ===
    {'id': 'bbbike', 'name': 'BBBike Extracts (200+ Cities)', 'category': 'City Extracts',
     'url': 'https://extract.bbbike.org/', 'format': 'various',
     'est_size': 'Varies', 'desc': 'Custom city/area extracts in PBF, GeoJSON, Shapefile, etc.'},
    {'id': 'bbbike-download', 'name': 'BBBike Pre-built Cities', 'category': 'City Extracts',
     'url': 'https://download.bbbike.org/osm/bbbike/', 'format': 'pbf',
     'est_size': 'Varies', 'desc': 'Pre-built extracts for 200+ world cities. Updated weekly.'},

    # === Nautical / Aviation ===
    {'id': 'noaa-charts', 'name': 'NOAA Nautical Charts', 'category': 'Specialty',
     'url': 'https://charts.noaa.gov/ChartCatalog/MapSelect.html', 'format': 'pdf/bsb',
     'est_size': 'Varies', 'desc': 'US coastal and inland waterway navigation charts.'},
    {'id': 'faa-sectionals', 'name': 'FAA Sectional Charts', 'category': 'Specialty',
     'url': 'https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/vfr/', 'format': 'pdf/tiff',
     'est_size': 'Varies', 'desc': 'US VFR sectional aeronautical charts.'},

    # === Weather / Climate ===
    {'id': 'worldclim', 'name': 'WorldClim Climate Data', 'category': 'Climate',
     'url': 'https://www.worldclim.org/data/worldclim21.html', 'format': 'tiff',
     'est_size': 'Varies', 'desc': 'Global climate data: temperature, precipitation, bioclimatic variables.'},

    # === Satellite Imagery ===
    {'id': 'sentinel2', 'name': 'Sentinel-2 Satellite (ESA)', 'category': 'Satellite',
     'url': 'https://browser.dataspace.copernicus.eu/', 'format': 'jp2/tiff',
     'est_size': 'Varies', 'desc': 'Free 10m resolution satellite imagery. Updated every 5 days.'},
    {'id': 'landsat', 'name': 'Landsat (USGS)', 'category': 'Satellite',
     'url': 'https://earthexplorer.usgs.gov/', 'format': 'tiff',
     'est_size': 'Varies', 'desc': 'Free 30m satellite imagery with 50+ year archive.'},
]

@maps_bp.route('/api/maps/regions')
def api_maps_regions():
    maps_dir = get_maps_dir()
    result = []
    for r in MAP_REGIONS:
        pmtiles = os.path.join(maps_dir, f'{r["id"]}.pmtiles')
        result.append({
            **r,
            'downloaded': os.path.isfile(pmtiles),
            'size': format_size(os.path.getsize(pmtiles)) if os.path.isfile(pmtiles) else None,
        })
    return jsonify(result)

@maps_bp.route('/api/maps/files')
def api_maps_files():
    maps_dir = get_maps_dir()
    MAP_EXTENSIONS = ('.pmtiles', '.pbf', '.osm', '.geojson', '.gpkg', '.mbtiles', '.shp', '.tiff', '.hgt')
    files = []
    for f in os.listdir(maps_dir):
        if any(f.endswith(ext) for ext in MAP_EXTENSIONS):
            fp = os.path.join(maps_dir, f)
            files.append({'filename': f, 'size': format_size(os.path.getsize(fp))})
    return jsonify(files)

@maps_bp.route('/api/maps/delete', methods=['POST'])
def api_maps_delete():
    data = request.get_json() or {}
    filename = data.get('filename')
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    maps_dir = get_maps_dir()
    path = os.path.normpath(os.path.join(maps_dir, filename))
    if not path.startswith(os.path.normpath(maps_dir) + os.sep):
        return jsonify({'error': 'Invalid filename'}), 400
    try:
        if os.path.isfile(path):
            os.remove(path)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@maps_bp.route('/api/maps/tiles/<path:filepath>')
def api_maps_serve_tile(filepath):
    """Serve local PMTiles files."""
    maps_dir = get_maps_dir()
    safe_path = os.path.normpath(os.path.join(maps_dir, filepath))
    if not os.path.normcase(safe_path).startswith(os.path.normcase(os.path.normpath(maps_dir))):
        return jsonify({'error': 'Forbidden'}), 403
    if not os.path.isfile(safe_path):
        return jsonify({'error': 'Not found'}), 404

    # Support range requests for PMTiles
    range_header = request.headers.get('Range')
    file_size = os.path.getsize(safe_path)

    if range_header:
        try:
            byte_range = range_header.replace('bytes=', '').split('-')
            start = int(byte_range[0])
            end = int(byte_range[1]) if byte_range[1] else file_size - 1
        except (ValueError, IndexError):
            return jsonify({'error': 'Invalid Range header'}), 416
        length = end - start + 1

        with open(safe_path, 'rb') as f:
            f.seek(start)
            data = f.read(length)

        resp = Response(data, 206, mimetype='application/octet-stream')
        resp.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        resp.headers['Accept-Ranges'] = 'bytes'
        resp.headers['Content-Length'] = length
        return resp

    def stream_file():
        with open(safe_path, 'rb') as f:
            while True:
                chunk = f.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                yield chunk
    resp = Response(stream_file(), mimetype='application/octet-stream')
    resp.headers['Content-Length'] = file_size
    resp.headers['Accept-Ranges'] = 'bytes'
    return resp

@maps_bp.route('/api/maps/sources')
def api_maps_sources():
    return jsonify(MAP_SOURCES)

@maps_bp.route('/api/maps/download-progress')
def api_maps_download_progress():
    with _state_lock:
        snapshot = dict(_map_downloads)
    return jsonify(snapshot)

def _get_pmtiles_cli():
    """Get path to pmtiles CLI, auto-downloading if needed."""
    from platform_utils import exe_name, IS_WINDOWS, IS_MACOS
    services_dir = get_services_dir()
    pmtiles_dir = os.path.join(services_dir, 'pmtiles')
    os.makedirs(pmtiles_dir, exist_ok=True)
    exe = os.path.join(pmtiles_dir, exe_name('pmtiles'))
    if os.path.isfile(exe):
        return exe
    # Download from GitHub releases
    import urllib.request, zipfile, io, json as _json
    api_url = 'https://api.github.com/repos/protomaps/go-pmtiles/releases/latest'
    log.info('Resolving pmtiles CLI release from %s', api_url)
    req = urllib.request.Request(api_url, headers={'User-Agent': 'NOMADFieldDesk/1.0.0', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        release = _json.loads(resp.read())
    url = None
    if IS_WINDOWS:
        plat_key, arch_key = 'Windows', 'x86_64'
    elif IS_MACOS:
        import platform as _plat
        arch = 'arm64' if _plat.machine() == 'arm64' else 'x86_64'
        plat_key, arch_key = 'Darwin', arch
    else:
        import platform as _plat
        arch = 'arm64' if _plat.machine() == 'aarch64' else 'x86_64'
        plat_key, arch_key = 'Linux', arch
    for asset in release.get('assets', []):
        if plat_key in asset['name'] and arch_key in asset['name']:
            url = asset['browser_download_url']
            break
    if not url:
        log.error('No %s %s asset found in go-pmtiles release', plat_key, arch_key)
        return None
    log.info('Downloading pmtiles CLI from %s', url)
    req = urllib.request.Request(url, headers={'User-Agent': 'NOMADFieldDesk/1.0.0'})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    binary_name = exe_name('pmtiles') if IS_WINDOWS else 'pmtiles'
    if url.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.endswith(binary_name):
                    extracted = zf.extract(name, pmtiles_dir)
                    if extracted != exe:
                        shutil.move(extracted, exe)
                    break
    elif url.endswith('.tar.gz') or url.endswith('.tgz'):
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tf:
            for name in tf.getnames():
                if name.endswith(binary_name):
                    # Path traversal protection
                    target = os.path.normpath(os.path.join(pmtiles_dir, name))
                    if not target.startswith(os.path.normpath(pmtiles_dir)):
                        continue
                    tf.extract(name, pmtiles_dir)
                    extracted = os.path.join(pmtiles_dir, name)
                    if extracted != exe:
                        shutil.move(extracted, exe)
                    break
    if os.path.isfile(exe):
        from platform_utils import make_executable
        make_executable(exe)
        log.info('pmtiles CLI installed at %s', exe)
        return exe
    return None

def _download_map_region_thread(region_id, bbox, maps_dir):
    """Background thread: extract a region from Protomaps planet using pmtiles CLI."""
    with _state_lock:
        _map_downloads[region_id] = {'progress': 0, 'status': 'Preparing...', 'error': None}
    try:
        # Get or install pmtiles CLI
        _map_downloads[region_id]['status'] = 'Installing pmtiles tool...'
        _map_downloads[region_id]['progress'] = 5
        pmtiles_exe = _get_pmtiles_cli()
        if not pmtiles_exe:
            _map_downloads[region_id] = {'progress': 0, 'status': 'Error', 'error': 'Failed to download pmtiles CLI'}
            return

        output_file = os.path.join(maps_dir, f'{region_id}.pmtiles')
        temp_file = output_file + '.tmp'

        # Clean up stale temp file from previous failed download
        if os.path.isfile(temp_file):
            try:
                os.remove(temp_file)
                log.info('Cleaned up stale temp file: %s', temp_file)
            except PermissionError:
                # File locked by another process — try alternative temp name
                temp_file = output_file + f'.{int(time.time())}.tmp'
                log.warning('Original temp file locked, using: %s', temp_file)

        # Source Cooperative mirror of Protomaps planet (supports range requests)
        source_url = 'https://data.source.coop/protomaps/openstreetmap/v4.pmtiles'

        bbox_str = f'{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}'

        _map_downloads[region_id]['status'] = f'Extracting region (bbox: {bbox_str})...'
        _map_downloads[region_id]['progress'] = 10

        # Run pmtiles extract with bbox
        cmd = [pmtiles_exe, 'extract', source_url, temp_file, f'--bbox={bbox_str}', '--maxzoom=12']
        log.info('Running: %s', ' '.join(cmd))

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, **_CREATION_FLAGS)

        # Monitor progress from output — wrapped in try/finally to prevent process leak
        lines = []
        try:
            for line in proc.stdout:
                lines.append(line.strip())
                # pmtiles extract outputs progress info
                if '%' in line:
                    try:
                        pct = int(float(line.split('%')[0].split()[-1]))
                        _map_downloads[region_id]['progress'] = min(10 + int(pct * 0.85), 95)
                    except (ValueError, IndexError):
                        pass
                _map_downloads[region_id]['status'] = f'Downloading tiles... {line.strip()}'

            proc.wait()
        except Exception:
            # Ensure the subprocess is cleaned up on any exception
            try:
                proc.terminate()
            except OSError:
                pass
            proc.wait()
            raise

        if proc.returncode != 0:
            err = '\n'.join(lines[-5:]) if lines else 'Unknown error'
            if 'permission denied' in err.lower() or 'access is denied' in err.lower():
                err = 'Permission denied. Your antivirus may be blocking pmtiles.exe. Add it to your antivirus exclusions, or try running NOMAD Field Desk as Administrator.'
            _map_downloads[region_id] = {'progress': 0, 'status': 'Error', 'error': f'pmtiles extract failed: {err}'}
            if os.path.isfile(temp_file):
                os.remove(temp_file)
            return

        # Rename temp to final
        if os.path.isfile(temp_file):
            try:
                if os.path.isfile(output_file):
                    os.remove(output_file)
                os.rename(temp_file, output_file)
            except PermissionError:
                # Output file may be locked by Flask tile server — retry with delay
                import time as _t
                _t.sleep(1)
                try:
                    if os.path.isfile(output_file):
                        os.remove(output_file)
                    os.rename(temp_file, output_file)
                except PermissionError as pe:
                    _map_downloads[region_id] = {'progress': 0, 'status': 'Error',
                        'error': f'Permission denied when saving map file. Close any programs using the maps folder and try again. ({pe})'}
                    return
            size = format_size(os.path.getsize(output_file))
            _map_downloads[region_id] = {'progress': 100, 'status': f'Complete ({size})', 'error': None}
            log.info('Map region %s downloaded: %s', region_id, size)
        else:
            _map_downloads[region_id] = {'progress': 0, 'status': 'Error', 'error': 'No output file produced'}

    except PermissionError as e:
        log.exception('Map download permission error for %s', region_id)
        _map_downloads[region_id] = {'progress': 0, 'status': 'Error',
            'error': 'Permission denied. Try running NOMAD Field Desk as Administrator, or check that your antivirus is not blocking pmtiles.exe.'}
    except Exception as e:
        log.exception('Map download error for %s', region_id)
        err_msg = str(e)
        if 'WinError 5' in err_msg or 'Permission denied' in err_msg or 'Access is denied' in err_msg:
            err_msg = 'Permission denied. Try running NOMAD Field Desk as Administrator, or check that your antivirus is not blocking pmtiles.exe.'
        _map_downloads[region_id] = {'progress': 0, 'status': 'Error', 'error': err_msg}

@maps_bp.route('/api/maps/download-region', methods=['POST'])
def api_maps_download_region():
    data = request.get_json() or {}
    region_id = data.get('region_id')
    if not region_id:
        return jsonify({'error': 'Missing region_id'}), 400

    # Check if already downloading
    if region_id in _map_downloads and _map_downloads[region_id].get('progress', 0) > 0 \
            and _map_downloads[region_id].get('progress', 0) < 100:
        return jsonify({'error': 'Already downloading'}), 409

    # Find region
    region = next((r for r in MAP_REGIONS if r['id'] == region_id), None)
    if not region:
        return jsonify({'error': 'Unknown region'}), 404

    maps_dir = get_maps_dir()
    bbox = region.get('bbox')
    if not bbox:
        return jsonify({'error': 'Region has no bounding box defined'}), 400

    t = threading.Thread(target=_download_map_region_thread, args=(region_id, bbox, maps_dir), daemon=True)
    t.start()
    return jsonify({'status': 'started', 'region_id': region_id})

@maps_bp.route('/api/maps/download-url', methods=['POST'])
def api_maps_download_url():
    """Download a map file from a direct URL."""
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    filename = data.get('filename', '').strip()
    if not url:
        return jsonify({'error': 'Missing url'}), 400

    # SSRF protection — validate URL before downloading
    try:
        _validate_download_url(url)
    except ValueError as e:
        return jsonify({'error': f'Invalid download URL: {e}'}), 400

    if not filename:
        filename = url.rstrip('/').split('/')[-1]
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'error': 'Invalid filename'}), 400

    dl_id = f'url-{filename}'
    if dl_id in _map_downloads and _map_downloads[dl_id].get('progress', 0) > 0 \
            and _map_downloads[dl_id].get('progress', 0) < 100:
        return jsonify({'error': 'Already downloading'}), 409

    def _dl_thread():
        import urllib.request
        _map_downloads[dl_id] = {'progress': 0, 'status': 'Connecting...', 'error': None}
        try:
            maps_dir = get_maps_dir()
            dest = os.path.join(maps_dir, filename)
            req = urllib.request.Request(url, headers={'User-Agent': 'NOMADFieldDesk/1.0.0'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                with open(dest, 'wb') as f:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int(downloaded / total * 100)
                            speed = format_size(downloaded)
                            _map_downloads[dl_id] = {'progress': pct, 'status': f'{speed} / {format_size(total)}', 'error': None}
                        else:
                            _map_downloads[dl_id] = {'progress': 50, 'status': f'{format_size(downloaded)} downloaded', 'error': None}
            _map_downloads[dl_id] = {'progress': 100, 'status': f'Complete ({format_size(os.path.getsize(dest))})', 'error': None}
        except Exception as e:
            _map_downloads[dl_id] = {'progress': 0, 'status': 'Error', 'error': str(e)}

    threading.Thread(target=_dl_thread, daemon=True).start()
    return jsonify({'status': 'started', 'dl_id': dl_id})

ALLOWED_MAP_EXTENSIONS = ('.pmtiles', '.mbtiles', '.geojson', '.gpx', '.kml')

@maps_bp.route('/api/maps/import-file', methods=['POST'])
def api_maps_import_file():
    """Import a local map file by copying it to the maps directory."""
    data = request.get_json() or {}
    source_path = data.get('path', '').strip()
    if not source_path:
        return jsonify({'error': 'No path provided'}), 400
    # Reject path traversal
    if '..' in source_path:
        return jsonify({'error': 'Invalid path: directory traversal not allowed'}), 400
    # Validate file extension
    ext = os.path.splitext(source_path)[1].lower()
    if ext not in ALLOWED_MAP_EXTENSIONS:
        return jsonify({'error': f'Unsupported map file type: {ext}. Allowed: {", ".join(ALLOWED_MAP_EXTENSIONS)}'}), 400
    if not os.path.isfile(source_path):
        return jsonify({'error': 'File not found'}), 404
    filename = os.path.basename(source_path)
    dest = os.path.join(get_maps_dir(), filename)
    try:
        shutil.copy2(source_path, dest)
        return jsonify({'status': 'imported', 'filename': filename, 'size': format_size(os.path.getsize(dest))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── Waypoints API ─────────────────────────────────────────────────

WAYPOINT_CATEGORIES = ['rally', 'water', 'cache', 'shelter', 'hazard', 'medical', 'comms', 'general']
WAYPOINT_COLORS = {'rally': '#5b9fff', 'water': '#4fc3f7', 'cache': '#ff9800', 'shelter': '#4caf50',
                   'hazard': '#f44336', 'medical': '#e91e63', 'comms': '#b388ff', 'general': '#9e9e9e'}

@maps_bp.route('/api/waypoints')
def api_waypoints_list():
    db = get_db()
    rows = db.execute('SELECT * FROM waypoints ORDER BY created_at DESC').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@maps_bp.route('/api/waypoints', methods=['POST'])
def api_waypoints_create():
    data = request.get_json() or {}
    cat = data.get('category', 'general')
    color = WAYPOINT_COLORS.get(cat, '#9e9e9e')
    db = get_db()
    cur = db.execute('INSERT INTO waypoints (name, lat, lng, category, color, notes) VALUES (?, ?, ?, ?, ?, ?)',
                     (data.get('name', 'Waypoint'), data.get('lat', 0), data.get('lng', 0),
                      cat, color, data.get('notes', '')))
    db.commit()
    row = db.execute('SELECT * FROM waypoints WHERE id = ?', (cur.lastrowid,)).fetchone()
    db.close()
    return jsonify(dict(row)), 201

@maps_bp.route('/api/waypoints/<int:wid>', methods=['DELETE'])
def api_waypoints_delete(wid):
    db = get_db()
    db.execute('DELETE FROM waypoints WHERE id = ?', (wid,))
    db.commit()
    db.close()
    return jsonify({'status': 'deleted'})

# ─── Map Routes & Annotations API ────────────────────────────────

@maps_bp.route('/api/maps/routes')
def api_map_routes_list():
    db = get_db()
    rows = db.execute('SELECT * FROM map_routes ORDER BY created_at DESC LIMIT 500').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@maps_bp.route('/api/maps/routes', methods=['POST'])
def api_map_routes_create():
    data = request.get_json() or {}
    db = get_db()
    try:
        db.execute('INSERT INTO map_routes (name, waypoint_ids, distance_km, estimated_time_min, terrain_difficulty, notes) VALUES (?,?,?,?,?,?)',
                   (data.get('name', 'New Route'), json.dumps(data.get('waypoint_ids', [])),
                    data.get('distance_km', 0), data.get('estimated_time_min', 0),
                    data.get('terrain_difficulty', 'moderate'), data.get('notes', '')))
        db.commit()
        rid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        return jsonify({'status': 'created', 'id': rid})
    finally:
        db.close()

@maps_bp.route('/api/maps/routes/<int:rid>', methods=['DELETE'])
def api_map_routes_delete(rid):
    db = get_db()
    db.execute('DELETE FROM map_routes WHERE id = ?', (rid,))
    db.commit()
    db.close()
    return jsonify({'status': 'deleted'})

@maps_bp.route('/api/maps/elevation-profile/<int:route_id>')
def api_elevation_profile(route_id):
    """Get elevation profile for a map route using waypoint elevations."""
    db = get_db()
    try:
        route = db.execute('SELECT waypoint_ids FROM map_routes WHERE id = ?', (route_id,)).fetchone()
        if not route:
            return jsonify({'error': 'Route not found'}), 404
        wp_ids = json.loads(route['waypoint_ids'] or '[]')
        if not wp_ids:
            return jsonify({'points': [], 'total_ascent': 0, 'total_descent': 0})

        placeholders = ','.join(['?' for _ in wp_ids])
        waypoints = db.execute(
            f'SELECT id, name, lat, lng, elevation_m FROM waypoints WHERE id IN ({placeholders}) ORDER BY CASE ' +
            ' '.join([f'WHEN id = ? THEN {i}' for i, _ in enumerate(wp_ids)]) + ' END',
            wp_ids + wp_ids
        ).fetchall()

        points = []
        total_dist = 0
        total_ascent = 0
        total_descent = 0
        prev = None

        import math
        for wp in waypoints:
            elev = wp['elevation_m'] or 0
            if prev:
                # Haversine distance
                R = 6371000
                dLat = math.radians(wp['lat'] - prev['lat'])
                dLon = math.radians(wp['lng'] - prev['lng'])
                a = math.sin(dLat/2)**2 + math.cos(math.radians(prev['lat'])) * math.cos(math.radians(wp['lat'])) * math.sin(dLon/2)**2
                seg_dist = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                total_dist += seg_dist
                delta = elev - (prev['elevation_m'] or 0)
                if delta > 0:
                    total_ascent += delta
                else:
                    total_descent += abs(delta)
            points.append({
                'distance_m': round(total_dist),
                'elevation_m': round(elev, 1),
                'name': wp['name'],
                'lat': wp['lat'],
                'lng': wp['lng'],
            })
            prev = wp

        return jsonify({
            'points': points,
            'total_ascent': round(total_ascent, 1),
            'total_descent': round(total_descent, 1),
            'total_distance_m': round(total_dist),
        })
    finally:
        db.close()

@maps_bp.route('/api/maps/annotations')
def api_map_annotations_list():
    db = get_db()
    rows = db.execute('SELECT * FROM map_annotations ORDER BY created_at DESC LIMIT 500').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@maps_bp.route('/api/maps/annotations', methods=['POST'])
def api_map_annotations_create():
    data = request.get_json() or {}
    db = get_db()
    try:
        db.execute('INSERT INTO map_annotations (type, geojson, label, color, notes) VALUES (?,?,?,?,?)',
                   (data.get('type', 'polygon'), json.dumps(data.get('geojson', {})),
                    data.get('label', ''), data.get('color', '#ff0000'), data.get('notes', '')))
        db.commit()
        aid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        return jsonify({'status': 'created', 'id': aid})
    finally:
        db.close()

@maps_bp.route('/api/maps/annotations/<int:aid>', methods=['DELETE'])
def api_map_annotations_delete(aid):
    db = get_db()
    db.execute('DELETE FROM map_annotations WHERE id = ?', (aid,))
    db.commit()
    db.close()
    return jsonify({'status': 'deleted'})

# ─── Contour Line Generation API ──────────────────────────────────

def _generate_contours(points, bounds, interval=100, grid_size=50):
    """Generate contour lines from scattered elevation points using IDW interpolation + marching squares."""
    import math as _math
    if len(points) < 3:
        return []

    # Create interpolation grid
    lat_step = (bounds['north'] - bounds['south']) / grid_size
    lng_step = (bounds['east'] - bounds['west']) / grid_size
    grid = []

    for r in range(grid_size + 1):
        row = []
        for c in range(grid_size + 1):
            glat = bounds['south'] + r * lat_step
            glng = bounds['west'] + c * lng_step
            # IDW interpolation
            total_w = 0
            total_v = 0
            for p in points:
                d = _math.sqrt((glat - p['lat'])**2 + (glng - p['lng'])**2) * 111000  # approx meters
                if d < 1:
                    d = 1
                w = 1.0 / (d ** 2)
                total_w += w
                total_v += w * p['elevation']
            row.append(total_v / total_w if total_w > 0 else 0)
        grid.append(row)

    # Find elevation range and contour levels
    min_elev = min(min(row) for row in grid)
    max_elev = max(max(row) for row in grid)
    levels = list(range(int(min_elev // interval * interval), int(max_elev) + interval, interval))

    # March through grid cells to find contour crossings
    features = []
    for level in levels:
        segments = []
        for r in range(grid_size):
            for c in range(grid_size):
                # Get 4 corners of cell
                tl = grid[r + 1][c]
                tr = grid[r + 1][c + 1]
                bl = grid[r][c]
                br = grid[r][c + 1]

                # Check edges for contour crossings
                edges = []
                pairs = [
                    (bl, br, (r, c), (r, c + 1), 'bottom'),
                    (tl, tr, (r + 1, c), (r + 1, c + 1), 'top'),
                    (bl, tl, (r, c), (r + 1, c), 'left'),
                    (br, tr, (r, c + 1), (r + 1, c + 1), 'right'),
                ]
                for v1, v2, p1, p2, edge_name in pairs:
                    if (v1 <= level < v2) or (v2 <= level < v1):
                        t = (level - v1) / (v2 - v1) if v2 != v1 else 0.5
                        lat = bounds['south'] + (p1[0] + t * (p2[0] - p1[0])) * lat_step
                        lng = bounds['west'] + (p1[1] + t * (p2[1] - p1[1])) * lng_step
                        edges.append([lng, lat])

                if len(edges) == 2:
                    segments.append(edges)

        # Connect segments into lines (simplified — output segments as-is)
        for seg in segments[:200]:  # Limit segments per level
            features.append({
                'type': 'Feature',
                'properties': {'elevation': level, 'label': f'{level}m'},
                'geometry': {'type': 'LineString', 'coordinates': seg}
            })

    return features[:1000]  # Cap total features

@maps_bp.route('/api/maps/contours')
def api_maps_contours():
    """Generate contour line GeoJSON from waypoint/annotation elevation data."""
    import math as _math
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius_km = request.args.get('radius_km', 50, type=float)
    interval = request.args.get('interval', 100, type=int)

    if lat is None or lng is None:
        return jsonify({'error': 'lat and lng query parameters required'}), 400
    if interval < 10:
        interval = 10
    if interval > 1000:
        interval = 1000
    if radius_km < 1:
        radius_km = 1
    if radius_km > 500:
        radius_km = 500

    # Convert radius to approximate degree offset
    deg_offset = radius_km / 111.0

    db = get_db()
    try:
        # Query waypoints with elevation data within radius
        wps = db.execute(
            '''SELECT lat, lng, elevation_m FROM waypoints
               WHERE elevation_m IS NOT NULL
               AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?
               LIMIT 500''',
            (lat - deg_offset, lat + deg_offset, lng - deg_offset, lng + deg_offset)
        ).fetchall()

        points = [{'lat': w['lat'], 'lng': w['lng'], 'elevation': w['elevation_m']} for w in wps]
    finally:
        db.close()

    if len(points) < 3:
        return jsonify({
            'type': 'FeatureCollection',
            'features': [],
            'message': f'Need at least 3 elevation points in area (found {len(points)}). Add waypoints with elevation data.'
        })

    # Calculate bounds from the points
    bounds = {
        'south': lat - deg_offset,
        'north': lat + deg_offset,
        'west': lng - deg_offset,
        'east': lng + deg_offset,
    }

    features = _generate_contours(points, bounds, interval=interval)

    return jsonify({
        'type': 'FeatureCollection',
        'features': features,
        'meta': {
            'points_used': len(points),
            'interval': interval,
            'radius_km': radius_km,
            'contour_count': len(features)
        }
    })

@maps_bp.route('/api/maps/minimap-data')
def api_maps_minimap_data():
    """Returns waypoints + annotations for the dashboard mini-map widget."""
    db = get_db()
    waypoints = [dict(r) for r in db.execute('SELECT id, name, lat, lng, category, icon, color FROM waypoints ORDER BY name').fetchall()]
    routes = [dict(r) for r in db.execute('SELECT id, name, waypoint_ids, distance_km FROM map_routes ORDER BY created_at DESC LIMIT 10').fetchall()]
    annotations = [dict(r) for r in db.execute('SELECT id, type, label, color FROM map_annotations ORDER BY created_at DESC LIMIT 20').fetchall()]
    db.close()
    return jsonify({'waypoints': waypoints, 'routes': routes, 'annotations': annotations})

WAYPOINT_ICONS = {
    'pin': '&#128205;', 'home': '&#127968;', 'water': '&#128167;', 'cache': '&#128230;',
    'rally': '&#127937;', 'danger': '&#9888;', 'shelter': '&#9978;', 'medical': '&#9829;',
    'radio': '&#128225;', 'observation': '&#128065;', 'gate': '&#128682;', 'fuel': '&#9981;',
}

@maps_bp.route('/api/maps/waypoint-icons')
def api_waypoint_icons():
    return jsonify(WAYPOINT_ICONS)

@maps_bp.route('/api/maps/atlas', methods=['POST'])
def api_maps_atlas():
    """Generate printable map atlas pages for the current view area."""
    data = request.get_json() or {}
    try:
        center_lat = float(data.get('lat', 0) or 0)
    except (TypeError, ValueError):
        center_lat = 0.0
    try:
        center_lng = float(data.get('lng', 0) or 0)
    except (TypeError, ValueError):
        center_lng = 0.0
    raw_zoom_levels = data.get('zoom_levels', [10, 12, 14])
    if not isinstance(raw_zoom_levels, list):
        raw_zoom_levels = [raw_zoom_levels]
    zoom_levels = []
    for zoom in raw_zoom_levels[:6]:
        try:
            zoom_levels.append(max(1, min(int(zoom), 18)))
        except (TypeError, ValueError):
            continue
    if not zoom_levels:
        zoom_levels = [10, 12, 14]
    page_title = str(data.get('title') or 'NOMAD Map Atlas')
    try:
        grid_size = max(1, min(int(data.get('grid_size', 2) or 2), 10))
    except (TypeError, ValueError):
        grid_size = 2

    pages = []
    page_num = 1
    db = get_db()
    try:
        for zoom in zoom_levels:
            n = 2 ** zoom
            lat_per_tile = 360 / n * 0.7
            lng_per_tile = 360 / n

            page_lat_span = lat_per_tile * 1.5
            page_lng_span = lng_per_tile * 1.5

            half = grid_size / 2
            for row in range(grid_size):
                for col in range(grid_size):
                    page_lat = center_lat + (row - half + 0.5) * page_lat_span
                    page_lng = center_lng + (col - half + 0.5) * page_lng_span

                    nearby = db.execute(
                        '''SELECT name, lat, lng, category, icon FROM waypoints
                           WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? LIMIT 20''',
                        (
                            page_lat - page_lat_span / 2,
                            page_lat + page_lat_span / 2,
                            page_lng - page_lng_span / 2,
                            page_lng + page_lng_span / 2,
                        ),
                    ).fetchall()

                    pages.append({
                        'page': page_num,
                        'zoom': zoom,
                        'grid_ref': f'{chr(65 + col)}{row + 1}',
                        'center_lat': round(page_lat, 6),
                        'center_lng': round(page_lng, 6),
                        'bounds': {
                            'north': round(page_lat + page_lat_span / 2, 6),
                            'south': round(page_lat - page_lat_span / 2, 6),
                            'east': round(page_lng + page_lng_span / 2, 6),
                            'west': round(page_lng - page_lng_span / 2, 6),
                        },
                        'waypoints': [dict(r) for r in nearby],
                    })
                    page_num += 1
    finally:
        db.close()

    generated_at = time.strftime('%Y-%m-%d %H:%M')
    zoom_summary = ', '.join(str(z) for z in zoom_levels)
    waypoint_hits = sum(len(page['waypoints']) for page in pages)

    toc_rows = ''.join(
        f'<tr><td class="doc-strong">Page {page["page"]}</td><td>{esc(page["grid_ref"])}</td>'
        f'<td>{page["zoom"]}</td><td>{page["center_lat"]:.4f}, {page["center_lng"]:.4f}</td></tr>'
        for page in pages
    ) or '<tr><td colspan="4">No atlas pages generated.</td></tr>'
    toc_html = (
        '<div class="doc-table-shell"><table><thead><tr><th>Page</th><th>Grid</th><th>Zoom</th><th>Center</th></tr></thead>'
        f'<tbody>{toc_rows}</tbody></table></div>'
    )

    page_sections = ''
    for page in pages:
        waypoint_rows = ''.join(
            f'<tr><td class="doc-strong">{esc(str(wp.get("name") or "Waypoint"))}</td>'
            f'<td>{esc(str(wp.get("category") or "-"))}</td>'
            f'<td>{wp["lat"]:.5f}</td><td>{wp["lng"]:.5f}</td></tr>'
            for wp in page['waypoints']
            if wp.get('lat') is not None and wp.get('lng') is not None
        )
        waypoint_html = (
            '<div class="doc-table-shell"><table><thead><tr><th>Name</th><th>Category</th><th>Lat</th><th>Lng</th></tr></thead>'
            f'<tbody>{waypoint_rows}</tbody></table></div>'
            if waypoint_rows else
            '<div class="doc-empty">No saved waypoints fall inside this atlas page extent.</div>'
        )
        page_sections += f'''<section class="doc-section" style="page-break-before:always;">
  <div class="doc-grid-2">
    <div class="doc-panel doc-panel-strong">
      <h2 class="doc-section-title">Atlas Page {page["page"]}</h2>
      <div class="doc-chip-list">
        <span class="doc-chip">Grid {esc(page["grid_ref"])}</span>
        <span class="doc-chip">Zoom {page["zoom"]}</span>
        <span class="doc-chip">Center {page["center_lat"]:.4f}, {page["center_lng"]:.4f}</span>
      </div>
      <div class="doc-note-box" style="margin-top:12px;">Bounds: N{page["bounds"]["north"]:.4f} S{page["bounds"]["south"]:.4f} E{page["bounds"]["east"]:.4f} W{page["bounds"]["west"]:.4f}</div>
    </div>
    <div class="doc-panel">
      <h2 class="doc-section-title">Capture Workflow</h2>
      <div class="doc-checklist">
        <div class="doc-check-item"><div class="doc-check-box"></div><div class="doc-check-label">Base Map</div><div class="doc-check-copy">Load the offline layer for this area before printing or screen capture.</div></div>
        <div class="doc-check-item"><div class="doc-check-box"></div><div class="doc-check-label">Screen Grab</div><div class="doc-check-copy">Capture the current map at the listed center and zoom, then file it with this page.</div></div>
        <div class="doc-check-item"><div class="doc-check-box"></div><div class="doc-check-label">Annotate</div><div class="doc-check-copy">Mark routes, hazards, rally points, and fallback notes before storing the binder copy.</div></div>
      </div>
    </div>
  </div>
  <div class="doc-panel" style="margin-top:16px;">
    <h2 class="doc-section-title">Map Capture Window</h2>
    <div class="doc-note-box" style="min-height:280px;display:grid;place-items:center;text-align:center;border-style:dashed;border-width:2px;background:linear-gradient(180deg,#f8fbff 0%,#eef5fb 100%);">
      <div>
        <div class="doc-strong" style="font-size:16px;letter-spacing:0.08em;text-transform:uppercase;">Grid {esc(page["grid_ref"])} / Zoom {page["zoom"]}</div>
        <div style="margin-top:8px;">Center: {page["center_lat"]:.6f}, {page["center_lng"]:.6f}</div>
        <div style="margin-top:8px;color:#5d7085;">Use this frame for a pasted map screenshot, route markup, or field notes overlay.</div>
      </div>
    </div>
  </div>
  <div class="doc-panel" style="margin-top:16px;">
    <h2 class="doc-section-title">Waypoints in Area</h2>
    {waypoint_html}
  </div>
  <div class="doc-footer" style="margin-top:14px;">
    <span>{esc(page_title)}</span>
    <span>Page {page["page"]} of {len(pages)}</span>
    <span>Generated {generated_at}</span>
  </div>
</section>'''

    body = f'''<section class="doc-section">
  <div class="doc-grid-2">
    <div class="doc-panel doc-panel-strong">
      <h2 class="doc-section-title">Atlas Overview</h2>
      <div class="doc-note-box">Printable map packet for offline movement planning, route review, and field annotation. Each atlas page is centered on the requested map view and leaves space for a captured map image or hand-marked notes.</div>
      <div class="doc-chip-list" style="margin-top:12px;">
        <span class="doc-chip">Center {center_lat:.4f}, {center_lng:.4f}</span>
        <span class="doc-chip">Zooms {esc(zoom_summary)}</span>
        <span class="doc-chip">Grid {grid_size}x{grid_size}</span>
      </div>
    </div>
    <div class="doc-panel">
      <h2 class="doc-section-title">Handling Notes</h2>
      <div class="doc-checklist">
        <div class="doc-check-item"><div class="doc-check-box"></div><div class="doc-check-label">Classify</div><div class="doc-check-copy">Treat route annotations, rally points, and cache notes as sensitive operational information.</div></div>
        <div class="doc-check-item"><div class="doc-check-box"></div><div class="doc-check-label">Refresh</div><div class="doc-check-copy">Replace the packet after major waypoint updates, seasonal route changes, or terrain disruptions.</div></div>
        <div class="doc-check-item"><div class="doc-check-box"></div><div class="doc-check-label">Pair</div><div class="doc-check-copy">Store with the Operations Binder or go-kit so navigation references stay together.</div></div>
      </div>
    </div>
  </div>
</section>
<section class="doc-section" style="page-break-before:always;">
  <div class="doc-grid-2">
    <div class="doc-panel">
      <h2 class="doc-section-title">Atlas Contents</h2>
      {toc_html}
    </div>
    <div class="doc-panel">
      <h2 class="doc-section-title">Print Prep</h2>
      <div class="doc-note-box">Landscape format works best for captured screenshots, manual route markup, and margin notes. Use the waypoint table to cross-reference saved positions while reviewing the map image.</div>
      <div class="doc-note-box" style="margin-top:12px;border-color:#e9b7b7;background:#fff5f5;color:#7a1d1d;">
        <div class="doc-strong" style="letter-spacing:0.12em;text-transform:uppercase;">Authorized Use Only</div>
        <div style="margin-top:6px;">Do not leave printed atlases unsecured if they include rally points, logistics routes, or private site annotations.</div>
      </div>
    </div>
  </div>
</section>
{page_sections}'''

    html = render_print_document(
        page_title,
        'Landscape-ready atlas packet for offline navigation, screenshot capture, and field route annotation.',
        body,
        eyebrow='NOMAD Field Desk Map Atlas',
        meta_items=[f'Generated {generated_at}', f'Center {center_lat:.4f}, {center_lng:.4f}', 'Authorized use only'],
        stat_items=[
            ('Pages', len(pages)),
            ('Zoom Levels', len(zoom_levels)),
            ('Grid Size', f'{grid_size}x{grid_size}'),
            ('Waypoint Hits', waypoint_hits),
        ],
        accent_start='#102338',
        accent_end='#2f556f',
        max_width='1180px',
        landscape=True,
    )
    return Response(html, mimetype='text/html')

# ─── Portable Mode Detection ─────────────────────────────────────
@maps_bp.route('/api/system/portable-mode')

@maps_bp.route('/api/geocode/search')
def api_geocode_search():
    """Search waypoints, annotations, and contacts by name — offline geocoding."""
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify([])
    db = get_db()
    results = []
    # Search waypoints
    wps = db.execute("SELECT id, name, lat, lng, category, icon FROM waypoints WHERE name LIKE ? LIMIT 20",
                     (f'%{q}%',)).fetchall()
    for w in wps:
        results.append({'type': 'waypoint', 'name': w['name'], 'lat': w['lat'], 'lng': w['lng'],
                       'category': w['category'], 'icon': w['icon'], 'id': w['id']})

    # Search annotations
    anns = db.execute("SELECT id, name, lat, lng, type FROM map_annotations WHERE name LIKE ? LIMIT 20",
                      (f'%{q}%',)).fetchall()
    for a in anns:
        results.append({'type': 'annotation', 'name': a['name'], 'lat': a['lat'], 'lng': a['lng'],
                       'category': a['type'], 'id': a['id']})

    # Search garden plots with coordinates
    plots = db.execute("SELECT id, name, lat, lng FROM garden_plots WHERE name LIKE ? AND lat IS NOT NULL LIMIT 10",
                       (f'%{q}%',)).fetchall()
    for p in plots:
        if p['lat']:
            results.append({'type': 'garden_plot', 'name': p['name'], 'lat': p['lat'], 'lng': p['lng'], 'id': p['id']})

    # Search contacts with coordinates (from waypoints linked by name)
    contacts = db.execute("SELECT c.id, c.name, c.role, w.lat, w.lng FROM contacts c LEFT JOIN waypoints w ON w.name LIKE '%' || c.name || '%' WHERE c.name LIKE ? AND w.lat IS NOT NULL LIMIT 10",
                          (f'%{q}%',)).fetchall()
    for c in contacts:
        if c['lat']:
            results.append({'type': 'contact', 'name': c['name'], 'lat': c['lat'], 'lng': c['lng'],
                           'category': c['role'], 'id': c['id']})

    db.close()
    return jsonify(results[:50])

@maps_bp.route('/api/geocode/reverse')
def api_geocode_reverse():
    """Reverse geocode — find nearest named features to a lat/lng coordinate."""
    try:
        lat = float(request.args.get('lat', 0))
        lng = float(request.args.get('lng', 0))
    except (ValueError, TypeError):
        return jsonify([])

    db = get_db()
    # Simple distance-based search (approximate, using degree difference)
    # 1 degree latitude ≈ 111km, so 0.01 degree ≈ 1.1km
    search_radius = 0.05  # ~5.5km
    results = []

    wps = db.execute("""SELECT id, name, lat, lng, category, icon,
        ((lat - ?) * (lat - ?) + (lng - ?) * (lng - ?)) as dist_sq
        FROM waypoints
        WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?
        ORDER BY dist_sq LIMIT 10""",
        (lat, lat, lng, lng,
         lat - search_radius, lat + search_radius, lng - search_radius, lng + search_radius)).fetchall()

    import math
    for w in wps:
        # Haversine distance
        R = 6371000
        dLat = math.radians(w['lat'] - lat)
        dLon = math.radians(w['lng'] - lng)
        a = math.sin(dLat/2)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(w['lat'])) * math.sin(dLon/2)**2
        dist_m = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        results.append({'type': 'waypoint', 'name': w['name'], 'lat': w['lat'], 'lng': w['lng'],
                       'category': w['category'], 'distance_m': round(dist_m), 'id': w['id']})

    anns = db.execute("""SELECT id, name, lat, lng, type,
        ((lat - ?) * (lat - ?) + (lng - ?) * (lng - ?)) as dist_sq
        FROM map_annotations
        WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?
        ORDER BY dist_sq LIMIT 10""",
        (lat, lat, lng, lng,
         lat - search_radius, lat + search_radius, lng - search_radius, lng + search_radius)).fetchall()
    for a in anns:
        dLat = math.radians(a['lat'] - lat)
        dLon = math.radians(a['lng'] - lng)
        aa = math.sin(dLat/2)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(a['lat'])) * math.sin(dLon/2)**2
        dist_m = R * 2 * math.atan2(math.sqrt(aa), math.sqrt(1-aa))
        results.append({'type': 'annotation', 'name': a['name'], 'lat': a['lat'], 'lng': a['lng'],
                       'category': a['type'], 'distance_m': round(dist_m), 'id': a['id']})

    results.sort(key=lambda x: x.get('distance_m', 999999))
    db.close()
    return jsonify(results[:20])

# ─── LoRA Fine-Tuning Pipeline ───────────────────────────────────
