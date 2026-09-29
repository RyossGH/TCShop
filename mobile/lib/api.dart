import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:http/http.dart' as http;

import 'platform/discovery.dart';

class SyncException implements Exception {
  SyncException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Dialogue avec TCShop sur le PC (même réseau Wi-Fi).
/// Android : http://ip:8765 ; iPhone (appli web servie par le PC) : https://ip:8443.
class SyncApi {
  SyncApi(this.host, this.port, this.token, {this.scheme = 'http'});

  final String host;
  final int port;
  final String token;
  final String scheme;

  static const corsHosts = ['assets.tcgdex.net', 'cards.scryfall.io', 'images.ygoprodeck.com'];

  Uri _u(String path) => Uri.parse('$scheme://$host:$port$path');
  Map<String, String> get _headers => {'X-TCShop-Token': token, 'Content-Type': 'application/json'};

  Future<bool> ping() async {
    try {
      final r = await http.get(_u('/api/ping')).timeout(const Duration(seconds: 3));
      return r.statusCode == 200 && r.body.contains('TCShop');
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>> catalog() async {
    final r = await http.get(_u('/api/catalog'), headers: _headers).timeout(const Duration(seconds: 40));
    _check(r);
    return jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> push(String deviceId, String deviceName, List<Map<String, dynamic>> ops) async {
    final body = jsonEncode({'device_id': deviceId, 'device_name': deviceName, 'ops': ops});
    final r = await http.post(_u('/api/sync'), headers: _headers, body: utf8.encode(body)).timeout(const Duration(seconds: 40));
    _check(r);
    return jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
  }

  void _check(http.Response r) {
    if (r.statusCode == 401) throw SyncException('Clé refusée par le PC : réassociez le téléphone (QR code).');
    if (r.statusCode != 200) throw SyncException('Le PC a répondu une erreur (${r.statusCode}).');
  }

  /// Adresse d'une image. Photos locales du PC : via le serveur de synchro.
  /// Sur iPhone, les images web passent aussi par le PC (le navigateur bloque les images d'autres sites).
  String? imageUrl(String? path) {
    if (path == null || path.isEmpty || host.isEmpty) return null;
    final t = Uri.encodeQueryComponent(token);
    if (path.startsWith('http://') || path.startsWith('https://')) {
      // ces sites autorisent l'affichage direct (utile en convention, loin du PC) ; les autres passent par le PC
      final direct = !kIsWeb || corsHosts.any((h) => Uri.tryParse(path)?.host == h);
      return direct ? path : '$scheme://$host:$port/api/image?url=${Uri.encodeQueryComponent(path)}&t=$t';
    }
    return '$scheme://$host:$port/api/image?path=${Uri.encodeQueryComponent(path)}&t=$t';
  }

  /// Retrouve le PC sur le Wi-Fi (Android uniquement), utile si son adresse IP a changé.
  static Future<({String host, int port})?> discover() => discoverPc();
}
