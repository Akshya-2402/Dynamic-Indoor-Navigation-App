import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'pdr_models.dart';

void main() {
  runApp(const IndoorNavigationApp());
}

class IndoorNavigationApp extends StatelessWidget {
  const IndoorNavigationApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Indoor Navigation',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff087f8c)),
        scaffoldBackgroundColor: const Color(0xfff3f7f7),
        cardTheme: CardThemeData(
          elevation: 0,
          margin: EdgeInsets.zero,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(18),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Color(0xffd4e0e0)),
          ),
        ),
        useMaterial3: true,
      ),
      home: const NavigationPage(),
    );
  }
}

class NavigationPage extends StatefulWidget {
  const NavigationPage({super.key});

  @override
  State<NavigationPage> createState() => _NavigationPageState();
}

class _NavigationPageState extends State<NavigationPage> {
  final _startController = TextEditingController(text: 'Room 101');
  final _endController = TextEditingController(text: 'Exit');
  final _floorController = TextEditingController();
  final _xController = TextEditingController();
  final _yController = TextEditingController();
  final _headingController = TextEditingController(text: '90');
  final _stepLengthController = TextEditingController(text: '0.7');
  final _baseUrlController = TextEditingController(
    text: 'http://localhost:5000',
  );
  final _crowdStartsController = TextEditingController(text: 'G26, G27, G28');
  final _crowdEndController = TextEditingController(text: 'Exit');
  final _crowdTimeController = TextEditingController(text: '10');
  final _crowdSpeedController = TextEditingController(text: '1.2');
  final _crowdRadiusController = TextEditingController(text: '25');

  bool _loading = false;
  String _status = 'Ready';
  String? _error;
  List<int>? _routeImageBytes;
  MapMatchResult? _lastMapMatch;
  PdrResult? _lastPdr;
  String? _activePdrRoom;
  Map<String, dynamic>? _crowdResult;
  Map<String, dynamic>? _crowdRoute;

  @override
  void initState() {
    super.initState();
    _startController.addListener(_onStartRoomChanged);
    _checkConnection();
  }

  void _onStartRoomChanged() {
    // A different room starts a new indoor-position session; never reuse the
    // previous room's coordinates for it.
    _activePdrRoom = null;
    _floorController.clear();
    _xController.clear();
    _yController.clear();
  }

  @override
  void dispose() {
    _startController.removeListener(_onStartRoomChanged);
    _startController.dispose();
    _endController.dispose();
    _floorController.dispose();
    _xController.dispose();
    _yController.dispose();
    _headingController.dispose();
    _stepLengthController.dispose();
    _baseUrlController.dispose();
    _crowdStartsController.dispose();
    _crowdEndController.dispose();
    _crowdTimeController.dispose();
    _crowdSpeedController.dispose();
    _crowdRadiusController.dispose();
    super.dispose();
  }

  Future<void> _checkConnection() async {
    final url = _baseUrlController.text.trim();
    if (url.isEmpty) {
      setState(() {
        _status = 'Enter a backend URL';
      });
      return;
    }

    try {
      final response = await http.get(Uri.parse('$url/health'));
      if (response.statusCode == 200) {
        setState(() {
          _status = 'Connected to Flask backend';
        });
      } else {
        setState(() {
          _status = 'Server responded with ${response.statusCode}';
        });
      }
    } catch (e) {
      setState(() {
        _status = 'Could not reach backend';
        _error = e.toString();
      });
    }
  }

  Future<void> _fetchRoute() async {
    final url = _baseUrlController.text.trim();
    if (url.isEmpty) {
      setState(() {
        _error = 'Please enter your Flask URL';
      });
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
      _routeImageBytes = null;
      _status = 'Requesting route...';
    });

    try {
      final response = await http.post(
        Uri.parse('$url/get_path'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'start': _startController.text.trim(),
          'end': _endController.text.trim(),
        }),
      );

      if (response.statusCode == 200) {
        setState(() {
          _routeImageBytes = response.bodyBytes;
          _status = 'Route received from Flask';
        });
      } else {
        final body = response.body;
        String message = 'Request failed';
        try {
          final decoded = jsonDecode(body);
          if (decoded is Map<String, dynamic> && decoded['error'] != null) {
            message = decoded['error'].toString();
          }
        } catch (_) {}
        setState(() {
          _error = message;
          _status = 'Route request failed';
        });
      }
    } catch (e) {
      setState(() {
        _error = e.toString();
        _status = 'Connection error';
      });
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  Future<void> _simulateCrowd() async {
    final url = _baseUrlController.text.trim();
    final starts = _crowdStartsController.text
        .split(',')
        .map((room) => room.trim())
        .where((room) => room.isNotEmpty)
        .toList();
    final timestamp = double.tryParse(_crowdTimeController.text.trim());
    final speed = double.tryParse(_crowdSpeedController.text.trim());
    final radius = double.tryParse(_crowdRadiusController.text.trim());
    if (url.isEmpty ||
        starts.isEmpty ||
        timestamp == null ||
        speed == null ||
        radius == null) {
      setState(
        () => _error =
            'Enter crowd rooms and valid time, speed, and radius values',
      );
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
      _crowdResult = null;
      _crowdRoute = null;
      _status = 'Simulating virtual users...';
    });
    try {
      final response = await http.post(
        Uri.parse('$url/simulate_crowd'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'timestamp': timestamp,
          'radius_m': radius,
          'users': starts
              .asMap()
              .entries
              .map(
                (entry) => {
                  'user_id': 'user_${entry.key + 1}',
                  'start': entry.value,
                  'end': _crowdEndController.text.trim(),
                  'speed_mps': speed,
                },
              )
              .toList(),
        }),
      );
      final decoded = jsonDecode(response.body);
      if (response.statusCode != 200) {
        throw Exception(decoded['error'] ?? 'Crowd simulation failed');
      }
      setState(() {
        _crowdResult = Map<String, dynamic>.from(decoded);
        _status = 'Crowd simulation complete';
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _status = 'Crowd simulation failed';
      });
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _fetchCrowdRoute() async {
    final url = _baseUrlController.text.trim();
    if (url.isEmpty) {
      setState(() => _error = 'Please enter your Flask URL');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _status = 'Finding a less crowded route...';
    });
    try {
      final response = await http.post(
        Uri.parse('$url/get_path'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'start': _startController.text.trim(),
          'end': _endController.text.trim(),
          'avoid_crowd': true,
          'format': 'json',
        }),
      );
      final decoded = jsonDecode(response.body);
      if (response.statusCode != 200) {
        throw Exception(decoded['error'] ?? 'Crowd-aware route failed');
      }
      setState(() {
        _crowdRoute = Map<String, dynamic>.from(decoded);
        _status = 'Less crowded route received';
      });

      final imageResponse = await http.post(
        Uri.parse('$url/get_path'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'start': _startController.text.trim(),
          'end': _endController.text.trim(),
          'avoid_crowd': true,
        }),
      );
      if (imageResponse.statusCode == 200) {
        setState(() => _routeImageBytes = imageResponse.bodyBytes);
      }
    } catch (e) {
      setState(() {
        _error = e.toString();
        _status = 'Crowd-aware route failed';
      });
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _mapMatch() async {
    final url = _baseUrlController.text.trim();
    if (url.isEmpty) {
      setState(() {
        _error = 'Please enter your Flask URL';
      });
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
      _lastMapMatch = null;
      _status = 'Map-matching...';
    });

    final xText = _xController.text.trim();
    final yText = _yController.text.trim();
    final startRoom = _startController.text.trim();
    final body = <String, dynamic>{};
    if (startRoom.isNotEmpty) {
      // Map matching always starts from the selected room, not the previous
      // room's X/Y values.
      body['room'] = startRoom;
    } else {
      final x = double.tryParse(xText);
      final y = double.tryParse(yText);
      if (x == null || y == null) {
        setState(
          () => _error = 'Enter a start room or both X and Y coordinates',
        );
        return;
      }
      body['x'] = x;
      body['y'] = y;
      if (_floorController.text.trim().isNotEmpty) {
        body['floor'] = _floorController.text.trim();
      }
    }

    try {
      final response = await http.post(
        Uri.parse('$url/map_match'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      );

      if (response.statusCode == 200) {
        setState(() {
          final result = MapMatchResult.fromJson(jsonDecode(response.body));
          _lastMapMatch = result;
          if (result.matched != null) {
            _xController.text = result.matched![0].toString();
            _yController.text = result.matched![1].toString();
          }
          if (result.floor != null) {
            _floorController.text = result.floor!;
          }
          _status = 'Map match successful';
        });
      } else {
        final decoded = jsonDecode(response.body);
        setState(() {
          _error = decoded['error'] ?? 'Map match failed';
          _status = 'Map match failed';
        });
      }
    } catch (e) {
      setState(() {
        _error = e.toString();
        _status = 'Connection error';
      });
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  Future<void> _pdrStep() async {
    final url = _baseUrlController.text.trim();
    if (url.isEmpty) {
      setState(() {
        _error = 'Please enter your Flask URL';
      });
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
      _lastPdr = null;
      _status = 'Running PDR step...';
    });

    final xText = _xController.text.trim();
    final yText = _yController.text.trim();
    final startRoom = _startController.text.trim();
    final body = <String, dynamic>{
      'heading_deg': double.tryParse(_headingController.text.trim()) ?? 0.0,
      'step_length': double.tryParse(_stepLengthController.text.trim()) ?? 0.7,
    };
    if (startRoom.isNotEmpty) {
      // The room identifies the correct floor when the user has not selected one.
      body['room'] = startRoom;
    }

    final x = double.tryParse(xText);
    final y = double.tryParse(yText);
    final startNewRoom = startRoom.isNotEmpty && _activePdrRoom != startRoom;
    if (startNewRoom) {
      // First step for a room: resolve its own centroid and floor.
      body['room'] = startRoom;
    } else if (x != null && y != null) {
      body['x'] = x;
      body['y'] = y;
      if (_floorController.text.trim().isNotEmpty) {
        body['floor'] = _floorController.text.trim();
      }
    } else if (startRoom.isNotEmpty) {
      // Resolve every room label (for example, “Room 102” or “G24”) first.
    } else {
      setState(() => _error = 'Enter a start room or both X and Y coordinates');
      return;
    }

    try {
      final response = await http.post(
        Uri.parse('$url/pdr_step'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      );

      if (response.statusCode == 200) {
        setState(() {
          final result = PdrResult.fromJson(jsonDecode(response.body));
          _lastPdr = result;
          _activePdrRoom = startRoom.isEmpty ? null : startRoom;
          _floorController.text = result.floor;
          final position = result.matched ?? result.raw;
          _xController.text = position[0].toString();
          _yController.text = position[1].toString();
          _status = 'PDR step successful';
        });
      } else {
        final decoded = jsonDecode(response.body);
        setState(() {
          _error = decoded['error'] ?? 'PDR step failed';
          _status = 'PDR step failed';
        });
      }
    } catch (e) {
      setState(() {
        _error = e.toString();
        _status = 'Connection error';
      });
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  Widget _buildResultCard() {
    final children = <Widget>[];

    if (_lastMapMatch != null) {
      children.addAll([
        const Text(
          'Map Match Result',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),
        Text('Raw: ${_lastMapMatch!.input}'),
        Text('Matched: ${_lastMapMatch!.matched ?? 'null'}'),
        const SizedBox(height: 12),
      ]);
    }

    if (_lastPdr != null) {
      children.addAll([
        const Text(
          'PDR Step Result',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),
        Text('Raw: ${_lastPdr!.raw}'),
        Text('Matched: ${_lastPdr!.matched ?? 'null'}'),
        Text('Floor: ${_lastPdr!.floor}'),
        const SizedBox(height: 12),
      ]);
    }

    if (children.isEmpty) {
      children.add(const Text('No PDR/Map-match results yet.'));
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: children,
        ),
      ),
    );
  }

  Widget _buildCrowdCard() {
    final locations = (_crowdResult?['locations'] as List?)?.length ?? 0;
    final observations = (_crowdResult?['observations'] as List?)?.length ?? 0;
    final flooded = _crowdResult?['flooded_nodes'] ?? 0;
    final hotspots = _crowdResult?['hotspots']?.length ?? 0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Software crowd simulation',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 6),
            const Text(
              'Virtual users move through the corridor graph. Their locations are counted and flooded into nearby areas.',
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _crowdStartsController,
              decoration: const InputDecoration(
                labelText: 'Virtual user start rooms (comma separated)',
                hintText: 'G28, G29, G30',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _crowdEndController,
              decoration: const InputDecoration(
                labelText: 'Virtual user destination',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _crowdTimeController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Time (seconds)',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    controller: _crowdSpeedController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Speed (m/s)',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    controller: _crowdRadiusController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Flood radius (m)',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              children: [
                ElevatedButton.icon(
                  onPressed: _loading ? null : _simulateCrowd,
                  icon: const Icon(Icons.groups),
                  label: const Text('Simulate crowd'),
                ),
                OutlinedButton.icon(
                  onPressed: _loading ? null : _fetchCrowdRoute,
                  icon: const Icon(Icons.alt_route),
                  label: const Text('Route around crowd'),
                ),
              ],
            ),
            if (_crowdResult != null) ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 16,
                runSpacing: 6,
                children: [
                  Text(
                    locations > 0
                        ? 'Users placed: $locations'
                        : 'Occupancy sources: $observations',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  Text('Flooded nodes: $flooded'),
                  Text('Hotspots: $hotspots'),
                ],
              ),
              if ((_crowdResult!['errors'] as List?)?.isNotEmpty ?? false)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(
                    'Skipped: ${(_crowdResult!['errors'] as List).join(' | ')}',
                    style: TextStyle(color: Colors.orange.shade900),
                  ),
                ),
            ],
            if (_crowdRoute != null) ...[
              const SizedBox(height: 8),
              Text(
                'Route distance: ${_crowdRoute!['distance_m']} m    Crowd exposure: ${_crowdRoute!['crowd_exposure']}',
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildStatusPanel(ColorScheme colors) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        child: Row(
          children: [
            Icon(
              _error == null ? Icons.check_circle : Icons.error,
              color: _error == null ? colors.primary : colors.error,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _status,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  if (_error != null)
                    Text(_error!, style: TextStyle(color: colors.error)),
                ],
              ),
            ),
            if (_loading)
              const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          children: [
            Icon(Icons.explore, size: 28),
            SizedBox(width: 10),
            Text(
              'Indoor Navigation',
              style: TextStyle(fontWeight: FontWeight.w700),
            ),
          ],
        ),
        backgroundColor: colors.primary,
        foregroundColor: Colors.white,
        elevation: 0,
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final contentWidth = constraints.maxWidth > 980
              ? 980.0
              : constraints.maxWidth;
          final fieldWidth = contentWidth > 700
              ? (contentWidth - 24) / 3
              : contentWidth;
          return SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 40),
            child: Center(
              child: SizedBox(
                width: contentWidth,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(24),
                      decoration: BoxDecoration(
                        color: colors.primaryContainer,
                        borderRadius: BorderRadius.circular(22),
                      ),
                      child: const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Navigate with confidence',
                            style: TextStyle(
                              fontSize: 28,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          SizedBox(height: 6),
                          Text(
                            'Plan indoor routes, test pedestrian movement, and avoid simulated congestion.',
                            style: TextStyle(fontSize: 15),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 20),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(22),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Plan your route',
                              style: TextStyle(
                                fontSize: 21,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                            const SizedBox(height: 4),
                            const Text(
                              'Choose where you are and where you want to go.',
                            ),
                            const SizedBox(height: 18),
                            TextField(
                              controller: _startController,
                              decoration: const InputDecoration(
                                labelText: 'Starting room or place',
                                prefixIcon: Icon(Icons.trip_origin),
                              ),
                            ),
                            const SizedBox(height: 12),
                            TextField(
                              controller: _endController,
                              decoration: const InputDecoration(
                                labelText: 'Destination',
                                prefixIcon: Icon(Icons.location_on),
                              ),
                            ),
                            const SizedBox(height: 16),
                            Wrap(
                              spacing: 12,
                              runSpacing: 12,
                              children: [
                                SizedBox(
                                  width: fieldWidth,
                                  child: TextField(
                                    controller: _baseUrlController,
                                    decoration: const InputDecoration(
                                      labelText: 'Backend URL',
                                      prefixIcon: Icon(Icons.dns),
                                    ),
                                  ),
                                ),
                                SizedBox(
                                  width: fieldWidth,
                                  child: TextField(
                                    controller: _floorController,
                                    decoration: const InputDecoration(
                                      labelText: 'Floor (optional)',
                                      prefixIcon: Icon(Icons.layers),
                                    ),
                                  ),
                                ),
                                SizedBox(
                                  width: fieldWidth,
                                  child: TextField(
                                    controller: _xController,
                                    keyboardType: TextInputType.number,
                                    decoration: const InputDecoration(
                                      labelText: 'X coordinate (optional)',
                                    ),
                                  ),
                                ),
                                SizedBox(
                                  width: fieldWidth,
                                  child: TextField(
                                    controller: _yController,
                                    keyboardType: TextInputType.number,
                                    decoration: const InputDecoration(
                                      labelText: 'Y coordinate (optional)',
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 18),
                            Wrap(
                              spacing: 12,
                              runSpacing: 10,
                              children: [
                                FilledButton.icon(
                                  onPressed: _loading ? null : _fetchRoute,
                                  icon: const Icon(Icons.route),
                                  label: const Text('Find shortest route'),
                                ),
                                OutlinedButton.icon(
                                  onPressed: _checkConnection,
                                  icon: const Icon(Icons.wifi_tethering),
                                  label: const Text('Check backend'),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            ExpansionTile(
                              tilePadding: EdgeInsets.zero,
                              childrenPadding: EdgeInsets.zero,
                              leading: const Icon(Icons.explore),
                              title: const Text(
                                'PDR and map matching tools',
                                style: TextStyle(fontWeight: FontWeight.w700),
                              ),
                              children: [
                                Wrap(
                                  spacing: 12,
                                  runSpacing: 12,
                                  children: [
                                    SizedBox(
                                      width: fieldWidth,
                                      child: TextField(
                                        controller: _headingController,
                                        keyboardType: TextInputType.number,
                                        decoration: const InputDecoration(
                                          labelText: 'Heading (degrees)',
                                        ),
                                      ),
                                    ),
                                    SizedBox(
                                      width: fieldWidth,
                                      child: TextField(
                                        controller: _stepLengthController,
                                        keyboardType: TextInputType.number,
                                        decoration: const InputDecoration(
                                          labelText: 'Step length (m)',
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 14),
                                Wrap(
                                  spacing: 12,
                                  runSpacing: 10,
                                  children: [
                                    OutlinedButton.icon(
                                      onPressed: _loading ? null : _mapMatch,
                                      icon: const Icon(Icons.gps_fixed),
                                      label: const Text('Map match position'),
                                    ),
                                    OutlinedButton.icon(
                                      onPressed: _loading ? null : _pdrStep,
                                      icon: const Icon(Icons.directions_walk),
                                      label: const Text('Run PDR step'),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 20),
                    _buildCrowdCard(),
                    const SizedBox(height: 16),
                    _buildStatusPanel(colors),
                    const SizedBox(height: 16),
                    _buildResultCard(),
                    if (_routeImageBytes != null) ...[
                      const SizedBox(height: 20),
                      const Text(
                        'Route map',
                        style: TextStyle(
                          fontSize: 21,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Card(
                        clipBehavior: Clip.antiAlias,
                        child: Padding(
                          padding: const EdgeInsets.all(10),
                          child: Image.memory(
                            Uint8List.fromList(_routeImageBytes!),
                            fit: BoxFit.contain,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
