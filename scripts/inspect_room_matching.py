import os
import math
import re
from collections import Counter

import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

ROOM_TYPE = 'Type'
ROOM_NAME = 'Room no.'
GEOJSON_PATHS = {
    'Level_1': 'geojsons/ground_floor.geojson',
    'Level_2': 'geojsons/first_floor.geojson',
    'Level_3': 'geojsons/second_floor.geojson',
}


def distance_meters(a, b):
    lat1, lon1 = math.radians(a.y), math.radians(a.x)
    lat2, lon2 = math.radians(b.y), math.radians(b.x)
    mean_lat = (lat1 + lat2) / 2
    dx = (lon2 - lon1) * math.cos(mean_lat)
    dy = lat2 - lat1
    return 6_371_000 * math.hypot(dx, dy)


def build_floor_graph(gdf):
    corridors = gdf[gdf[ROOM_TYPE].astype(str).str.contains('corridor', case=False, na=False)]
    G = nx.Graph()
    for geom in corridors.geometry:
        if geom is None or geom.is_empty:
            continue
        boundary = geom.boundary
        lines = [boundary] if boundary.geom_type == 'LineString' else list(boundary.geoms)
        for line in lines:
            coords = list(line.coords)
            for i in range(len(coords) - 1):
                p1 = Point(coords[i])
                p2 = Point(coords[i + 1])
                G.add_edge((p1.x, p1.y), (p2.x, p2.y), weight=distance_meters(p1, p2))
    return G


def connect_to_corridor(point, G):
    nearest = None
    min_d = float('inf')
    for node in G.nodes:
        d = Point(node).distance(point)
        if d < min_d:
            min_d = d
            nearest = node
    return nearest


def canonical(text):
    if text is None:
        return '', ''
    normalized = str(text).strip().lower()
    alnum = ''.join(ch for ch in normalized if ch.isalnum())
    return normalized, alnum


def room_identifier_variants(value):
    normalized, alnum = canonical(value)
    variants = {normalized, alnum}
    without_prefix = re.sub(r'^(?:room|rm|room\s*(?:no\.?|number)?)\s*', '', normalized).strip()
    if without_prefix:
        variants.add(without_prefix)
        variants.add(''.join(ch for ch in without_prefix if ch.isalnum()))
    return {v for v in variants if v}


def room_matches_identifier(room_name, identifier):
    room_raw, room_alnum = canonical(room_name)
    return bool({room_raw, room_alnum} & room_identifier_variants(identifier))


def load_data():
    floor_gdfs = {}
    for lvl, path in GEOJSON_PATHS.items():
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        gdf = gpd.read_file(path)
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        floor_gdfs[lvl] = gdf
    return floor_gdfs


def find_best_match(input_str, all_rooms, floor_graphs):
    if not input_str:
        return None, None, []
    q_raw, q_alnum = canonical(input_str)

    for r in all_rooms:
        if room_matches_identifier(r['room_name'], input_str):
            floor = r['floor']
            centroid = Point(r['coords'])
            node = connect_to_corridor(centroid, floor_graphs[floor])
            return (floor, node), centroid, [r['room_name']]

    for r in all_rooms:
        if r['room_type'].strip().lower() == q_raw:
            floor = r['floor']
            centroid = Point(r['coords'])
            node = connect_to_corridor(centroid, floor_graphs[floor])
            return (floor, node), centroid, [r['room_type']]

    substr_matches = []
    for r in all_rooms:
        rn = str(r['room_name']).strip().lower()
        if q_raw and q_raw in rn:
            substr_matches.append(r)
    if substr_matches:
        r = substr_matches[0]
        node = connect_to_corridor(Point(r['coords']), floor_graphs[r['floor']])
        return (r['floor'], node), Point(r['coords']), [x['room_name'] for x in substr_matches[:10]]

    if q_alnum:
        for r in all_rooms:
            rn_alnum = ''.join(ch for ch in r['room_name'].strip().lower() if ch.isalnum())
            if rn_alnum and rn_alnum == q_alnum:
                node = connect_to_corridor(Point(r['coords']), floor_graphs[r['floor']])
                return (floor, node), Point(r['coords']), [r['room_name']]

    for r in all_rooms:
        rt = r['room_type'].strip().lower()
        if q_raw and q_raw in rt:
            node = connect_to_corridor(Point(r['coords']), floor_graphs[r['floor']])
            return (floor, node), Point(r['coords']), [r['room_type']]

    return None, None, []


def main():
    floor_gdfs = load_data()
    floor_graphs = {lvl: build_floor_graph(gdf) for lvl, gdf in floor_gdfs.items()}

    all_rooms = []
    for lvl, gdf in floor_gdfs.items():
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            centroid = geom.centroid
            room_name = str(row.get(ROOM_NAME, '')).strip()
            room_type = str(row.get(ROOM_TYPE, '')).strip()
            if not room_name:
                continue
            all_rooms.append({
                'floor': lvl,
                'room_type': room_type,
                'room_name': room_name,
                'coords': (float(centroid.x), float(centroid.y)),
            })

    match_counts = Counter()
    node_to_rooms = {}
    for room in all_rooms:
        node = connect_to_corridor(Point(room['coords']), floor_graphs[room['floor']])
        node_to_rooms.setdefault((room['floor'], node), []).append(room['room_name'])
        match_counts[node] += 1

    print('Total rooms:', len(all_rooms))
    print('Rooms per shared node (top 20):')
    for node, count in match_counts.most_common(20):
        print(count, node)

    tests = ['Room 101', '101', 'Exit', 'G17', 'G01', 'Room G01', 'S101', 'C9', 'C12', '216']
    for test in tests:
        node, centroid, candidates = find_best_match(test, all_rooms, floor_graphs)
        print('\nTest:', test)
        print('  node=', node)
        print('  centroid=', centroid)
        print('  candidates=', candidates)


if __name__ == '__main__':
    main()
