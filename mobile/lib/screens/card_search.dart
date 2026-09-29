import 'package:flutter/material.dart';

import '../cards_api.dart';
import '../store.dart';
import '../widgets.dart';

/// Ouvre la recherche dans les bases de cartes en ligne ; renvoie la carte choisie (nom, extension, prix, image…).
Future<Json?> pickOnlineCard(BuildContext context, {String game = 'Pokémon', String query = ''}) =>
    Navigator.push<Json>(context, MaterialPageRoute(builder: (_) => CardSearchScreen(game: game, query: query)));

class CardSearchScreen extends StatefulWidget {
  const CardSearchScreen({super.key, required this.game, this.query = ''});
  final String game;
  final String query;

  @override
  State<CardSearchScreen> createState() => _CardSearchScreenState();
}

class _CardSearchScreenState extends State<CardSearchScreen> {
  late String game = onlineGames.contains(widget.game) ? widget.game : onlineGames.first;
  late final ctrl = TextEditingController(text: widget.query);
  List<Json> results = [];
  bool loading = false;
  String? message;

  @override
  void initState() {
    super.initState();
    if (widget.query.isNotEmpty) _search();
  }

  Future<void> _search() async {
    if (ctrl.text.trim().isEmpty) return;
    setState(() {
      loading = true;
      message = null;
    });
    try {
      results = await CardsApi.search(game, ctrl.text);
      message = results.isEmpty ? 'Aucune carte trouvée.' : null;
    } catch (e) {
      results = [];
      message = 'Recherche impossible : pas de connexion Internet ?\n($e)';
    }
    if (mounted) setState(() => loading = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Base de cartes en ligne')),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 4),
          child: DropdownButtonFormField<String>(
            initialValue: game,
            decoration: const InputDecoration(labelText: 'Jeu', isDense: true),
            items: [for (final g in onlineGames) DropdownMenuItem(value: g, child: Text(g))],
            onChanged: (v) => setState(() => game = v ?? game),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
          child: TextField(
            controller: ctrl,
            autofocus: widget.query.isEmpty,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _search(),
            decoration: InputDecoration(
              hintText: game == 'Pokémon' ? 'Nom de la carte (ex. Dracaufeu)' : 'Nom de la carte (en anglais)',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: IconButton(icon: const Icon(Icons.arrow_forward), onPressed: _search),
            ),
          ),
        ),
        if (loading) const LinearProgressIndicator(),
        if (message != null)
          Padding(padding: const EdgeInsets.all(20), child: Text(message!, textAlign: TextAlign.center,
              style: const TextStyle(color: muted))),
        Expanded(
          child: ListView.builder(
            itemCount: results.length,
            itemBuilder: (_, i) {
              final c = results[i];
              final sub = [c['set_name'], if ('${c['number']}'.isNotEmpty) '#${c['number']}', c['rarity'], c['language']]
                  .where((e) => '${e ?? ''}'.isNotEmpty).join(' · ');
              return ListTile(
                leading: ProductImage(c, size: 44),
                title: Text('${c['name']}'),
                subtitle: Text(sub, style: const TextStyle(color: muted, fontSize: 12)),
                trailing: Text(numOf(c['market_price']) > 0 ? money(numOf(c['market_price'])) : '—',
                    style: const TextStyle(fontWeight: FontWeight.bold)),
                onTap: () => Navigator.pop(context, c),
              );
            },
          ),
        ),
      ]),
    );
  }
}
