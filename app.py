import matplotlib
matplotlib.use("Agg")
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import geopandas as gpd
import networkx as nx
from shapely.geometry import Point, LineString
from shapely.ops import nearest_points, unary_union
import matplotlib.pyplot as plt
import io
import os
import difflib
import math
import re

app = Flask(__name__)
CORS(app)

# --- CONFIG ---
ROOM_TYPE = "Type"
ROOM_NAME = "Room no."   # label column from GeoJSON
GEOJSON_PATHS = {
    "Level_1": "geojsons/ground_floor.geojson",
    "Level_2": "geojsons/first_floor.geojson",
    "Level_3": "geojsons/second_floor.geojson",
}
CORRIDOR_PATTERN = re.compile(r'^(c\d+|corridor|corriodr)$', re.IGNORECASE)

ROOM_DOOR_MAP = {
    # Ground Floor
    'G11': 'C14',
    'G10': 'C14',
    'G01': 'C15',
    'G02': 'C15',
    'G12': 'C12',
    'G14': 'C10',
    'G16': 'C10',
    'G17': 'C7',
    'G18': 'C7',
    'G19': 'C7',
    'G20': 'C8',
    'G21': 'C6',
    'G22': 'C6',
    'G23': 'C3',
    'G24': 'C3',
    'G25': 'C4',
    'G26': 'C4',
    'G27': 'C1',
    'G28': 'C1',
    'G04': 'C16',
    'G05': 'C17',
    'G06': 'C17',
    'G07': 'C16',
    'CanteenG01': 'C14',
    'ShopG01': 'C10',
    'B08': 'C8',
    'SAG01': 'C10',
    'SAG02': 'C10',

    # 1st Floor
    '101': 'C14',
    '102': 'C14',
    '103': '15',
    '104': 'C16',
    '105': '15',
    '106': 'C16',
    '107': 'C15',
    '108': 'C16',
    '109': 'C12',
    '110': 'C11',
    '111': 'C11',
    '112': 'C11',
    '113': 'C12',
    '116': 'C9',
    '117': 'C8',
    '118': 'C9',
    '119': 'C4',
    '120': 'C6',
    '121': 'C6',
    '122': 'C7',
    '123': 'C7',
    '124': 'C7',
    '125': 'C3',
    '126': 'C4',
    '127': 'C4',
    '128': 'C3',
    '129': 'C3',
    '131': 'C1',
    '132': 'C1',

    # 2nd Floor
    '201': 'C13',
    '202': 'C13',
    '203': 'C16',
    '204': 'C15',
    '205': 'C16',
    '206': 'C16',
    '207': 'C16',
    '208': 'C15',
    '209': 'C12',
    '210': 'C12',
    '212': 'C12',
    '213': 'C9',
    '214': 'C9',
    '215': 'C9',
    '216': 'C8',
    '217': 'C8',
    '218': 'C7',
    '219': 'C6',
    '220': 'C6',
    '221': 'C7',
    '222': 'C7',
    '223': 'C3',
    '224': 'C3',
    '225': 'C3',
    '226': 'C1',
    '227': 'C1',
}

# --- SAFE LOAD GEOJSONS ---
floor_gdfs = {}
for lvl, path in GEOJSON_PATHS.items():
    if not os.path.exists(path):
        print(f"GeoJSON missing: {path} (level {lvl}) - creating empty GeoDataFrame")
        floor_gdfs[lvl] = gpd.GeoDataFrame()
        continue
    try:
        gdf = gpd.read_file(path)
        gdf = gdf[gdf.geometry.notnull()]
        gdf = gdf[~gdf.geometry.is_empty]
        if ROOM_TYPE not in gdf.columns:
            gdf[ROOM_TYPE] = ""
        if ROOM_NAME not in gdf.columns:
            gdf[ROOM_NAME] = ""
        floor_gdfs[lvl] = gdf
        print(f"Loaded {len(gdf)} features from {path}")
    except Exception as e:
        print(f"Error reading {path}: {e}")
        floor_gdfs[lvl] = gpd.GeoDataFrame()

# --- HELPERS ---
def is_corridor_feature(row):
    rname = str(row.get(ROOM_NAME, "")).strip()
    rtype = str(row.get(ROOM_TYPE, "")).strip()
    return bool(CORRIDOR_PATTERN.match(rname) or CORRIDOR_PATTERN.match(rtype))

def get_door_corridor(room_name, room_geom, gdf):
    if room_name in ROOM_DOOR_MAP:
        mapped_corridor = ROOM_DOOR_MAP[room_name]
        if get_corridor_geometry(mapped_corridor, gdf) is not None:
            return mapped_corridor
        if room_geom is not None and gdf is not None and not gdf.empty:
            corridors = gdf[gdf.apply(is_corridor_feature, axis=1)]
            nearest = min(
                (row for _, row in corridors.iterrows()),
                key=lambda row: room_geom.distance(row.geometry),
                default=None,
            )
            if nearest is not None:
                name = str(nearest.get(ROOM_NAME, '')).strip()
                if name.lower() == 'corridor' or not name:
                    name = str(nearest.get(ROOM_TYPE, '')).strip()
                return name
    if room_geom is None or gdf is None or gdf.empty:
        return None
    corridors = gdf[gdf.apply(is_corridor_feature, axis=1)]
    best_c, max_len = None, -1.0
    nearest_c, nearest_d = None, float("inf")
    for _, crow in corridors.iterrows():
        cname = str(crow.get(ROOM_NAME, "")).strip()
        if cname.lower() == 'corridor' or not cname:
            cname = str(crow.get(ROOM_TYPE, "")).strip()
        cgeom = crow.geometry
        if cgeom is None: continue
        distance = room_geom.distance(cgeom)
        if distance < nearest_d:
            nearest_d, nearest_c = distance, cname
        inter = room_geom.intersection(cgeom)
        if inter.length > max_len:
            max_len, best_c = inter.length, cname
    return best_c or nearest_c

def get_corridor_geometry(corridor_name, gdf):
    if not corridor_name or gdf is None or gdf.empty:
        return None
    geometries = []
    for _, row in gdf.iterrows():
        if not is_corridor_feature(row):
            continue
        name = str(row.get(ROOM_NAME, '')).strip()
        if name.lower() == 'corridor' or not name:
            name = str(row.get(ROOM_TYPE, '')).strip()
        if name == corridor_name and row.geometry is not None and not row.geometry.is_empty:
            geometries.append(row.geometry)
    return unary_union(geometries) if geometries else None

def build_floor_graph(gdf):
    if gdf.empty:
        return nx.Graph()
    is_corridor_mask = gdf.apply(is_corridor_feature, axis=1)
    corridors = gdf[is_corridor_mask]
    G = nx.Graph()
    for _, row in corridors.iterrows():
        cname = str(row.get(ROOM_NAME, '')).strip()
        if cname.lower() == 'corridor' or not cname:
            cname = str(row.get(ROOM_TYPE, '')).strip()
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        boundary = geom.boundary
        lines = [boundary] if boundary.geom_type == "LineString" else list(boundary.geoms)
        for line in lines:
            coords = list(line.coords)
            for i in range(len(coords)-1):
                p1 = Point(coords[i])
                p2 = Point(coords[i+1])
                u = (p1.x, p1.y)
                v = (p2.x, p2.y)
                G.add_edge(u, v, weight=p1.distance(p2))
                G.nodes[u].setdefault("corridors", set()).add(cname)
                G.nodes[v].setdefault("corridors", set()).add(cname)
    return G

def connect_to_corridor(point, G, target_corridor=None, room_geom=None, corridor_geom=None):
    if G is None or len(G.nodes) == 0:
        return None
    pt = Point(point) if not isinstance(point, Point) else point
    candidates = list(G.nodes)
    if target_corridor:
        matching = [n for n in G.nodes if target_corridor in G.nodes[n].get("corridors", set())]
        if matching:
            candidates = matching
    nearest = None
    min_d = float("inf")
    fallback = None
    fallback_d = float("inf")
    allowed_geom = None
    if room_geom is not None and corridor_geom is not None:
        allowed_geom = unary_union([room_geom, corridor_geom])
    for node in candidates:
        try:
            node_pt = Point(node)
            d = pt.distance(node_pt)
        except Exception:
            continue
        if d < fallback_d:
            fallback_d = d
            fallback = node
        if allowed_geom is not None:
            connector = LineString([pt, node_pt])
            if connector.difference(allowed_geom).length > 1e-8:
                continue
        if d < min_d:
            min_d = d
            nearest = node
    return nearest if nearest is not None else fallback


def connect_to_corridor_node(point, G):
    if G is None or len(G.nodes) == 0:
        return None
    pt = Point(point) if not isinstance(point, Point) else point
    nearest = None
    min_d = float("inf")
    for node in G.nodes:
        try:
            node_pt = Point(node)
            d = pt.distance(node_pt)
        except Exception:
            continue
        if d < min_d:
            min_d = d
            nearest = node
    return nearest


def get_room_connection(room):
    floor = room["floor"]
    anchor = room_connection_nodes.get(id(room))
    return (floor, anchor), Point(room["coords"])

def nearest_pair_list(list_a, list_b):
    pairs = []
    used_b = set()
    for a in list_a:
        best_b = None
        best_d = float("inf")
        pa = Point(a)
        for b in list_b:
            if b in used_b:
                continue
            d = pa.distance(Point(b))
            if d < best_d:
                best_d = d
                best_b = b
        if best_b is not None:
            pairs.append((a, best_b))
            used_b.add(best_b)
    return pairs

# --- BUILD FLOOR GRAPHS & STAIRS ---
floor_graphs = {}
floor_stairs = {}
for lvl, gdf in floor_gdfs.items():
    G = build_floor_graph(gdf)
    floor_graphs[lvl] = G

    # Add staircase centroids
    stair_nodes = []
    if not gdf.empty:
        stairs = gdf[gdf[ROOM_TYPE].astype(str).str.contains("staircase", case=False, na=False)]
        for _, row in stairs.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            c = geom.centroid
            if c is None or c.is_empty:
                continue
            nearest = connect_to_corridor(c, G)
            if nearest:
                G.add_edge((float(c.x), float(c.y)), nearest, weight=0.5)
            stair_nodes.append((float(c.x), float(c.y)))
    floor_stairs[lvl] = stair_nodes

# --- SMART STAIR CONNECTIONS ---
# Match staircases by their name (SG01 <-> S201 etc.)
def get_stair_pairs():
    pairs = []
    levels = sorted(floor_gdfs.keys())
    for i in range(len(levels)-1):
        a, b = levels[i], levels[i+1]
        gdf_a, gdf_b = floor_gdfs[a], floor_gdfs[b]
        stairs_a = gdf_a[gdf_a[ROOM_TYPE].astype(str).str.contains("staircase", case=False, na=False)]
        stairs_b = gdf_b[gdf_b[ROOM_TYPE].astype(str).str.contains("staircase", case=False, na=False)]

        for _, row_a in stairs_a.iterrows():
            name_a = str(row_a.get(ROOM_NAME, "")).strip().lower()
            geom_a = row_a.geometry
            if geom_a is None or geom_a.is_empty:
                continue
            cent_a = (float(geom_a.centroid.x), float(geom_a.centroid.y))

            best_match = None
            min_dist = float("inf")
            for _, row_b in stairs_b.iterrows():
                name_b = str(row_b.get(ROOM_NAME, "")).strip().lower()
                geom_b = row_b.geometry
                if geom_b is None or geom_b.is_empty:
                    continue
                cent_b = (float(geom_b.centroid.x), float(geom_b.centroid.y))

                # match by similar ID (SG01 <-> S201 etc.)
                if name_a[:2] == name_b[:2] or name_a[-2:] == name_b[-2:]:
                    d = Point(cent_a).distance(Point(cent_b))
                    if d < min_dist:
                        min_dist = d
                        best_match = cent_b

            if best_match:
                pairs.append(((a, cent_a), (b, best_match)))
    return pairs

# --- MERGE GRAPH ---
G_all = nx.Graph()
for lvl, G in floor_graphs.items():
    for node in G.nodes:
        G_all.add_node((lvl, node))
    for u, v, data in G.edges(data=True):
        G_all.add_edge((lvl, u), (lvl, v), weight=data.get("weight", 1.0))

# --- Connect staircases between floors based on IDs ---
stair_pairs = get_stair_pairs()
for (a, sa), (b, sb) in stair_pairs:
    G_all.add_edge((a, sa), (b, sb), weight=1.0)

# --- ROOMS LIST ---
all_rooms = []
for lvl, gdf in floor_gdfs.items():
    if gdf.empty:
        continue
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        centroid = geom.centroid
        if centroid is None or centroid.is_empty:
            continue
        rtype = str(row.get(ROOM_TYPE, "")).strip()
        rname = str(row.get(ROOM_NAME, "")).strip()
        all_rooms.append({
            "floor": lvl,
            "room_type": rtype,
            "room_name": rname,
            "coords": (float(centroid.x), float(centroid.y)),
            "geom": geom
        })

room_connection_nodes = {}
for index, room in enumerate(all_rooms):
    floor = room["floor"]
    room_geom = room.get("geom")
    door_c = get_door_corridor(room["room_name"], room_geom, floor_gdfs[floor])
    corridor_geom = get_corridor_geometry(door_c, floor_gdfs[floor])
    if room_geom is None or corridor_geom is None:
        continue
    room_door, corridor_door = nearest_points(room_geom, corridor_geom)
    corridor_node = connect_to_corridor(
        corridor_door,
        floor_graphs[floor],
        target_corridor=door_c,
        corridor_geom=corridor_geom,
    )
    if corridor_node is None:
        continue
    anchor = (float(room_door.x), float(room_door.y))
    graph_anchor = (floor, anchor)
    graph_corridor_node = (floor, corridor_node)
    G_all.add_node(graph_anchor)
    G_all.add_edge(
        graph_anchor,
        graph_corridor_node,
        weight=Point(corridor_door).distance(Point(corridor_node)),
    )
    room_connection_nodes[id(room)] = anchor

room_name_list = [r["room_name"] for r in all_rooms if r["room_name"]]
room_type_list = [r["room_type"] for r in all_rooms if r["room_type"]]
match_candidates = sorted(list(set(room_name_list + room_type_list)))

# --- MATCHING FUNCTIONS ---
def canonical(s):
    if s is None:
        return ""
    s2 = str(s).strip().lower()
    s_alnum = "".join(ch for ch in s2 if ch.isalnum())
    return s2, s_alnum

def find_best_match(input_str):
    if not input_str:
        return None, None, []

    q_raw, q_alnum = canonical(input_str)

    for r in all_rooms:
        if r["room_name"].strip().lower() == q_raw:
            connection, centroid = get_room_connection(r)
            return connection, centroid, [r["room_name"]]

    for r in all_rooms:
        if r["room_type"].strip().lower() == q_raw:
            connection, centroid = get_room_connection(r)
            return connection, centroid, [r["room_type"]]

    substr_matches = []
    for r in all_rooms:
        rn = r["room_name"].strip().lower()
        if q_raw and q_raw in rn:
            substr_matches.append(r)
    if substr_matches:
        r = substr_matches[0]
        connection, centroid = get_room_connection(r)
        return connection, centroid, [x["room_name"] for x in substr_matches[:10]]

    if q_alnum:
        for r in all_rooms:
            rn_alnum = "".join(ch for ch in r["room_name"].strip().lower() if ch.isalnum())
            if rn_alnum and rn_alnum == q_alnum:
                connection, centroid = get_room_connection(r)
                return connection, centroid, [r["room_name"]]

    for r in all_rooms:
        rt = r["room_type"].strip().lower()
        if q_raw and q_raw in rt:
            connection, centroid = get_room_connection(r)
            return connection, centroid, [r["room_type"]]

    close = difflib.get_close_matches(input_str, match_candidates, n=5, cutoff=0.6)
    return None, None, close


def resolve_room_position(room):
    """Resolve a room-like identifier to a floor and centroid point."""
    if room is None:
        return None, None, []

    if isinstance(room, dict):
        room_text = room.get("room") or room.get("name") or room.get("room_name") or room.get("location")
        room_floor = room.get("floor")
    else:
        room_text = room
        room_floor = None

    if room_text is None:
        return None, None, []

    room_str = str(room_text).strip()
    if not room_str:
        return None, None, []

    connection, centroid, candidates = find_best_match(room_str)
    if connection is not None and centroid is not None:
        floor_name = connection[0]
        if room_floor is not None and floor_name != room_floor:
            floor_name = room_floor
        return floor_name, centroid, candidates
    return None, None, candidates


def resolve_floor_hint(floor, room):
    """Return an explicit floor and a room lookup tuple if the user supplied just a room name."""
    if floor not in (None, ""):
        return floor, None

    if room is None:
        return None, None

    if isinstance(room, dict):
        room_floor = room.get("floor")
        if room_floor not in (None, ""):
            return room_floor, None
        room_value = room.get("room") or room.get("name") or room.get("room_name") or room.get("location")
    else:
        room_floor = None
        room_value = room

    resolved_floor, centroid, candidates = resolve_room_position(room_value)
    if resolved_floor is not None and centroid is not None:
        return resolved_floor, (centroid, candidates)
    return None, None


def resolve_crowd_observation(observation):
    """Convert a crowd observation into a corridor graph node and intensity count."""
    if not isinstance(observation, dict):
        return None

    room_value = observation.get("room") or observation.get("name") or observation.get("location")
    floor_hint = observation.get("floor")
    x_value = observation.get("x")
    y_value = observation.get("y")
    count = observation.get("count", observation.get("intensity", observation.get("weight", 1.0)))

    try:
        count = float(count)
    except (TypeError, ValueError):
        return None
    if count <= 0:
        return None

    if isinstance(room_value, str) and room_value.strip():
        resolved_floor, centroid, _ = resolve_room_position(room_value)
        if resolved_floor is not None and centroid is not None:
            floor_hint = floor_hint or resolved_floor
            x_value = x_value if x_value is not None else centroid.x
            y_value = y_value if y_value is not None else centroid.y

    if floor_hint is None and x_value is not None and y_value is not None:
        for floor_name, G in floor_graphs.items():
            if G is None or G.number_of_nodes() == 0:
                continue
            node = connect_to_corridor_node(Point(float(x_value), float(y_value)), G)
            if node is not None:
                floor_hint = floor_name
                break

    if floor_hint is None or x_value is None or y_value is None:
        return None

    try:
        floor_name = str(floor_hint)
        x_coord = float(x_value)
        y_coord = float(y_value)
    except (TypeError, ValueError):
        return None

    G = floor_graphs.get(floor_name)
    if G is None or G.number_of_nodes() == 0:
        return None

    node = connect_to_corridor_node(Point(x_coord, y_coord), G)
    if node is None:
        return None

    return (floor_name, node), count


def flood_crowd_field(observations, radius_m=25.0, max_count=20.0):
    """Propagate crowd intensity from samples across the corridor graph."""
    field = {}
    seeds = []
    for observation in observations:
        resolved = resolve_crowd_observation(observation)
        if resolved:
            seeds.append(resolved)

    radius_m = max(0.1, float(radius_m))
    max_count = max(1.0, float(max_count))
    for seed, count in seeds:
        floor = seed[0]
        distances = nx.single_source_dijkstra_path_length(
            floor_graphs[floor], seed[1], cutoff=radius_m, weight="weight"
        )
        for node, distance in distances.items():
            intensity = min(1.0, count / max_count) * max(0.0, 1.0 - distance / radius_m)
            key = (floor, node)
            field[key] = min(1.0, field.get(key, 0.0) + intensity)
    return field, seeds


def crowd_weighted_graph(crowd_field, crowd_weight=4.0):
    """Copy the route graph and penalize edges passing through crowded nodes."""
    weighted = G_all.copy()
    for u, v, data in weighted.edges(data=True):
        base_weight = data.get("weight", 1.0)
        crowd = (crowd_field.get(u, 0.0) + crowd_field.get(v, 0.0)) / 2
        data["weight"] = base_weight * (1.0 + max(0.0, crowd_weight) * crowd)
    return weighted


def route_details(start_node, end_node, crowd_field=None, crowd_weight=4.0):
    """Return a route and its physical length plus crowd exposure."""
    crowd_field = crowd_field or {}
    graph = crowd_weighted_graph(crowd_field, crowd_weight)
    path_nodes = nx.astar_path(graph, start_node, end_node, weight="weight")
    distance = 0.0
    crowd_exposure = 0.0
    for from_node, to_node in zip(path_nodes, path_nodes[1:]):
        base = G_all.edges[from_node, to_node].get("weight", 0.0)
        distance += base
        crowd_exposure += base * (crowd_field.get(from_node, 0.0) + crowd_field.get(to_node, 0.0)) / 2
    return path_nodes, distance, crowd_exposure


def resolve_simulation_destination(identifier, start_node):
    """Resolve a room or the nearest reachable exit for a virtual user."""
    if str(identifier).strip().lower() != "exit":
        destination, _, candidates = find_best_match(identifier)
        return destination, candidates

    exits = [r for r in all_rooms if "exit" in r["room_type"].lower() or "exit" in r["room_name"].lower()]
    best = None
    best_distance = float("inf")
    for room in exits:
        node = connect_to_corridor_node(Point(room["coords"]), floor_graphs[room["floor"]])
        if node is None:
            continue
        destination = (room["floor"], node)
        try:
            distance = nx.shortest_path_length(G_all, start_node, destination, weight="weight")
        except nx.NetworkXNoPath:
            continue
        if distance < best_distance:
            best, best_distance = destination, distance
    return best, []


def simulate_crowd(users, timestamp):
    """Place virtual users on graph paths and count them at corridor nodes."""
    counts = {}
    locations = []
    errors = []
    for index, user in enumerate(users):
        if not isinstance(user, dict) or not user.get("start") or not user.get("end"):
            errors.append(f"User {index + 1} requires start and end")
            continue
        start_node, _, candidates = find_best_match(user["start"])
        if not start_node:
            errors.append(f"User {index + 1} start not found: {user['start']} ({candidates})")
            continue
        end_node, candidates = resolve_simulation_destination(user["end"], start_node)
        if not end_node:
            errors.append(f"User {index + 1} destination not found: {user['end']} ({candidates})")
            continue
        try:
            speed = max(0.1, float(user.get("speed_mps", 1.2)))
            start_time = float(user.get("start_time", 0.0))
            sample_time = float(timestamp)
        except (TypeError, ValueError):
            errors.append(f"User {index + 1} has invalid time or speed")
            continue
        if sample_time < start_time:
            continue
        try:
            path = nx.shortest_path(G_all, start_node, end_node, weight="weight")
        except nx.NetworkXNoPath:
            errors.append(f"User {index + 1} has no reachable path")
            continue

        remaining_distance = max(0.0, (sample_time - start_time) * speed)
        current_node = path[-1]
        for from_node, to_node in zip(path, path[1:]):
            edge_distance = G_all.edges[from_node, to_node].get("weight", 0.0)
            if remaining_distance <= edge_distance:
                current_node = from_node if edge_distance == 0 else from_node
                break
            remaining_distance -= edge_distance
        counts[current_node] = counts.get(current_node, 0) + 1
        locations.append({
            "user_id": user.get("user_id", f"user_{index + 1}"),
            "floor": current_node[0],
            "x": current_node[1][0],
            "y": current_node[1][1],
        })

    observations = [
        {"floor": floor, "x": node[0], "y": node[1], "count": count}
        for (floor, node), count in counts.items()
    ]
    return observations, locations, errors


def parse_clock_time(value):
    """Return minutes after midnight from HH:MM or a numeric minute value."""
    if isinstance(value, str) and ":" in value:
        hours, minutes = value.split(":", 1)
        return int(hours) * 60 + int(minutes)
    return int(float(value))


def scheduled_occupancy(clock_time):
    """Create explainable occupancy estimates from an example theory/lab timetable.

    This schedule uses the demo timetable pattern from the project: theory slots run
    in 50-minute blocks across the morning and afternoon, while labs occupy adjacent
    50-minute windows. The values are estimates for demonstration purposes only.
    """
    minutes = parse_clock_time(clock_time)
    hour = minutes // 60
    minute = minutes % 60

    theory_blocks = [
        (8 * 60, 8 * 60 + 50),
        (9 * 60, 9 * 60 + 50),
        (10 * 60, 10 * 60 + 50),
        (11 * 60, 11 * 60 + 50),
        (12 * 60, 12 * 60 + 50),
        (14 * 60, 14 * 60 + 50),
        (15 * 60, 15 * 60 + 50),
        (16 * 60, 16 * 60 + 50),
        (17 * 60, 17 * 60 + 50),
    ]
    lab_blocks = [
        (8 * 60, 8 * 60 + 50),
        (9 * 60 + 51, 10 * 60 + 41),
        (10 * 60 + 51, 11 * 60 + 41),
        (14 * 60, 14 * 60 + 50),
        (15 * 60, 15 * 60 + 50),
        (16 * 60, 16 * 60 + 50),
    ]
    transition_windows = [
        (8 * 60 + 50, 9 * 60),
        (9 * 60 + 50, 10 * 60),
        (10 * 60 + 50, 11 * 60),
        (11 * 60 + 50, 12 * 60),
        (12 * 60 + 50, 13 * 60),
        (13 * 60 + 30, 14 * 60),
        (14 * 60 + 50, 15 * 60),
        (15 * 60 + 50, 16 * 60),
        (16 * 60 + 50, 17 * 60),
        (17 * 60 + 50, 18 * 60),
    ]
    lunch_window = 12 * 60 + 30 <= minutes < 13 * 60 + 30
    canteen_peak = 12 * 60 + 30 <= minutes < 13 * 60 + 30 or 16 * 60 + 30 <= minutes < 17 * 60 + 30
    in_class = any(start <= minutes < end for start, end in theory_blocks + lab_blocks)
    in_break = any(start <= minutes < end for start, end in transition_windows) or lunch_window

    observations = []
    summary = {"classrooms": 0, "canteens": 0, "washrooms": 0}

    for room in all_rooms:
        room_type = room["room_type"].lower()
        count = 0
        category = None
        if "classroom" in room_type or "lab" in room_type or "laboratory" in room_type:
            count = 45 if in_class else (8 if in_break else 0)
            category = "classrooms"
        elif "canteen" in room_type:
            count = 23 if canteen_peak else 5
            category = "canteens"
        elif "washroom" in room_type or "wahroom" in room_type:
            count = 6 if in_break else (2 if in_class else 0)
            category = "washrooms"

        if count and category:
            observations.append({
                "floor": room["floor"],
                "x": room["coords"][0],
                "y": room["coords"][1],
                "count": count,
                "source": "scheduled_occupancy",
                "location": room["room_name"] or room["room_type"],
            })
            summary[category] += count

    return observations, {
        "time": f"{hour:02d}:{minute:02d}",
        "class_period_active": in_class,
        "between_classes": in_break,
        "canteen_peak": canteen_peak,
        "lunch_window": lunch_window,
        "totals": summary,
    }

# --- ROUTES ---
@app.route("/")
def home():
    return send_file("template/index.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/crowd_status", methods=["GET", "POST"])
def crowd_status():
    """Store samples and return the flood-filled crowd map.

    POST body: {"observations": [{"room": "101", "count": 12}, ...],
                "radius_m": 25, "max_count": 20}
    Each observation may use ``room`` or ``floor``, ``x``, ``y``.
    """
    global crowd_observations, crowd_settings
    data = request.get_json() or {}
    if request.method == "POST":
        observations = data.get("observations", [])
        if not isinstance(observations, list):
            return jsonify({"error": "observations must be a list"}), 400
        crowd_observations = [item for item in observations if isinstance(item, dict)]
        if data.get("include_occupancy"):
            try:
                scheduled, _ = scheduled_occupancy(data.get("time", "13:30"))
            except (TypeError, ValueError):
                return jsonify({"error": "time must be HH:MM or minutes after midnight"}), 400
            crowd_observations.extend(scheduled)

    try:
        radius_m = float(data.get("radius_m", 25.0))
        max_count = float(data.get("max_count", 20.0))
        crowd_settings = {"radius_m": radius_m, "max_count": max_count}
        field, seeds = flood_crowd_field(crowd_observations, radius_m, max_count)
    except (TypeError, ValueError):
        return jsonify({"error": "radius_m and max_count must be numbers"}), 400

    hotspots = [
        {"floor": floor, "x": node[0], "y": node[1], "intensity": round(intensity, 3)}
        for (floor, node), intensity in field.items()
        if intensity >= 0.2
    ]
    hotspots.sort(key=lambda item: item["intensity"], reverse=True)
    return jsonify({"observations": crowd_observations, "hotspots": hotspots,
                    "flooded_nodes": len(field), "radius_m": radius_m})


@app.route("/occupancy_status", methods=["GET", "POST"])
def occupancy_status():
    """Estimate occupancy from timetable rules and flood it across corridors.

    POST body: {"time": "13:30", "radius_m": 25, "max_count": 45}
    """
    global crowd_observations, crowd_settings
    data = request.get_json() or {}
    try:
        observations, schedule = scheduled_occupancy(data.get("time", "13:30"))
        radius_m = float(data.get("radius_m", 25.0))
        max_count = float(data.get("max_count", 45.0))
    except (TypeError, ValueError):
        return jsonify({"error": "time must be HH:MM and numeric settings must be valid"}), 400

    crowd_observations = observations
    crowd_settings = {"radius_m": radius_m, "max_count": max_count}
    field, _ = flood_crowd_field(observations, radius_m, max_count)
    hotspots = [
        {"floor": floor, "x": node[0], "y": node[1], "intensity": round(intensity, 3)}
        for (floor, node), intensity in field.items() if intensity >= 0.2
    ]
    hotspots.sort(key=lambda item: item["intensity"], reverse=True)
    return jsonify({"schedule": schedule, "observations": observations,
                    "hotspots": hotspots, "flooded_nodes": len(field)})


@app.route("/simulate_crowd", methods=["POST"])
def simulate_crowd_endpoint():
    """Generate crowd counts from virtual users at one simulation time.

    POST body: {"timestamp": 20, "users": [{"start": "G28",
                "end": "Exit", "speed_mps": 1.2, "start_time": 0}]}
    """
    global crowd_observations, crowd_settings
    data = request.get_json() or {}
    users = data.get("users", [])
    if not isinstance(users, list) or not users:
        return jsonify({"error": "users must be a non-empty list"}), 400
    try:
        timestamp = float(data.get("timestamp", 0.0))
        radius_m = float(data.get("radius_m", 25.0))
        max_count = float(data.get("max_count", max(1, len(users))))
    except (TypeError, ValueError):
        return jsonify({"error": "timestamp, radius_m and max_count must be numbers"}), 400

    observations, locations, errors = simulate_crowd(users, timestamp)
    crowd_observations = observations
    crowd_settings = {"radius_m": radius_m, "max_count": max_count}
    field, _ = flood_crowd_field(observations, radius_m, max_count)
    hotspots = [
        {"floor": floor, "x": node[0], "y": node[1], "intensity": round(intensity, 3)}
        for (floor, node), intensity in field.items()
        if intensity >= 0.2
    ]
    hotspots.sort(key=lambda item: item["intensity"], reverse=True)
    return jsonify({
        "timestamp": timestamp,
        "locations": locations,
        "observations": observations,
        "hotspots": hotspots,
        "flooded_nodes": len(field),
        "errors": errors,
    })

@app.route("/debug_rooms")
def debug_rooms():
    return jsonify({"count": len(all_rooms),
                    "room_names": room_name_list[:200],
                    "room_types": list(set(room_type_list))[:200],
                    "candidates_sample": match_candidates[:200]})


# --- PDR and Map-matching endpoints ---
@app.route("/map_match", methods=["POST"])
def map_match():
    """Map-match a single point to the nearest corridor node on the given floor.
    Request JSON: {"floor": "Level_1", "x": 100.0, "y": 200.0}
    Response JSON: {"input": [x,y], "matched": [mx,my] or null}
    """
    data = request.get_json() or {}
    floor = data.get("floor")
    x = data.get("x")
    y = data.get("y")
    room = data.get("room")

    # A room is also a useful floor hint after the UI has filled X/Y from a
    # previous map-match or PDR result.
    floor, room_lookup = resolve_floor_hint(floor, room)
    if (x is None or y is None) and room:
        if room_lookup is None:
            resolved_floor, centroid, candidates = resolve_room_position(room)
        else:
            resolved_floor = floor
            centroid, candidates = room_lookup
        if resolved_floor is None or centroid is None:
            return jsonify({"error": f"Room '{room}' not found", "candidates": candidates}), 400
        floor = floor or resolved_floor
        x, y = centroid.x, centroid.y

    if floor is None or x is None or y is None:
        return jsonify({"error": "floor, x and y or room required"}), 400

    G = floor_graphs.get(floor)
    if G is None:
        return jsonify({"error": f"Unknown floor '{floor}'"}), 400

    try:
        pt = Point(float(x), float(y))
    except Exception:
        return jsonify({"error": "Invalid coordinates"}), 400

    nearest = connect_to_corridor_point(pt, floor_corridor_lines.get(floor))
    if nearest:
        return jsonify({"input": [float(x), float(y)], "matched": [float(nearest[0]), float(nearest[1])], "floor": floor})
    else:
        return jsonify({"input": [float(x), float(y)], "matched": None, "floor": floor})


@app.route("/pdr_step", methods=["POST"])
def pdr_step():
    """Apply a single PDR step and return the raw and map-matched positions.
    Request JSON: {"floor":"Level_1", "x":X, "y":Y, "heading_deg":90.0, "step_length":0.7}
    or {"room": "Room 101", "heading_deg": 90.0}
    Response JSON: {"raw": [x,y], "matched": [mx,my], "floor": "Level_1"}
    """
    data = request.get_json() or {}
    floor = data.get("floor")
    x = data.get("x")
    y = data.get("y")
    room = data.get("room")
    heading = data.get("heading_deg", 0)
    step_length = data.get("step_length", 0.7)

    floor, room_lookup = resolve_floor_hint(floor, room)
    if (x is None or y is None) and room:
        if room_lookup is None:
            resolved_floor, centroid, candidates = resolve_room_position(room)
        else:
            resolved_floor = floor
            centroid, candidates = room_lookup
        if resolved_floor is None or centroid is None:
            return jsonify({"error": f"Room '{room}' not found", "candidates": candidates}), 400
        floor = floor or resolved_floor
        x, y = centroid.x, centroid.y

    if floor is None or x is None or y is None:
        return jsonify({"error": "floor, x and y or room required"}), 400

    try:
        sx = float(x)
        sy = float(y)
        hd = float(heading)
        sl = float(step_length)
    except Exception:
        return jsonify({"error": "Invalid numeric values"}), 400

    # heading: 0° = east, 90° = north; step length is measured in metres.
    nx, ny = offset_point_by_meters(sx, sy, hd, sl)

    # map-match to nearest corridor node on the same floor
    G = floor_graphs.get(floor)
    matched = None
    if G is not None and len(G.nodes) > 0:
        nearest = connect_to_corridor_point(Point((nx, ny)), floor_corridor_lines.get(floor))
        if nearest:
            matched = [float(nearest[0]), float(nearest[1])]

    return jsonify({
        "raw": [nx, ny],
        "matched": matched,
        "floor": floor
    })

@app.route("/get_rooms")
def get_rooms():
    types = sorted(list({r["room_type"] for r in all_rooms if r["room_type"]}))
    return jsonify(types)

@app.route("/get_path", methods=["POST"])
def get_path():
    data = request.get_json() or {}
    start_in = data.get("start", "")
    end_in = data.get("end", "")
    use_crowd = bool(data.get("avoid_crowd", False) or data.get("observations"))
    observations = data.get("observations", crowd_observations) if use_crowd else []
    try:
        crowd_field, crowd_seeds = flood_crowd_field(
            observations,
            data.get("radius_m", crowd_settings["radius_m"]),
            data.get("max_count", crowd_settings["max_count"]),
        )
        crowd_weight = float(data.get("crowd_weight", 4.0))
    except (TypeError, ValueError):
        return jsonify({"error": "Crowd settings must be numeric"}), 400

    start_node, start_centroid, start_candidates = find_best_match(start_in)
    if not start_node:
        return jsonify({
            "error": f"Start '{start_in}' not found",
            "candidates": start_candidates
        }), 400

    if isinstance(end_in, str) and end_in.strip().lower() == "exit":
        end_node, end_centroid = None, None
        exit_rooms = [r for r in all_rooms if "exit" in r["room_type"].lower() or "exit" in r["room_name"].lower()]
        best = None
        best_len = float("inf")
        best_cent = None
        for r in exit_rooms:
            enode = connect_to_corridor_node(Point(r["coords"]), floor_graphs[r["floor"]])
            if not enode:
                continue
            try:
                path, length, _ = route_details(
                    start_node, (r["floor"], enode), crowd_field, crowd_weight
                )
                if length < best_len:
                    best_len = length
                    best = (r["floor"], enode)
                    best_cent = Point(r["coords"])
            except Exception:
                continue
        if not best:
            return jsonify({"error": "No reachable emergency exit"}), 400
        end_node, end_centroid = best, best_cent
    else:
        end_node, end_centroid, end_candidates = find_best_match(end_in)
        if not end_node:
            return jsonify({
                "error": f"End '{end_in}' not found",
                "candidates": end_candidates
            }), 400

    try:
        path_nodes, route_distance, crowd_exposure = route_details(
            start_node, end_node, crowd_field, crowd_weight
        )
    except nx.NetworkXNoPath:
        return jsonify({"error": "No path between given nodes"}), 400

    if data.get("format") == "json":
        return jsonify({
            "path": [{"floor": floor, "x": node[0], "y": node[1]} for floor, node in path_nodes],
            "distance_m": round(route_distance, 2),
            "crowd_exposure": round(crowd_exposure, 2),
            "crowd_avoided": use_crowd,
            "hotspots": sum(1 for value in crowd_field.values() if value >= 0.2),
        })

    route_floors = []
    floor_segments = {}
    for f, _ in path_nodes:
        if f not in route_floors:
            route_floors.append(f)
    for (from_floor, from_node), (to_floor, to_node) in zip(path_nodes, path_nodes[1:]):
        if from_floor == to_floor:
            floor_segments.setdefault(from_floor, []).append((from_node, to_node))

    fig, axes = plt.subplots(len(route_floors), 1, figsize=(10, 6 * len(route_floors)))
    if len(route_floors) == 1:
        axes = [axes]
    for ax, floor in zip(axes, route_floors):
        gdf = floor_gdfs.get(floor)
        if gdf is None or gdf.empty:
            ax.set_title(f"{floor} (no data)")
            continue

        gdf.plot(ax=ax, color="lightgrey", edgecolor="black")

        # --- DISPLAY ROOM NUMBERS ON POLYGONS ---
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            c = geom.centroid
            if c is None or c.is_empty:
                continue
            room_no = str(row.get(ROOM_NAME, "")).strip()
            if room_no:
                ax.text(
                    c.x, c.y, room_no,
                    fontsize=7,
                    ha="center", va="center",
                    color="black", weight="bold",
                    bbox=dict(facecolor="white", alpha=0.6, edgecolor="none", pad=0.5),
                    zorder=6
                )

        # draw path
        for start_node, end_node in floor_segments.get(floor, []):
            seg = LineString([start_node, end_node])
            ax.plot(*seg.xy, linewidth=2, linestyle="--", color="blue", zorder=5)

        if use_crowd:
            for (crowd_floor, crowd_node), intensity in crowd_field.items():
                if crowd_floor == floor and intensity >= 0.05:
                    ax.scatter(
                        crowd_node[0], crowd_node[1], s=55 + 125 * intensity,
                        color="red", alpha=0.7 + 0.25 * intensity,
                        edgecolors="darkred", zorder=4,
                    )

        # draw stairs
        for sx, sy in floor_stairs.get(floor, []):
            ax.scatter(sx, sy, s=80, edgecolor="black", facecolor="yellow", zorder=6)

        # start and end
        if floor == start_node[0]:
            ax.scatter(start_centroid.x, start_centroid.y, s=100, color="green", zorder=8)
        if floor == end_node[0]:
            ax.scatter(end_centroid.x, end_centroid.y, s=100, color="blue", zorder=8)

        ax.set_title(f"Path on {floor}")
        ax.axis("off")

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)
    return send_file(buf, mimetype="image/png")

if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=5000)


