"""OpenStreetMap Overpass downloads — streets and POIs."""

from __future__ import annotations

import hashlib
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from xypi.map.graph import StreetGraph, graph_from_overpass
from xypi.map.locations import BASE_MAP_CONFIG
from xypi.map.view import MapView

# Public Overpass mirrors — tried in order on timeout / 5xx.
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]


def _cache_path(cache_dir: Path, prefix: str, bbox: list[float]) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha1(json.dumps([round(v, 8) for v in bbox]).encode("utf-8")).hexdigest()[:12]
    return cache_dir / f"{prefix}_{cache_key}.json"


def _mirror_urls(map_cfg: dict[str, Any]) -> list[str]:
    primary = map_cfg.get("overpass_url", BASE_MAP_CONFIG["overpass_url"])
    urls = [primary]
    for url in OVERPASS_MIRRORS:
        if url not in urls:
            urls.append(url)
    return urls


def _ssl_verify_failed(exc: Exception) -> bool:
    reason = getattr(exc, "reason", None)
    return (
        isinstance(exc, ssl.SSLCertVerificationError)
        or isinstance(reason, ssl.SSLCertVerificationError)
        or "CERTIFICATE_VERIFY_FAILED" in str(exc)
    )


def _read_overpass(url: str, body: bytes, *, timeout: int, context=None) -> dict:
    req = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": "XYPI/0.2 map-agent"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def _overpass_query(map_cfg: dict[str, Any], query_body: str, *, timeout: int = 90) -> dict:
    body = urllib.parse.urlencode({"data": query_body}).encode()
    last_exc: Exception | None = None

    for url in _mirror_urls(map_cfg):
        for attempt in range(2):
            try:
                return _read_overpass(url, body, timeout=timeout)
            except Exception as exc:
                last_exc = exc
                retryable = isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 502, 503, 504)
                retryable = retryable or isinstance(exc, TimeoutError) or "timed out" in str(exc).lower()
                if _ssl_verify_failed(exc):
                    try:
                        import certifi

                        ctx = ssl.create_default_context(cafile=certifi.where())
                        return _read_overpass(url, body, timeout=timeout, context=ctx)
                    except Exception as cert_exc:
                        last_exc = cert_exc
                        if map_cfg.get("allow_insecure_ssl_fallback", True):
                            try:
                                return _read_overpass(
                                    url, body, timeout=timeout, context=ssl._create_unverified_context()
                                )
                            except Exception as insecure_exc:
                                last_exc = insecure_exc
                if retryable and attempt == 0:
                    wait = 2.0 * (attempt + 1)
                    print(f"[map] Overpass retry ({url}) after {exc} — waiting {wait:.0f}s")
                    time.sleep(wait)
                    continue
                print(f"[map] Overpass mirror failed ({url}): {exc}")
                break

    raise RuntimeError(f"All Overpass mirrors failed: {last_exc}") from last_exc


def download_overpass(map_cfg: dict[str, Any], cache_dir: Path) -> dict:
    view = MapView.from_bbox(map_cfg["bbox"])
    cache = _cache_path(cache_dir, "streets", map_cfg["bbox"])
    if cache.exists():
        return json.loads(cache.read_text())

    query = f"""[out:json][timeout:90];
    way["highway"]["highway"!~"motorway|motorway_link|trunk|trunk_link|raceway|construction|proposed"]({view.south},{view.west},{view.north},{view.east});
    (._;>;);
    out body;"""
    data = _overpass_query(map_cfg, query, timeout=120)
    cache.write_text(json.dumps(data))
    return data


def _element_lat_lon(element: dict) -> tuple[float, float] | None:
    if element.get("type") == "node":
        return float(element["lat"]), float(element["lon"])
    center = element.get("center")
    if center and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    return None


def _parse_poi_elements(
    raw: dict,
    view: MapView,
    *,
    amenity: str,
    default_name: str,
) -> list[dict[str, Any]]:
    pois: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()
    for el in raw.get("elements", []):
        latlon = _element_lat_lon(el)
        if latlon is None:
            continue
        lat, lon = latlon
        key = (round(lat, 5), round(lon, 5))
        if key in seen:
            continue
        seen.add(key)
        x, y = view.normalize(lat, lon)
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("operator") or default_name
        pois.append(
            {
                "id": el.get("id"),
                "amenity": tags.get("amenity", amenity),
                "name": name,
                "lat": lat,
                "lon": lon,
                "x": x,
                "y": y,
                "osm_type": el.get("type", "node"),
            }
        )
    return pois


def download_pois(
    map_cfg: dict[str, Any],
    cache_dir: Path,
    *,
    amenity: str,
    prefix: str | None = None,
    query_body: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch POI features for an amenity type (nodes, ways with center)."""
    view = MapView.from_bbox(map_cfg["bbox"])
    prefix = prefix or amenity
    cache = _cache_path(cache_dir, prefix, map_cfg["bbox"])
    if cache.exists():
        return json.loads(cache.read_text())

    if query_body is None:
        query_body = f"""[out:json][timeout:60];
    node["amenity"="{amenity}"]({view.south},{view.west},{view.north},{view.east});
    out body;"""
    try:
        raw = _overpass_query(map_cfg, query_body, timeout=90)
    except Exception as exc:
        print(f"[map] POI download failed ({amenity}): {exc}")
        return []

    pois = _parse_poi_elements(raw, view, amenity=amenity, default_name=amenity)
    cache.write_text(json.dumps(pois))
    return pois


def download_schools(map_cfg: dict[str, Any], cache_dir: Path) -> list[dict[str, Any]]:
    """Schools + kindergartens from OSM nodes and building/amenity ways."""
    view = MapView.from_bbox(map_cfg["bbox"])
    query = f"""[out:json][timeout:90];
(
  node["amenity"~"^(school|kindergarten|college)$"]({view.south},{view.west},{view.north},{view.east});
  way["amenity"~"^(school|kindergarten|college)$"]({view.south},{view.west},{view.north},{view.east});
  node["building"="school"]({view.south},{view.west},{view.north},{view.east});
  way["building"="school"]({view.south},{view.west},{view.north},{view.east});
);
out center;"""
    return download_pois(
        map_cfg,
        cache_dir,
        amenity="school",
        prefix="schools_v2",
        query_body=query,
    )


def download_hospitals(map_cfg: dict[str, Any], cache_dir: Path) -> list[dict[str, Any]]:
    view = MapView.from_bbox(map_cfg["bbox"])
    query = f"""[out:json][timeout:90];
(
  node["amenity"~"^(hospital|clinic)$"]({view.south},{view.west},{view.north},{view.east});
  way["amenity"~"^(hospital|clinic)$"]({view.south},{view.west},{view.north},{view.east});
  node["healthcare"="hospital"]({view.south},{view.west},{view.north},{view.east});
  way["healthcare"="hospital"]({view.south},{view.west},{view.north},{view.east});
);
out center;"""
    return download_pois(
        map_cfg,
        cache_dir,
        amenity="hospital",
        prefix="hospitals_v2",
        query_body=query,
    )


def load_street_graph(map_cfg: dict[str, Any], cache_dir: Path) -> StreetGraph:
    view = MapView.from_bbox(map_cfg["bbox"])
    raw = download_overpass(map_cfg, cache_dir)
    graph = graph_from_overpass(raw, view, float(map_cfg.get("corner_angle_deg", 25.0)))
    if not graph.edges:
        raise RuntimeError("Overpass returned no usable street edges for this bounding box")
    return graph


def load_location_data(map_cfg: dict[str, Any], cache_dir: Path) -> dict[str, Any]:
    """Streets first (required), POIs best-effort (non-fatal on timeout)."""
    graph = load_street_graph(map_cfg, cache_dir)
    schools = download_schools(map_cfg, cache_dir)
    hospitals = download_hospitals(map_cfg, cache_dir)
    if not schools:
        print("[map] schools unavailable (empty or download failed)")
    if not hospitals:
        print("[map] hospitals unavailable (empty or download failed)")
    return {
        "graph": graph,
        "schools": schools,
        "hospitals": hospitals,
        "street_segments": len(graph.edges),
        "corner_nodes": len(graph.nodes),
    }
