import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';

import 'api.dart';
import 'platform/storage.dart';

typedef Json = Map<String, dynamic>;

late final AppStore store;

String newUuid() {
  final r = Random.secure();
  final b = List<int>.generate(16, (_) => r.nextInt(256));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  final h = b.map((v) => v.toRadixString(16).padLeft(2, '0')).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}

String nowStr([DateTime? d]) {
  d ??= DateTime.now();
  String p(int v) => v.toString().padLeft(2, '0');
  return '${d.year}-${p(d.month)}-${p(d.day)} ${p(d.hour)}:${p(d.minute)}:${p(d.second)}';
}

String money(num v) {
  final s = v.abs().toStringAsFixed(2).split('.');
  final ip = s[0];
  final buf = StringBuffer();
  for (var i = 0; i < ip.length; i++) {
    if (i > 0 && (ip.length - i) % 3 == 0) buf.write(' ');
    buf.write(ip[i]);
  }
  return '${v < 0 ? '-' : ''}$buf,${s[1]} €';
}

/// Date « 2026-09-28 14:03:00 » → « 28/09 14:03 »
String shortDate(String? s) {
  if (s == null || s.length < 16) return s ?? '';
  return '${s.substring(8, 10)}/${s.substring(5, 7)} ${s.substring(11, 16)}';
}

num numOf(dynamic v) => v is num ? v : num.tryParse('$v') ?? 0;

const orderStatuses = ['À préparer', 'Préparée', 'Expédiée', 'Livrée', 'Annulée'];
const nextStatus = {'À préparer': 'Préparée', 'Préparée': 'Expédiée', 'Expédiée': 'Livrée'};

/// Données du téléphone : copie du catalogue du PC + journal des opérations à envoyer.
/// Tout fonctionne hors ligne ; la synchro envoie le journal puis récupère le catalogue à jour.
class AppStore extends ChangeNotifier {
  Json config = {};
  Json catalog = {};
  List<Json> pending = [];
  List<Json> history = [];
  List<String> errors = [];
  bool syncing = false;
  String? lastError;
  final KvStorage _kv = KvStorage();
  Timer? _timer;

  final Map<int, Json> _byId = {};
  final Map<String, Json> _byCode = {};

  // ------------------------------------------------------------------ accès
  bool get paired => '${config['token'] ?? ''}'.isNotEmpty;

  /// Sur iPhone, l'appli est servie par le PC : son adresse est celle de la page.
  String get host => kIsWeb ? Uri.base.host : '${config['host'] ?? ''}';
  int get port => kIsWeb ? Uri.base.port : numOf(config['port'] ?? 8765).toInt();
  String get scheme => kIsWeb ? Uri.base.scheme : 'http';
  String get deviceName => '${config['device_name'] ?? 'Téléphone Android'}';
  String? get lastSync => config['last_sync'] as String?;
  String get shopName => '${(catalog['shop'] as Map?)?['name'] ?? 'TCShop'}';
  SyncApi get api => SyncApi(host, port, '${config['token'] ?? ''}', scheme: scheme);

  List<Json> _list(String key) => ((catalog[key] as List?) ?? const []).cast<Json>();
  List<Json> get products => _list('products');
  List<Json> get orders => _list('orders');
  List<String> get channels {
    final c = ((catalog['channels'] as List?) ?? const []).map((e) => '$e').toList();
    return c.isEmpty ? ['Site web', 'Cardmarket', 'eBay', 'Vinted', 'Leboncoin', 'Autre'] : c;
  }

  List<String> get payments {
    final p = ((catalog['payments'] as List?) ?? const []).map((e) => '$e').toList();
    return p.isEmpty ? ['Espèces', 'Virement', 'Wero'] : p;
  }

  // ------------------------------------------------------------------ rachats / collections
  List<String> get payouts {
    final p = ((catalog['payouts'] as List?) ?? const []).map((e) => '$e').toList();
    return p.isEmpty ? ['Espèces', 'Virement', 'Wero', 'Crédit boutique'] : p;
  }

  Json get settings => ((catalog['settings'] as Map?) ?? const {}).cast<String, dynamic>();
  double get buyRateCash => numOf(settings['buy_rate_cash'] ?? 50).toDouble();
  double get buyRateCredit => numOf(settings['buy_rate_credit'] ?? 65).toDouble();
  double get priceCoef => numOf(settings['price_coef'] ?? 1).toDouble();
  List<Json> get customers => _list('customers');
  List<Json> get collections => _list('collections');
  List<Json> get _cards => _list('collection_cards');

  static String keyOf(Json o) => o['id'] != null ? 'id:${o['id']}' : 'uuid:${o['uuid']}';

  /// Retrouve une collection, même si elle a été créée sur le téléphone puis synchronisée (uuid → id PC).
  Json? findCollection(Json col) {
    final refs = (config['refs'] as Map?) ?? const {};
    final mapped = col['uuid'] != null ? refs[col['uuid']] : null;
    for (final c in collections) {
      if ((col['id'] != null && c['id'] == col['id']) || (col['uuid'] != null && c['uuid'] == col['uuid']) ||
          (mapped != null && '${c['id']}' == '$mapped')) {
        return c;
      }
    }
    return null;
  }

  List<Json> cardsOf(Json col) => _cards
      .where((c) => (col['id'] != null && c['collection_id'] == col['id']) ||
          (col['uuid'] != null && c['collection_uuid'] == col['uuid']))
      .toList();

  Json? productById(dynamic id) => id == null ? null : _byId[numOf(id).toInt()];

  Json? findByCode(String code) {
    final c = code.trim().toLowerCase();
    return _byCode[c];
  }

  List<Json> search(String q, {bool inStockOnly = false}) {
    final words = q.toLowerCase().split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();
    final out = <Json>[];
    for (final p in products) {
      if (inStockOnly && p['track_stock'] != 0 && numOf(p['quantity']) <= 0) continue;
      if (words.isNotEmpty) {
        final hay = [p['name'], p['short_name'], p['variant'], p['brand'], p['set_name'], p['number'], p['sku'],
          p['barcode'], p['category'], p['game']].map((e) => '${e ?? ''}'.toLowerCase()).join(' ');
        if (!words.every(hay.contains)) continue;
      }
      out.add(p);
      if (out.length >= 150) break;
    }
    return out;
  }

  static String productLabel(Json p) {
    final extra = [p['variant'], p['set_name']].where((e) => '${e ?? ''}'.isNotEmpty).join(' · ');
    final card = p['category'] == 'Carte' ? ' (${p['condition'] ?? ''} ${p['language'] ?? ''})' : '';
    return '${p['name']}${extra.isNotEmpty ? ' — $extra' : ''}$card';
  }

  void _index() {
    _byId.clear();
    _byCode.clear();
    for (final p in products) {
      _byId[numOf(p['id']).toInt()] = p;
      for (final k in ['barcode', 'sku']) {
        final v = '${p[k] ?? ''}'.trim().toLowerCase();
        if (v.isNotEmpty) _byCode[v] = p;
      }
    }
    for (final b in ((catalog['barcodes'] as List?) ?? const []).cast<Json>()) {
      final p = _byId[numOf(b['product_id']).toInt()];
      if (p != null) _byCode['${b['code']}'.trim().toLowerCase()] = p;
    }
  }

  // ------------------------------------------------------------------ persistance
  Future<Json?> _read(String name) async {
    try {
      final v = await _kv.read(name);
      return v == null ? null : jsonDecode(v) as Json;
    } catch (_) {
      return null;
    }
  }

  Future<void> _write(String name, Object data) => _kv.write(name, jsonEncode(data));

  Future<void> _persist() async {
    await _write('config.json', config);
    await _write('pending.json', {'ops': pending, 'history': history, 'errors': errors});
  }

  Future<void> load() async {
    await _kv.init();
    config = await _read('config.json') ?? {};
    // iPhone : le lien ouvert depuis le QR code du PC contient la clé (…/app/?t=CLÉ)
    final urlToken = kIsWeb ? Uri.base.queryParameters['t'] : null;
    if (urlToken != null && urlToken.isNotEmpty) config['token'] = urlToken;
    if (kIsWeb && config['device_name'] == null) config['device_name'] = 'iPhone';
    catalog = await _read('catalog.json') ?? {};
    final p = await _read('pending.json') ?? {};
    pending = ((p['ops'] as List?) ?? const []).cast<Json>();
    history = ((p['history'] as List?) ?? const []).cast<Json>();
    errors = ((p['errors'] as List?) ?? const []).map((e) => '$e').toList();
    config['device_id'] ??= newUuid();
    config['device_name'] ??= 'Téléphone Android';
    await _persist();
    _index();
    for (final op in pending) {
      _applyLocal(op); // le catalogue enregistré est celui du PC : on rejoue les opérations pas encore envoyées
    }
    _timer = Timer.periodic(const Duration(seconds: 60), (_) => sync());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  // ------------------------------------------------------------------ opérations
  Future<Json> addOp(String type, Json data, {String? label}) async {
    final op = <String, dynamic>{'uuid': newUuid(), 'type': type, 'date': nowStr(), 'data': data};
    _applyLocal(op);
    pending.add(op);
    history.insert(0, {'uuid': op['uuid'], 'type': type, 'date': op['date'], 'label': label ?? type, 'data': data,
      'state': 'pending'});
    if (history.length > 300) history.removeRange(300, history.length);
    await _persist();
    notifyListeners();
    unawaited(sync());
    return op;
  }

  void _delta(dynamic pid, int d) {
    final p = productById(pid);
    if (p != null && p['track_stock'] != 0) p['quantity'] = numOf(p['quantity']).toInt() + d;
  }

  void _applyLocal(Json op) {
    final d = (op['data'] as Map).cast<String, dynamic>();
    switch (op['type']) {
      case 'sale':
        for (final l in ((d['lines'] as List?) ?? const []).cast<Map>()) {
          _delta(l['product_id'], -numOf(l['qty']).toInt());
        }
      case 'order':
        final lines = ((d['lines'] as List?) ?? const []).cast<Map>();
        for (final l in lines) {
          _delta(l['product_id'], -numOf(l['qty']).toInt());
        }
        final items = lines.fold<num>(0, (s, l) => s + numOf(l['qty']) * numOf(l['unit_price']));
        final list = (catalog['orders'] as List?) ?? [];
        list.insert(0, {
          'id': null, 'uuid': op['uuid'], 'number': 'Nouvelle', 'date': op['date'], 'channel': d['channel'],
          'external_ref': d['external_ref'] ?? '', 'customer_name': d['customer_name'] ?? '', 'address': d['address'] ?? '',
          'status': d['status'] ?? 'À préparer', 'shipping': d['shipping'] ?? 0, 'total': items + numOf(d['shipping']),
          'tracking': d['tracking'] ?? '', 'notes': d['notes'] ?? '', 'items': lines, 'local': true,
        });
        catalog['orders'] = list;
      case 'order_status':
        for (final o in orders) {
          final same = (d['order_id'] != null && o['id'] == d['order_id']) ||
              (d['order_uuid'] != null && o['uuid'] == d['order_uuid']);
          if (same) {
            o['status'] = d['status'];
            if (d['tracking'] != null) o['tracking'] = d['tracking'];
          }
        }
      case 'stock':
        _delta(d['product_id'], numOf(d['delta']).toInt());
      case 'buy':
        for (final l in ((d['lines'] as List?) ?? const []).cast<Map>()) {
          _delta(l['product_id'], numOf(l['qty']).toInt());
        }
      case 'collection_create':
      case 'collection_import_set':
        final list = (catalog['collections'] as List?) ?? [];
        list.add({'id': null, 'uuid': op['uuid'], 'name': d['name'], 'game': d['game'] ?? '',
          'description': op['type'] == 'collection_import_set' ? 'Import en cours : synchronisez avec le PC' : '',
          'local': true});
        catalog['collections'] = list;
      case 'collection_add_card':
        final list = (catalog['collection_cards'] as List?) ?? [];
        list.add({...d, 'id': null, 'uuid': op['uuid'], 'owned': numOf(d['owned']).toInt()});
        catalog['collection_cards'] = list;
      case 'collection_owned':
        for (final c in _cards) {
          if ((d['card_id'] != null && c['id'] == d['card_id']) || (d['card_uuid'] != null && c['uuid'] == d['card_uuid'])) {
            c['owned'] = max(0, numOf(c['owned']).toInt() + numOf(d['delta']).toInt());
          }
        }
    }
  }

  // ------------------------------------------------------------------ synchronisation
  Future<bool> sync({bool manual = false}) async {
    if (!paired || syncing) return false;
    syncing = true;
    notifyListeners();
    try {
      var api = this.api;
      if (!await api.ping()) {
        final found = kIsWeb ? null : await SyncApi.discover();
        if (found == null) {
          throw SyncException('PC introuvable. Vérifiez que TCShop est ouvert sur le PC et que vous êtes sur le même Wi-Fi.');
        }
        config['host'] = found.host;
        config['port'] = found.port;
        api = this.api;
      }
      if (pending.isNotEmpty) {
        final sent = List<Json>.of(pending);
        final res = await api.push('${config['device_id']}', deviceName, sent);
        final results = ((res['results'] as List?) ?? const []).cast<Map>();
        final refs = ((config['refs'] as Map?) ?? {}).cast<String, dynamic>();
        for (final r in results) {
          final uid = r['uuid'];
          if (r['ok'] == true && r['ref'] != null) refs['$uid'] = r['ref'];
          pending.removeWhere((o) => o['uuid'] == uid);
          for (final h in history) {
            if (h['uuid'] == uid) {
              h['state'] = r['ok'] == true ? 'ok' : 'error';
              if (r['ok'] != true) {
                h['error'] = r['error'];
                errors.insert(0, '${shortDate(h['date'] as String?)} · ${h['label']} : ${r['error']}');
              }
            }
          }
        }
        config['refs'] = refs;
      }
      if (((config['refs'] as Map?) ?? const {}).length > 500) config['refs'] = {};
      final cat = await api.catalog();
      catalog = cat;
      _index();
      for (final op in pending) {
        _applyLocal(op); // opérations faites pendant la synchro
      }
      await _write('catalog.json', cat);
      config['last_sync'] = nowStr();
      lastError = null;
      await _persist();
      return true;
    } catch (e) {
      lastError = e is SyncException ? e.message : 'Connexion au PC impossible ($e)';
      return false;
    } finally {
      syncing = false;
      notifyListeners();
    }
  }

  Future<bool> pair(Uri uri) async {
    final q = uri.queryParameters;
    final isTcshop = uri.scheme == 'tcshop' || uri.path.endsWith('/iphone') || uri.path.contains('/app');
    if (!isTcshop || (q['t'] ?? '').isEmpty) {
      throw SyncException("Ce QR code n'est pas un QR code d'association TCShop.");
    }
    // QR Android : tcshop://pair?h=IP&p=PORT&t=CLÉ — QR iPhone : http://IP:8765/iphone?t=CLÉ
    config['host'] = q['h'] ?? uri.host;
    config['port'] = int.tryParse(q['p'] ?? '') ?? (uri.scheme == 'tcshop' ? 8765 : 8765);
    config['token'] = q['t'];
    await _persist();
    notifyListeners();
    return sync(manual: true);
  }

  Future<void> unpair() async {
    config.remove('token');
    await _persist();
    notifyListeners();
  }

  Future<void> setDeviceName(String name) async {
    config['device_name'] = name.trim().isEmpty ? 'Téléphone Android' : name.trim();
    await _persist();
    notifyListeners();
  }

  Future<void> clearErrors() async {
    errors.clear();
    await _persist();
    notifyListeners();
  }
}
