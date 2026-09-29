import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'store.dart';

/// Recherche de cartes directement depuis le téléphone (4G en convention) dans les bases publiques gratuites :
/// Pokémon → TCGdex (noms français, prix Cardmarket), Magic → Scryfall, Yu-Gi-Oh! → YGOPRODeck.
const onlineGames = ['Pokémon', 'Magic: The Gathering', 'Yu-Gi-Oh!'];

class CardsApi {
  static const _timeout = Duration(seconds: 20);

  static Future<dynamic> _get(String url) async {
    final r = await http.get(Uri.parse(url), headers: {'Accept': 'application/json'}).timeout(_timeout);
    if (r.statusCode == 404 || r.statusCode == 400) return null;
    if (r.statusCode != 200) throw Exception('Erreur ${r.statusCode}');
    return jsonDecode(utf8.decode(r.bodyBytes));
  }

  static double _f(dynamic v) => v == null ? 0 : (double.tryParse('$v') ?? 0);

  // ------------------------------------------------------------------ recherche
  static Future<List<Json>> search(String game, String query) async {
    final q = query.trim();
    if (q.isEmpty) return [];
    try {
      switch (game) {
        case 'Pokémon':
          return _pokemon(q);
        case 'Magic: The Gathering':
          return _magic(q);
        case 'Yu-Gi-Oh!':
          return _yugioh(q);
      }
    } on TimeoutException {
      throw Exception('Pas de réponse : vérifiez la connexion Internet (4G / Wi-Fi).');
    }
    return [];
  }

  static Json _pkmCard(Json c, String lang) {
    final cm = ((c['pricing'] as Map?)?['cardmarket'] as Map?) ?? {};
    var price = 0.0;
    for (final k in ['trend', 'avg30', 'avg', 'trend-holo', 'avg30-holo']) {
      price = _f(cm[k]);
      if (price > 0) break;
    }
    final set = (c['set'] as Map?) ?? {};
    final img = '${c['image'] ?? ''}';
    return {
      'game': 'Pokémon', 'name': c['name'] ?? '', 'set_name': set['name'] ?? '', 'set_code': '${set['id'] ?? ''}'.toUpperCase(),
      'number': c['localId'] ?? '', 'rarity': c['rarity'] ?? '', 'image_url': img.isEmpty ? '' : '$img/low.png',
      'market_price': price, 'external_id': c['id'] ?? '', 'language': lang.toUpperCase(),
    };
  }

  static Future<List<Json>> _pokemon(String q) async {
    for (final lang in ['fr', 'en']) {
      final list = await _get('https://api.tcgdex.net/v2/$lang/cards?name=${Uri.encodeQueryComponent(q)}') as List?;
      if (list == null || list.isEmpty) continue;
      // les plus récentes d'abord ; le détail (prix) est chargé pour 30 cartes max, en parallèle
      final briefs = list.reversed.take(30).cast<Map>().toList();
      final details = await Future.wait(briefs.map((b) async {
        try {
          final d = await _get('https://api.tcgdex.net/v2/$lang/cards/${Uri.encodeComponent('${b['id']}')}');
          if (d is Map) return _pkmCard(d.cast<String, dynamic>(), lang);
        } catch (_) {}
        final img = '${b['image'] ?? ''}';
        return <String, dynamic>{
          'game': 'Pokémon', 'name': b['name'] ?? '', 'set_name': '', 'set_code': '', 'number': b['localId'] ?? '',
          'rarity': '', 'image_url': img.isEmpty ? '' : '$img/low.png', 'market_price': 0.0, 'external_id': b['id'] ?? '',
          'language': lang.toUpperCase(),
        };
      }));
      return details;
    }
    return [];
  }

  static Json _mtgCard(Map c) {
    var img = '${(c['image_uris'] as Map?)?['normal'] ?? ''}';
    if (img.isEmpty && c['card_faces'] is List && (c['card_faces'] as List).isNotEmpty) {
      img = '${((c['card_faces'] as List).first['image_uris'] as Map?)?['normal'] ?? ''}';
    }
    final prices = (c['prices'] as Map?) ?? {};
    final price = _f(prices['eur']) > 0 ? _f(prices['eur']) : _f(prices['eur_foil']);
    return {
      'game': 'Magic: The Gathering', 'name': c['printed_name'] ?? c['name'] ?? '', 'set_name': c['set_name'] ?? '',
      'set_code': '${c['set'] ?? ''}'.toUpperCase(), 'number': c['collector_number'] ?? '',
      'rarity': '${c['rarity'] ?? ''}', 'image_url': img, 'market_price': price, 'external_id': c['id'] ?? '',
      'language': '${c['lang'] ?? 'en'}'.toUpperCase(),
    };
  }

  static Future<List<Json>> _magic(String q) async {
    final d = await _get('https://api.scryfall.com/cards/search?unique=prints&order=released&q=${Uri.encodeQueryComponent(q)}');
    final data = (d is Map ? d['data'] as List? : null) ?? const [];
    return data.take(80).map((c) => _mtgCard(c as Map)).toList();
  }

  static Future<List<Json>> _yugioh(String q) async {
    final d = await _get('https://db.ygoprodeck.com/api/v7/cardinfo.php?fname=${Uri.encodeQueryComponent(q)}');
    final data = (d is Map ? d['data'] as List? : null) ?? const [];
    final out = <Json>[];
    for (final c in data.take(30).cast<Map>()) {
      final img = '${((c['card_images'] as List?)?.first as Map?)?['image_url_small'] ?? ''}';
      final price = _f(((c['card_prices'] as List?)?.first as Map?)?['cardmarket_price']);
      final sets = (c['card_sets'] as List?)?.cast<Map>() ?? [<String, dynamic>{}];
      for (final s in sets.isEmpty ? [<String, dynamic>{}] : sets) {
        final code = '${s['set_code'] ?? ''}';
        out.add({
          'game': 'Yu-Gi-Oh!', 'name': c['name'] ?? '', 'set_name': s['set_name'] ?? '',
          'set_code': code.contains('-') ? code.split('-').first : code, 'number': code,
          'rarity': s['set_rarity'] ?? '', 'image_url': img, 'market_price': price, 'external_id': '${c['id'] ?? ''}',
          'language': 'EN',
        });
        if (out.length >= 120) return out;
      }
    }
    return out;
  }

  // ------------------------------------------------------------------ extensions (import de collection)
  static Future<List<({String code, String name, String date})>> sets(String game) async {
    switch (game) {
      case 'Pokémon':
        final d = await _get('https://api.tcgdex.net/v2/fr/sets') as List? ?? const [];
        return [for (final s in d.reversed.cast<Map>()) (code: '${s['id']}', name: '${s['name']}', date: '')];
      case 'Magic: The Gathering':
        final d = await _get('https://api.scryfall.com/sets') as Map? ?? const {};
        return [
          for (final s in ((d['data'] as List?) ?? const []).cast<Map>())
            if ((s['card_count'] ?? 0) > 0 && s['digital'] != true)
              (code: '${s['code']}'.toUpperCase(), name: '${s['name']}', date: '${s['released_at'] ?? ''}'),
        ];
      case 'Yu-Gi-Oh!':
        final d = await _get('https://db.ygoprodeck.com/api/v7/cardsets.php') as List? ?? const [];
        final rows = [
          for (final s in d.cast<Map>())
            (code: '${s['set_name']}', name: '${s['set_name']} (${s['set_code'] ?? ''})', date: '${s['tcg_date'] ?? ''}'),
        ];
        rows.sort((a, b) => b.date.compareTo(a.date));
        return rows;
    }
    return [];
  }
}
