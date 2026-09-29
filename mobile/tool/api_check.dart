// ignore_for_file: avoid_print
// Vérifie le dialogue avec TCShop sur le PC, avec le vrai code réseau de l'appli.
// Usage : dart run tool/api_check.dart <ip> <port> <clé>
import 'package:tcshop_mobile/api.dart';

Future<void> main(List<String> args) async {
  final api = SyncApi(args[0], int.parse(args[1]), args[2]);
  print('ping: ${await api.ping()}');
  print('découverte UDP: ${await SyncApi.discover()}');
  final cat = await api.catalog();
  final products = (cat['products'] as List).cast<Map>();
  print('catalogue: ${products.length} articles, ${(cat['orders'] as List).length} commandes, paiements ${cat['payments']}');
  final p = products.first;
  final ops = [
    {'uuid': 'dart-check-1', 'type': 'stock', 'date': '2026-09-28 10:00:00',
      'data': {'product_id': p['id'], 'delta': 3, 'reason': 'reception'}},
    {'uuid': 'dart-check-2', 'type': 'sale', 'date': '2026-09-28 10:05:00',
      'data': {'payment': 'Virement', 'lines': [{'product_id': p['id'], 'name': p['name'], 'qty': 1, 'unit_price': 9.5}]}},
  ];
  print('envoi: ${await api.push('dart-device', 'Test Dart', ops)}');
  print('renvoi (doit être ignoré): ${await api.push('dart-device', 'Test Dart', ops)}');
  try {
    await SyncApi(args[0], int.parse(args[1]), 'mauvaise').catalog();
  } on SyncException catch (e) {
    print('mauvaise clé -> $e');
  }
}
