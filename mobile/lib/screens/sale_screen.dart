import 'package:flutter/material.dart';

import '../store.dart';
import '../widgets.dart';

/// Caisse mobile (conventions, salons…) : panier, puis espèces / virement / Wero.
class SaleScreen extends StatefulWidget {
  const SaleScreen({super.key});

  @override
  State<SaleScreen> createState() => _SaleScreenState();
}

class _SaleScreenState extends State<SaleScreen> {
  final List<Json> cart = [];

  num get total => cart.fold<num>(0, (s, l) => s + numOf(l['qty']) * numOf(l['unit_price']));
  int get count => cart.fold<int>(0, (s, l) => s + numOf(l['qty']).toInt());

  void _add(Json p) {
    setState(() {
      final existing = cart.where((l) => l['product_id'] == p['id']).toList();
      if (existing.isNotEmpty) {
        existing.first['qty'] = numOf(existing.first['qty']) + 1;
      } else {
        cart.add({'product_id': p['id'], 'name': AppStore.productLabel(p), 'qty': 1, 'unit_price': numOf(p['price'])});
      }
    });
  }

  String? _scanned(String code) {
    final p = store.findByCode(code);
    if (p == null) return 'Code inconnu : $code';
    _add(p);
    return 'OK : ${p['name']} — ${money(numOf(p['price']))}';
  }

  Future<void> _scan() async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => ScannerPage(title: 'Ajouter au panier', onCode: _scanned)));
    setState(() {});
  }

  Future<void> _search() async {
    final p = await pickProduct(context, inStockOnly: true);
    if (p != null) _add(p);
  }

  Future<void> _free() async {
    final name = await askText(context, 'Article libre', hint: 'Ex. lot de cartes, service…');
    if (name == null || name.isEmpty || !mounted) return;
    final price = await askNumber(context, 'Prix', decimal: true, suffix: '€');
    if (price == null) return;
    setState(() => cart.add({'product_id': null, 'name': name, 'qty': 1, 'unit_price': price}));
  }

  Future<void> _editLine(Json l) async {
    final price = await askNumber(context, 'Prix unitaire', initial: numOf(l['unit_price']), decimal: true, suffix: '€');
    if (price != null) setState(() => l['unit_price'] = price);
  }

  Future<void> _pay(String method) async {
    if (cart.isEmpty) return;
    final t = total;
    num? given;
    if (method == 'Espèces') {
      given = await askNumber(context, 'Espèces reçues', decimal: true, suffix: '€', hint: 'Laisser vide si compte exact');
    }
    if (!mounted) return;
    final change = given != null && given > t ? given - t : 0;
    final ok = await confirm(context, 'Encaisser ${money(t)}',
        '$count article(s) · paiement : $method${change > 0 ? '\n\nÀ rendre : ${money(change)}' : ''}',
        ok: 'Valider la vente');
    if (!ok) return;
    await store.addOp('sale', {'payment': method, 'lines': cart.map((l) => Map<String, dynamic>.of(l)).toList()},
        label: 'Vente ${money(t)} ($method)');
    setState(cart.clear);
    if (mounted) toast(context, 'Vente enregistrée : ${money(t)} — $method');
  }

  void _history() {
    final today = nowStr().substring(0, 10);
    final sales = store.history.where((h) => h['type'] == 'sale' && '${h['date']}'.startsWith(today)).toList();
    final sum = sales.fold<num>(0, (s, h) {
      final lines = ((h['data'] as Map)['lines'] as List).cast<Map>();
      return s + lines.fold<num>(0, (a, l) => a + numOf(l['qty']) * numOf(l['unit_price']));
    });
    showModalBottomSheet(
      context: context,
      backgroundColor: panel,
      builder: (_) => Column(mainAxisSize: MainAxisSize.min, children: [
        ListTile(
          title: Text("Ventes d'aujourd'hui sur ce téléphone", style: Theme.of(context).textTheme.titleMedium),
          subtitle: Text('${sales.length} vente(s) · ${money(sum)}'),
        ),
        Flexible(
          child: ListView(shrinkWrap: true, children: [
            for (final h in sales)
              ListTile(
                dense: true,
                leading: Icon(h['state'] == 'ok' ? Icons.cloud_done : Icons.cloud_upload,
                    color: h['state'] == 'ok' ? success : warning),
                title: Text('${h['label']}'),
                subtitle: Text(shortDate(h['date'] as String?)),
              ),
          ]),
        ),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Caisse'),
        actions: [IconButton(onPressed: _history, icon: const Icon(Icons.receipt_long), tooltip: 'Ventes du jour')],
      ),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
          child: Row(children: [
            Expanded(
              child: FilledButton.icon(
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                onPressed: _scan,
                icon: const Icon(Icons.qr_code_scanner),
                label: const Text('Scanner'),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.outlined(onPressed: _search, icon: const Icon(Icons.search), tooltip: 'Chercher un article',
                iconSize: 26),
            const SizedBox(width: 4),
            IconButton.outlined(onPressed: _free, icon: const Icon(Icons.add), tooltip: 'Article libre', iconSize: 26),
          ]),
        ),
        Expanded(
          child: cart.isEmpty
              ? const Center(
                  child: Text('Panier vide\nScannez ou cherchez un article', textAlign: TextAlign.center,
                      style: TextStyle(color: muted)))
              : ListView.separated(
                  itemCount: cart.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) {
                    final l = cart[i];
                    return Dismissible(
                      key: ObjectKey(l),
                      direction: DismissDirection.endToStart,
                      background: Container(color: danger, alignment: Alignment.centerRight,
                          padding: const EdgeInsets.only(right: 20), child: const Icon(Icons.delete)),
                      onDismissed: (_) => setState(() => cart.remove(l)),
                      child: ListTile(
                        title: Text('${l['name']}', maxLines: 2, overflow: TextOverflow.ellipsis),
                        subtitle: Text('${money(numOf(l['unit_price']))} · toucher pour changer le prix',
                            style: const TextStyle(color: muted, fontSize: 12)),
                        onTap: () => _editLine(l),
                        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                          IconButton(
                            icon: const Icon(Icons.remove_circle_outline),
                            onPressed: () => setState(() {
                              if (numOf(l['qty']) <= 1) {
                                cart.remove(l);
                              } else {
                                l['qty'] = numOf(l['qty']) - 1;
                              }
                            }),
                          ),
                          Text('${l['qty']}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                          IconButton(icon: const Icon(Icons.add_circle_outline),
                              onPressed: () => setState(() => l['qty'] = numOf(l['qty']) + 1)),
                        ]),
                      ),
                    );
                  },
                ),
        ),
        Container(
          color: panel,
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          child: Column(children: [
            Row(children: [
              Text('$count article(s)', style: const TextStyle(color: muted)),
              const Spacer(),
              Text(money(total), style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: accent)),
            ]),
            const SizedBox(height: 10),
            Row(children: [
              for (final m in store.payments) ...[
                Expanded(
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(54),
                      backgroundColor: m == 'Espèces' ? success : panel2,
                      foregroundColor: Colors.white,
                    ),
                    onPressed: cart.isEmpty ? null : () => _pay(m),
                    child: Text(m, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                  ),
                ),
                if (m != store.payments.last) const SizedBox(width: 8),
              ],
            ]),
          ]),
        ),
      ]),
    );
  }
}
