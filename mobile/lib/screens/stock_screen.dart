import 'package:flutter/material.dart';

import '../store.dart';
import '../widgets.dart';

/// Stock : recherche, fiche article, réception / sortie / comptage (inventaire).
class StockScreen extends StatefulWidget {
  const StockScreen({super.key});

  @override
  State<StockScreen> createState() => _StockScreenState();
}

class _StockScreenState extends State<StockScreen> {
  String q = '';

  Future<void> _scan() async {
    final code = await ScannerPage.scanOnce(context, title: 'Scanner un article');
    if (code == null || !mounted) return;
    final p = store.findByCode(code);
    if (p == null) {
      toast(context, 'Code inconnu : $code — associez-le à un article depuis TCShop sur le PC.', error: true);
      return;
    }
    await showProductSheet(context, p);
  }

  Future<void> _countMode() async {
    final counts = <int, int>{};
    await Navigator.push(context, MaterialPageRoute(builder: (_) => ScannerPage(
      title: 'Comptage d\'inventaire',
      onCode: (code) {
        final p = store.findByCode(code);
        if (p == null) return 'Code inconnu : $code';
        final id = numOf(p['id']).toInt();
        counts[id] = (counts[id] ?? 0) + 1;
        return '${p['name']} : ${counts[id]} compté(s)';
      },
    )));
    if (counts.isEmpty || !mounted) return;
    final diffs = <int, int>{};
    for (final e in counts.entries) {
      final p = store.productById(e.key);
      if (p == null || p['track_stock'] == 0) continue;
      final d = e.value - numOf(p['quantity']).toInt();
      if (d != 0) diffs[e.key] = d;
    }
    if (diffs.isEmpty) {
      toast(context, 'Aucun écart : le stock correspond au comptage');
      return;
    }
    final lines = diffs.entries.map((e) => '• ${store.productById(e.key)!['name']} : ${e.value > 0 ? '+' : ''}${e.value}').join('\n');
    final ok = await confirm(context, 'Appliquer l\'inventaire ?', '${diffs.length} écart(s) :\n$lines', ok: 'Corriger le stock');
    if (!ok) return;
    for (final e in diffs.entries) {
      await store.addOp('stock', {'product_id': e.key, 'delta': e.value, 'reason': 'count'},
          label: 'Inventaire ${store.productById(e.key)!['name']} ${e.value > 0 ? '+' : ''}${e.value}');
    }
    if (mounted) toast(context, 'Stock corrigé pour ${diffs.length} article(s)');
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final rows = store.search(q);
        return Scaffold(
          appBar: AppBar(title: const Text('Stock'), actions: [
            IconButton(onPressed: _countMode, icon: const Icon(Icons.fact_check), tooltip: 'Comptage d\'inventaire'),
          ]),
          body: Column(children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
              child: Row(children: [
                Expanded(
                  child: TextField(
                    decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Rechercher un article…'),
                    onChanged: (v) => setState(() => q = v),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filled(onPressed: _scan, icon: const Icon(Icons.qr_code_scanner), iconSize: 28),
              ]),
            ),
            Expanded(
              child: rows.isEmpty
                  ? const Center(child: Text('Aucun article.\nSynchronisez avec le PC pour récupérer le catalogue.',
                      textAlign: TextAlign.center, style: TextStyle(color: muted)))
                  : ListView.builder(
                      itemCount: rows.length,
                      itemBuilder: (_, i) => ProductTile(rows[i], onTap: () => showProductSheet(context, rows[i])),
                    ),
            ),
          ]),
        );
      },
    );
  }
}

Future<void> showProductSheet(BuildContext context, Json p0) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: panel,
    builder: (ctx) => ListenableBuilder(
      listenable: store,
      builder: (ctx, _) {
        final p = store.productById(p0['id']) ?? p0; // relu à chaque synchro
        final details = [
          p['category'], p['brand'], p['variant'], p['game'], p['set_name'],
          if ('${p['number'] ?? ''}'.isNotEmpty) 'n° ${p['number']}',
          if (p['category'] == 'Carte') '${p['condition']} · ${p['language']}',
        ].where((e) => '${e ?? ''}'.trim().isNotEmpty).join(' · ');
        final tracked = p['track_stock'] != 0;
        Future<void> move(String reason, String title, int sign) async {
          final n = await askNumber(ctx, title, initial: reason == 'count' ? numOf(p['quantity']) : 1);
          if (n == null || n == 0) return;
          final delta = reason == 'count' ? n.toInt() - numOf(p['quantity']).toInt() : sign * n.toInt();
          if (delta == 0) return;
          await store.addOp('stock', {'product_id': p['id'], 'delta': delta, 'reason': reason},
              label: '$title ${p['name']} ${delta > 0 ? '+' : ''}$delta');
          if (ctx.mounted) toast(ctx, 'Stock de « ${p['name']} » : ${p['quantity']}');
        }

        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                ProductImage(p, size: 90),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('${p['name']}', style: Theme.of(ctx).textTheme.titleLarge),
                    const SizedBox(height: 4),
                    Text(details, style: const TextStyle(color: muted)),
                    const SizedBox(height: 8),
                    Text(money(numOf(p['price'])),
                        style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: accent)),
                    if (numOf(p['market_price']) > 0)
                      Text('Prix marché ${money(numOf(p['market_price']))}', style: const TextStyle(color: muted)),
                  ]),
                ),
              ]),
              const SizedBox(height: 14),
              Row(children: [
                const Icon(Icons.inventory_2_outlined, color: muted, size: 18),
                const SizedBox(width: 6),
                Text(tracked ? 'Stock : ${p['quantity']}' : 'Prestation sans stock',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                const Spacer(),
                const Icon(Icons.place_outlined, color: muted, size: 18),
                Text(' ${'${p['location'] ?? ''}'.isEmpty ? '—' : p['location']}'),
              ]),
              Text('SKU ${p['sku']}${'${p['barcode'] ?? ''}'.isNotEmpty ? ' · EAN ${p['barcode']}' : ''}',
                  style: const TextStyle(color: muted, fontSize: 12)),
              if (tracked) ...[
                const SizedBox(height: 16),
                Row(children: [
                  Expanded(child: FilledButton.tonalIcon(onPressed: () => move('reception', 'Réception', 1),
                      icon: const Icon(Icons.add), label: const Text('Réception'))),
                  const SizedBox(width: 8),
                  Expanded(child: FilledButton.tonalIcon(onPressed: () => move('out', 'Sortie', -1),
                      icon: const Icon(Icons.remove), label: const Text('Sortie'))),
                  const SizedBox(width: 8),
                  Expanded(child: FilledButton.tonalIcon(onPressed: () => move('count', 'Compter', 1),
                      icon: const Icon(Icons.fact_check), label: const Text('Compter'))),
                ]),
              ],
            ]),
          ),
        );
      },
    ),
  );
}
