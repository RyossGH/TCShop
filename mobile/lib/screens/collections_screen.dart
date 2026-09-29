import 'package:flutter/material.dart';

import '../cards_api.dart';
import '../store.dart';
import '../widgets.dart';
import 'card_search.dart';

const _grey = ColorFilter.matrix(<double>[
  0.2126, 0.7152, 0.0722, 0, 0, //
  0.2126, 0.7152, 0.0722, 0, 0, //
  0.2126, 0.7152, 0.0722, 0, 0, //
  0, 0, 0, 1, 0,
]);

/// Collections : suivi de complétion (master sets, classeurs clients…), comme sur le PC.
class CollectionsScreen extends StatelessWidget {
  const CollectionsScreen({super.key});

  Future<void> _new(BuildContext context) async {
    final choice = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: panel,
      builder: (ctx) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          ListTile(
            leading: const Icon(Icons.download),
            title: const Text('Importer une extension complète'),
            subtitle: const Text('Toutes les cartes, raretés et prix (préparé par le PC à la synchro)'),
            onTap: () => Navigator.pop(ctx, 'import'),
          ),
          ListTile(
            leading: const Icon(Icons.create_new_folder_outlined),
            title: const Text('Collection vide'),
            subtitle: const Text('Vous ajoutez les cartes une par une'),
            onTap: () => Navigator.pop(ctx, 'empty'),
          ),
        ]),
      ),
    );
    if (!context.mounted || choice == null) return;
    if (choice == 'empty') {
      final r = await _askNameAndGame(context);
      if (r == null) return;
      await store.addOp('collection_create', {'name': r.name, 'game': r.game}, label: 'Collection ${r.name}');
    } else {
      await Navigator.push(context, MaterialPageRoute(builder: (_) => const SetImportScreen()));
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final cols = store.collections;
        return Scaffold(
          appBar: AppBar(title: const Text('Collections')),
          body: cols.isEmpty
              ? const Center(
                  child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text('Aucune collection.\nImportez une extension ou créez une collection vide.',
                      textAlign: TextAlign.center, style: TextStyle(color: muted)),
                ))
              : ListView.builder(
                  padding: const EdgeInsets.only(bottom: 90),
                  itemCount: cols.length,
                  itemBuilder: (_, i) {
                    final c = cols[i];
                    final cards = store.cardsOf(c);
                    final owned = cards.where((x) => numOf(x['owned']) > 0).length;
                    final pct = cards.isEmpty ? 0.0 : owned / cards.length;
                    return Card(
                      color: panel,
                      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      child: ListTile(
                        onTap: () => Navigator.push(context,
                            MaterialPageRoute(builder: (_) => CollectionDetail(collection: c))),
                        title: Text('${c['name']}', style: const TextStyle(fontWeight: FontWeight.bold)),
                        subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('${c['game']} · $owned / ${cards.length} cartes'
                              '${c['local'] == true ? ' · ${c['description']}' : ''}',
                              style: const TextStyle(color: muted)),
                          const SizedBox(height: 6),
                          LinearProgressIndicator(value: pct, minHeight: 6, borderRadius: BorderRadius.circular(4)),
                        ]),
                        trailing: Text('${(pct * 100).round()} %', style: const TextStyle(fontWeight: FontWeight.bold)),
                      ),
                    );
                  },
                ),
          floatingActionButton: FloatingActionButton.extended(
            onPressed: () => _new(context),
            icon: const Icon(Icons.add),
            label: const Text('Nouvelle collection'),
          ),
        );
      },
    );
  }
}

Future<({String name, String game})?> _askNameAndGame(BuildContext context) async {
  final name = TextEditingController();
  var game = onlineGames.first;
  return showDialog<({String name, String game})>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setState) => AlertDialog(
        title: const Text('Nouvelle collection'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: name, autofocus: true, decoration: const InputDecoration(labelText: 'Nom')),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            initialValue: game,
            decoration: const InputDecoration(labelText: 'Jeu'),
            items: [for (final g in [...onlineGames, 'Autre']) DropdownMenuItem(value: g, child: Text(g))],
            onChanged: (v) => setState(() => game = v ?? game),
          ),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Annuler')),
          FilledButton(
            onPressed: () => name.text.trim().isEmpty ? null : Navigator.pop(ctx, (name: name.text.trim(), game: game)),
            child: const Text('Créer'),
          ),
        ],
      ),
    ),
  );
}

// ====================================================================== import d'une extension
class SetImportScreen extends StatefulWidget {
  const SetImportScreen({super.key});

  @override
  State<SetImportScreen> createState() => _SetImportScreenState();
}

class _SetImportScreenState extends State<SetImportScreen> {
  String game = onlineGames.first;
  List<({String code, String name, String date})> sets = [];
  String filter = '';
  bool loading = false;
  String? error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      loading = true;
      error = null;
      sets = [];
    });
    try {
      sets = await CardsApi.sets(game);
    } catch (e) {
      error = "Liste des extensions indisponible : pas de connexion Internet ?";
    }
    if (mounted) setState(() => loading = false);
  }

  Future<void> _pick(({String code, String name, String date}) s) async {
    final ok = await confirm(context, 'Importer « ${s.name} » ?',
        "La collection apparaît tout de suite ; ses cartes (avec prix et raretés) sont téléchargées par le PC "
        "à la prochaine synchro.", ok: 'Importer');
    if (!ok) return;
    await store.addOp('collection_import_set', {'game': game, 'code': s.code, 'name': s.name},
        label: 'Import ${s.name}');
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final f = filter.toLowerCase();
    final rows = sets.where((s) => f.isEmpty || s.name.toLowerCase().contains(f) || s.code.toLowerCase().contains(f)).toList();
    return Scaffold(
      appBar: AppBar(title: const Text('Importer une extension')),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 4),
          child: DropdownButtonFormField<String>(
            initialValue: game,
            decoration: const InputDecoration(labelText: 'Jeu', isDense: true),
            items: [for (final g in onlineGames) DropdownMenuItem(value: g, child: Text(g))],
            onChanged: (v) {
              game = v ?? game;
              _load();
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
          child: TextField(
            decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Filtrer les extensions…'),
            onChanged: (v) => setState(() => filter = v),
          ),
        ),
        if (loading) const LinearProgressIndicator(),
        if (error != null) Padding(padding: const EdgeInsets.all(20), child: Text(error!, style: const TextStyle(color: warning))),
        Expanded(
          child: ListView.builder(
            itemCount: rows.length,
            itemBuilder: (_, i) => ListTile(
              title: Text(rows[i].name),
              subtitle: Text([rows[i].code, if (rows[i].date.length >= 4) rows[i].date.substring(0, 4)].join(' · '),
                  style: const TextStyle(color: muted)),
              onTap: () => _pick(rows[i]),
            ),
          ),
        ),
      ]),
    );
  }
}

// ====================================================================== détail d'une collection
class CollectionDetail extends StatefulWidget {
  const CollectionDetail({super.key, required this.collection});
  final Json collection;

  @override
  State<CollectionDetail> createState() => _CollectionDetailState();
}

class _CollectionDetailState extends State<CollectionDetail> {
  int filter = 0; // 0 toutes, 1 possédées, 2 manquantes
  String q = '';

  Json get col => store.findCollection(widget.collection) ?? widget.collection;

  Future<void> _change(Json card, int delta) async {
    if (delta < 0 && numOf(card['owned']) <= 0) return;
    final data = <String, dynamic>{'delta': delta};
    if (card['id'] != null) {
      data['card_id'] = card['id'];
    } else {
      data['card_uuid'] = card['uuid'];
    }
    await store.addOp('collection_owned', data, label: '${card['name']} ${delta > 0 ? '+' : ''}$delta');
  }

  Future<void> _addCard() async {
    final c = await pickOnlineCard(context, game: '${col['game']}');
    if (c == null) return;
    final data = <String, dynamic>{
      for (final k in ['name', 'set_name', 'number', 'rarity', 'image_url', 'external_id', 'market_price']) k: c[k],
      'owned': 1,
    };
    if (col['id'] != null) {
      data['collection_id'] = col['id'];
    } else {
      data['collection_uuid'] = col['uuid'];
    }
    await store.addOp('collection_add_card', data, label: 'Ajout ${c['name']} à ${col['name']}');
    if (mounted) toast(context, '${c['name']} ajoutée (1 exemplaire)');
  }

  void _details(Json card) {
    showModalBottomSheet(
      context: context,
      backgroundColor: panel,
      builder: (ctx) => ListenableBuilder(
        listenable: store,
        builder: (ctx, _) {
          final c = store.cardsOf(col).firstWhere((x) => StoreKey.same(x, card), orElse: () => card);
          return SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                ProductImage(c, size: 110),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('${c['name']}', style: Theme.of(ctx).textTheme.titleLarge),
                    Text('${c['set_name']} · #${c['number']}\n${c['rarity']}', style: const TextStyle(color: muted)),
                    const SizedBox(height: 6),
                    Text('Prix marché ${money(numOf(c['market_price']))}'),
                    const SizedBox(height: 10),
                    Row(children: [
                      IconButton.filledTonal(onPressed: () => _change(c, -1), icon: const Icon(Icons.remove)),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 14),
                        child: Text('${c['owned']}', style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold)),
                      ),
                      IconButton.filled(onPressed: () => _change(c, 1), icon: const Icon(Icons.add)),
                    ]),
                    const Text('exemplaire(s) possédé(s)', style: TextStyle(color: muted, fontSize: 12)),
                  ]),
                ),
              ]),
            ),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final all = store.cardsOf(col);
        final owned = all.where((c) => numOf(c['owned']) > 0).toList();
        final vOwned = owned.fold<num>(0, (s, c) => s + numOf(c['market_price']));
        final vMissing = all.where((c) => numOf(c['owned']) <= 0).fold<num>(0, (s, c) => s + numOf(c['market_price']));
        final w = q.toLowerCase();
        final cards = all.where((c) {
          final has = numOf(c['owned']) > 0;
          if ((filter == 1 && !has) || (filter == 2 && has)) return false;
          return w.isEmpty || '${c['name']} ${c['number']}'.toLowerCase().contains(w);
        }).toList();
        return Scaffold(
          appBar: AppBar(
            title: Text('${col['name']}'),
            actions: [IconButton(onPressed: _addCard, icon: const Icon(Icons.add_card), tooltip: 'Ajouter une carte')],
          ),
          body: Column(children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                LinearProgressIndicator(value: all.isEmpty ? 0 : owned.length / all.length, minHeight: 8,
                    borderRadius: BorderRadius.circular(4)),
                const SizedBox(height: 6),
                Text('${owned.length} / ${all.length} cartes · possédé ${money(vOwned)} · il manque ≈ ${money(vMissing)}',
                    style: const TextStyle(color: muted, fontSize: 13)),
                if (col['local'] == true && all.isEmpty)
                  Text('${col['description']}', style: const TextStyle(color: warning, fontSize: 13)),
              ]),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Row(children: [
                Expanded(
                  child: TextField(
                    decoration: const InputDecoration(isDense: true, prefixIcon: Icon(Icons.search), hintText: 'Nom ou n°'),
                    onChanged: (v) => setState(() => q = v),
                  ),
                ),
                const SizedBox(width: 8),
                SegmentedButton<int>(
                  showSelectedIcon: false,
                  segments: const [
                    ButtonSegment(value: 0, label: Text('Tout')),
                    ButtonSegment(value: 1, label: Text('Eues')),
                    ButtonSegment(value: 2, label: Text('Manq.')),
                  ],
                  selected: {filter},
                  onSelectionChanged: (s) => setState(() => filter = s.first),
                ),
              ]),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: GridView.builder(
                padding: const EdgeInsets.fromLTRB(10, 0, 10, 20),
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 3, childAspectRatio: 0.58, mainAxisSpacing: 8, crossAxisSpacing: 8),
                itemCount: cards.length,
                itemBuilder: (_, i) {
                  final c = cards[i];
                  final n = numOf(c['owned']).toInt();
                  Widget img = LayoutBuilder(builder: (_, box) => ProductImage(c, size: box.maxWidth));
                  if (n <= 0) img = Opacity(opacity: 0.4, child: ColorFiltered(colorFilter: _grey, child: img));
                  return InkWell(
                    onTap: () => _change(c, 1),
                    onLongPress: () => _details(c),
                    borderRadius: BorderRadius.circular(8),
                    child: Column(children: [
                      Expanded(
                        child: Stack(children: [
                          Positioned.fill(child: img),
                          if (n > 0)
                            Positioned(
                              right: 2,
                              top: 2,
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                                decoration: BoxDecoration(color: success, borderRadius: BorderRadius.circular(10)),
                                child: Text('×$n', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                              ),
                            ),
                        ]),
                      ),
                      Text('#${c['number']} ${c['name']}', maxLines: 1, overflow: TextOverflow.ellipsis,
                          style: TextStyle(fontSize: 11, color: n > 0 ? Colors.white : muted)),
                    ]),
                  );
                },
              ),
            ),
            const Padding(
              padding: EdgeInsets.only(bottom: 8),
              child: Text('Toucher : +1 exemplaire · Appui long : détails / −1', style: TextStyle(color: muted, fontSize: 12)),
            ),
          ]),
        );
      },
    );
  }
}

/// Compare deux objets (carte, collection) qu'ils aient un id PC ou seulement un uuid local.
class StoreKey {
  static bool same(Json a, Json b) =>
      (a['id'] != null && a['id'] == b['id']) || (a['uuid'] != null && a['uuid'] == b['uuid']);
}
