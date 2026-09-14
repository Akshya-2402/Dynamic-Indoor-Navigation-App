class PdrResult {
  final List<double> raw;
  final List<double>? matched;
  final String floor;

  PdrResult({required this.raw, required this.matched, required this.floor});

  factory PdrResult.fromJson(Map<String, dynamic> json) {
    return PdrResult(
      raw: List<double>.from(json['raw'].map((x) => x.toDouble())),
      matched: json['matched'] != null ? List<double>.from(json['matched'].map((x) => x.toDouble())) : null,
      floor: json['floor'] as String,
    );
  }
}

class MapMatchResult {
  final List<double> input;
  final List<double>? matched;
  final String? floor;

  MapMatchResult({required this.input, required this.matched, this.floor});

  factory MapMatchResult.fromJson(Map<String, dynamic> json) {
    return MapMatchResult(
      input: List<double>.from(json['input'].map((x) => x.toDouble())),
      matched: json['matched'] != null ? List<double>.from(json['matched'].map((x) => x.toDouble())) : null,
      floor: json['floor'] as String?,
    );
  }
}
