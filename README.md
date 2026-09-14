# Indoor Navigation System

This project is an indoor navigation application built with Python (Flask) and a web frontend. It calculates and visualizes the shortest paths between rooms across multiple floors, handling staircases and corridors using graph algorithms.

## Features

- Crowd-aware routing: flood-fill crowd observations across nearby corridor nodes and route around busy areas.

## Prerequisites

- POST/GET /crowd_status: Stores or reads crowd hotspots. POST body example:
  {"observations":[{"room":"G28","count":15}],"radius_m":25,"max_count":20}
- Crowd observations can also be sent directly to /get_path with avoid_crowd: true.
  Use "format":"json" to receive path nodes, distance, crowd exposure, and hotspot count.
  git clone <repository_url>
  cd INDOOR_NAV

2.  Install dependencies:
    It is recommended to use a virtual environment.
    python3 -m venv venv
    source venv/bin/activate # On Windows use `venv\Scripts\activate`
    pip install -r requirements.txt

## Usage

1.  Run the application:
    python app.py
2.  Access the web interface:
    Open your web browser and navigate to:
    http://127.0.0.1:5000

3.  Find a path:
    - Enter a "Start" location (e.g., a room number or name).
    - Enter an "End" location (or type "Exit" for the nearest emergency exit).
    - Click "Get Path" to view the route.

## Project Structure

- app.py: The main Flask server handling logic, graph construction, and pathfinding.
- geojsons/: Contains GeoJSON files representing the floor plans.
- template/: Contains the index.html frontend file.

## Tech Stack

- Backend: Flask, NetworkX (Graph algorithms), GeoPandas (Spatial data), Shapely (Geometry).
- Visualization: Matplotlib (Plotting paths on maps).
- Frontend: HTML/JS (User interface).

## API Endpoints

- GET /: Serves the frontend application.
- POST /get_path: Calculates the path between two points.
- JSON Body: {"start": "Room A", "end": "Room B"}
- POST /simulate_crowd: Moves virtual users along the corridor graph and counts
  them at a selected time. Example body:
  {"timestamp":20,"users":[{"start":"G28","end":"Exit","speed_mps":1.2}]}
- The simulator output is automatically used by /get_path when avoid_crowd is true.
- POST /occupancy_status: Generates software-only occupancy estimates from the
  timetable. Use {"time":"13:30"} for a canteen peak or {"time":"09:20"}
  for an active 50-minute class. Classroom occupancy is estimated at 45 of 50,
  canteens at 23 during 13:00-14:00 and 16:00-18:00, and washrooms at 6 during
  breaks. These estimates are then used by /get_path.
- GET /get_rooms: Returns a list of available room types.
- GET /debug_rooms: Returns debugging information about loaded rooms.

## LICENSE

This project is licensed under the GNU General Public License v3.0 (GPL-3.0).

This means:
You are free to use, modify, and distribute this software.
Any distributed modifications must also be released under the same license.
The source code must remain open.
See the LICENSE file for full license details.

## Author

- R. Akshya
- Samriddhi Shaw
- Meghana Gopinath Tanuja
