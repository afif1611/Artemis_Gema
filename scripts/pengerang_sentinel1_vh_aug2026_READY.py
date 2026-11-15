#!/usr/bin/env python3
"""Download genuine Sentinel-1 VH GRD imagery over Pengerang as GeoTIFF.

Dataset: Google Earth Engine COPERNICUS/S1_GRD (calibrated, terrain-corrected dB).
Actual matched before/after UTC acquisition dates: 2026-08-23 and 2026-09-04.

IMPORTANT: A requested calendar date does not guarantee a satellite acquisition.
Default mode NEVER substitutes a different date. --nearest allows clearly
labelled, date-constrained before/after alternatives. No imagery or results are fabricated.

Required: pip install earthengine-api requests rasterio
Usage: python pengerang_sentinel1_vh_aug2026.py --project YOUR_EE_PROJECT_ID
       python pengerang_sentinel1_vh_aug2026.py --project YOUR_EE_PROJECT_ID --nearest
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import ee
import requests

# Geographical search region: [min lon, min lat, max lon, max lat]
# An initial search box, NOT a validated fire perimeter.
DEFAULT_BBOX = (104.10, 1.33, 104.30, 1.45)
EVENT_START = date(2026, 8, 24)
EVENT_END = date(2026, 8, 28)
TARGETS = (('before', date(2026, 8, 23)), ('after', date(2026, 9, 4)))
PROPERTIES = (
    'system:time_start', 'system:index', 'orbitProperties_pass',
    'relativeOrbitNumber_start', 'platform_number', 'resolution_meters',
    'instrumentMode', 'transmitterReceiverPolarisation'
)


def connect(project: str) -> None:
    try:
        ee.Initialize(project=project)
    except Exception:
        print('Google Earth Engine authentication is needed. Opening login flow...')
        ee.Authenticate()
        ee.Initialize(project=project)


def iso_date(millis: int) -> date:
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).date()


def discover(aoi: ee.Geometry, start: date, stop_exclusive: date) -> list[dict]:
    """Return real scene IDs and selected metadata, not image pixels."""
    collection = (
        ee.ImageCollection('COPERNICUS/S1_GRD')
        .filterBounds(aoi)
        .filterDate(start.isoformat(), stop_exclusive.isoformat())
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
        .sort('system:time_start')
    )
    count = int(collection.size().getInfo())
    if count > 100:
        raise RuntimeError(f'{count} scenes matched; narrow the search (maximum 100).')
    if count == 0:
        return []
    images = collection.toList(count)
    items = []
    for n in range(count):
        img = ee.Image(images.get(n))
        meta = img.toDictionary(list(PROPERTIES)).getInfo()
        acquisition = int(meta['system:time_start'])
        items.append({
            'scene_id': str(img.id().getInfo()),
            'date_utc': iso_date(acquisition),
            'time_utc': datetime.fromtimestamp(acquisition / 1000, timezone.utc).isoformat(),
            'pass': meta.get('orbitProperties_pass', ''),
            'relative_orbit': meta.get('relativeOrbitNumber_start', ''),
            'platform': meta.get('platform_number', ''),
            'resolution_m': meta.get('resolution_meters', ''),
            'bands': ','.join(meta.get('transmitterReceiverPolarisation', [])),
        })
    return items


def choose_scene(scenes: list[dict], target: date, phase: str,
                 allow_nearest: bool, used: set[str]) -> tuple[dict | None, str]:
    available = [s for s in scenes if s['scene_id'] not in used]
    exact = [s for s in available if s['date_utc'] == target]
    if exact:
        return exact[0], 'exact'
    if not allow_nearest:
        return None, 'no-exact-acquisition'

    # Alternatives still need to belong to the correct fire period.
    if phase == 'before':
        eligible = [s for s in available if EVENT_START - timedelta(days=14) <= s['date_utc'] < EVENT_START]
    else:
        eligible = [s for s in available if s['date_utc'] > EVENT_END and s['date_utc'] <= EVENT_END + timedelta(days=20)]
    if not eligible:
        return None, 'no-acquisition-in-valid-alternative-window'
    eligible.sort(key=lambda s: (abs((s['date_utc'] - target).days), s['time_utc']))
    return eligible[0], 'nearby-real-acquisition'


def safe_filename(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', value).strip('_')[-110:]


def download_image(scene: dict, aoi: ee.Geometry, outdir: Path,
                   phase: str, scale: int) -> Path:
    # IDs collected via img.id() can be short system:index names, not full
    # Earth Engine asset paths. Filter the original collection to load the
    # selected scene reliably, avoiding Image.load short-ID failures.
    matches = (ee.ImageCollection('COPERNICUS/S1_GRD')
               .filter(ee.Filter.eq('system:index', scene['scene_id'])))
    if matches.size().getInfo() != 1:
        raise RuntimeError('Cannot uniquely resolve scene in COPERNICUS/S1_GRD: ' + scene['scene_id'])
    # Preserve numerical VH dB values; -9999 marks missing pixels.
    image = ee.Image(matches.first()).select('VH').clip(aoi).unmask(-9999, False).toFloat()
    params = {
        'region': aoi,
        'crs': 'EPSG:32648',  # UTM zone 48N contains Pengerang.
        'scale': scale,
        'format': 'GEO_TIFF',
    }
    url = image.getDownloadURL(params)
    filename = f"Pengerang_S1_VH_{phase}_{scene['date_utc'].isoformat()}_{safe_filename(scene['scene_id'].split('/')[-1])}_{scale}m.tif"
    final = outdir / filename
    temp = final.with_suffix('.partial')
    print(f'  Downloading actual scene {scene["scene_id"]}')
    with requests.get(url, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        with temp.open('wb') as fp:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fp.write(chunk)
    if temp.stat().st_size < 512:
        temp.unlink(missing_ok=True)
        raise RuntimeError('Output unexpectedly small; not a valid GeoTIFF.')

    # Validate that this is a georeferenced, numerical 1-band raster.
    try:
        import rasterio
        with rasterio.open(temp, 'r+') as dataset:
            if dataset.count != 1 or dataset.crs is None:
                raise RuntimeError('Downloaded file is not a georeferenced single-band GeoTIFF.')
            dataset.nodata = -9999
            dataset.update_tags(source='ESA Copernicus Sentinel-1 via Google Earth Engine',
                                polarization='VH', units='dB',
                                scene_id=scene['scene_id'],
                                acquisition_utc=scene['time_utc'])
            dataset.update_tags(1, units='dB', polarization='VH')
            print(f'  Validated {dataset.width} x {dataset.height} pixels; CRS={dataset.crs}')
    except ImportError as exc:
        raise RuntimeError('Install rasterio: python -m pip install rasterio') from exc

    temp.replace(final)
    print(f'  Saved: {final} ({final.stat().st_size / 1024**2:.1f} MiB)')
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True,
                        help='Google Cloud project ID enabled for Earth Engine')
    parser.add_argument('--output', default='pengerang_s1_vh_aug2026')
    parser.add_argument('--scale', type=int, choices=(10, 20), default=20,
                        help='GeoTIFF pixel spacing in meters; 20 is faster/smaller')
    parser.add_argument('--nearest', action='store_true',
                        help='If either matching-date image is missing, allow a nearby before/after real scene')
    parser.add_argument('--bbox', type=float, nargs=4, default=DEFAULT_BBOX,
                        metavar=('MIN_LON', 'MIN_LAT', 'MAX_LON', 'MAX_LAT'))
    args = parser.parse_args()
    west, south, east, north = args.bbox
    if west >= east or south >= north:
        parser.error('Invalid bounding box order: expected min_lon min_lat max_lon max_lat')
    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)

    # CRITICAL: authenticate and initialize BEFORE constructing ee.Geometry.
    # Creating Earth Engine objects before ee.Initialize() raises:
    # 'Earth Engine client library not initialized.'
    print('Connecting to Google Earth Engine...', flush=True)
    connect(args.project)
    aoi = ee.Geometry.Rectangle([west, south, east, north], proj='EPSG:4326', geodesic=False)
    # Search broad enough to cover known 23-Aug and 04-Sep matching-orbit scenes.
    start = date(2026, 8, 9) if args.nearest else date(2026, 8, 23)
    end = date(2026, 9, 18) if args.nearest else date(2026, 9, 5)
    print(f'Searching real Sentinel-1 IW/VH scenes from {start} to {end - timedelta(days=1)} UTC')
    scenes = discover(aoi, start, end)
    if not scenes:
        print('NO MATCHING SENTINEL-1 VH SCENES found. No TIFF files will be fabricated.')
        print('Try widening the AOI or date window and checking Copernicus Browser.')
        return 2

    print(f'\nFound {len(scenes)} intersecting scenes:')
    for s in scenes:
        print(f"  {s['time_utc']} | {s['platform']} | {s['pass']} | relative orbit {s['relative_orbit']} | {s['scene_id']}")
    # Full catalogue metadata, even when a target acquisition is missing.
    with (outdir / 'available_scenes.csv').open('w', newline='', encoding='utf-8') as fp:
        writer = csv.DictWriter(fp, fieldnames=list(scenes[0].keys()))
        writer.writeheader()
        writer.writerows([{k: str(v) for k, v in item.items()} for item in scenes])

    selected = []
    used = set()
    for phase, requested_date in TARGETS:
        scene, status = choose_scene(scenes, requested_date, phase, args.nearest, used)
        if not scene:
            print(f'\n{phase.upper()}: no eligible image for {requested_date} ({status}).')
            if not args.nearest:
                print('  Run again with --nearest to search valid nearby event/post dates.')
            continue
        used.add(scene['scene_id'])
        print(f'\n{phase.upper()}: requested {requested_date}; ACTUAL acquisition {scene["date_utc"]} ({status})')
        try:
            result = download_image(scene, aoi, outdir, phase, args.scale)
        except Exception as exc:
            print(f'  ERROR downloading {phase}: {exc}')
            continue
        selected.append({
            'phase': phase,
            'requested_date': requested_date.isoformat(),
            'actual_date_utc': scene['date_utc'].isoformat(),
            'acquisition_time_utc': scene['time_utc'],
            'date_status': status,
            'scene_id': scene['scene_id'],
            'orbit_pass': scene['pass'],
            'relative_orbit': scene['relative_orbit'],
            'platform': scene['platform'],
            'polarization': 'VH',
            'units': 'dB',
            'crs': 'EPSG:32648',
            'output_pixel_spacing_m': args.scale,
            'filename': result.name,
        })

    with (outdir / 'scene_manifest.csv').open('w', newline='', encoding='utf-8') as fp:
        fields = ['phase', 'requested_date', 'actual_date_utc', 'acquisition_time_utc',
                  'date_status', 'scene_id', 'orbit_pass', 'relative_orbit',
                  'platform', 'polarization', 'units', 'crs',
                  'output_pixel_spacing_m', 'filename']
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    (outdir / 'study_area.geojson').write_text(json.dumps({
        'type': 'FeatureCollection', 'features': [{
            'type': 'Feature',
            'properties': {'name': 'Provisional Pengerang search AOI - NOT fire perimeter'},
            'geometry': {'type': 'Polygon', 'coordinates': [[
                [west, south], [east, south], [east, north], [west, north], [west, south]
            ]]}
        }]
    }, indent=2), encoding='utf-8')

    if len(selected) == 2:
        a, b = selected
        same_geometry = (a['orbit_pass'] == b['orbit_pass'] and
                         a['relative_orbit'] == b['relative_orbit'])
        if not same_geometry:
            print('\nCAUTION: Scenes have different orbit passes or relative orbits.')
            print('Do not subtract their dB values without assessing geometry/incident-angle effects.')
        else:
            print('\nOrbit pass/relative orbit match. Still examine masks, incidence angle,')
            print('speckle and surface-moisture effects before interpreting changes.')
    print(f'\nDownloaded {len(selected)} GeoTIFF(s). Metadata saved under: {outdir.resolve()}')
    print('NOTE: AOI has not been verified as the August 2026 burn perimeter.')
    return 0 if len(selected) == 2 else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(3)
