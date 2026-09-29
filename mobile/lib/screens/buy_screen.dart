import 'package:flutter/material.dart';

import '../store.dart';
import '../widgets.dart';
import 'card_search.dart';

const conditions = ['MT', 'NM', 'EX', 'GD', 'LP', 'PL', 'PO', 'Scellé'];
const conditionFactors = {'MT': 1.0, 'NM': 1.0, 'EX': 0.85, 'GD': 0.70, 'LP': 0.60, 'PL': 0.45, 'PO': 0.30, 'Scellé': 1.0};
const idTypes = ["Carte d'identité", 'Passeport', 'Permis de conduire', 'Titre de séjour'];

/// Rachat en convention : vendeur + pièce d'identité (livre de police), état, offre calculée selon vos taux.
class BuyScreen extends StatefulWidget {
  const BuyScreen({super.key});

  @override
  State<BuyScreen> createState() => _BuyScreenState();
}

class _BuyScreenState extends State<BuyScreen> {
  Json? customer; // client existant
  Json? newCustomer; // nouveau vendeur saisi sur le téléphone
  String payout = 'Espèces';
  final lines = <Json>[];
  bool certified = false;

  double get rate => payout == 'Crédit boutique' ? store.buyRateCredit : store.buyRateCash;
  num get total => lines.fold<num>(0, (s, l) => s + numOf(l['qty']) * numOf(l['offer_price']));
  num get marketTotal => lines.fold<num>(0, (s, l) => s + numOf(l['qty']) * numOf(l['market_price']));
  String get sellerName => '${customer?['name'] ?? newCustomer?['name'] ?? ''}';
  bool get hasId => customer?['has_id'] == 1 || customer?['has_id'] == true ||
      '${newCustomer?['id_number'] ?? ''}'.isNotEmpty;

  double _offer(Json l) =>
      (numOf(l['market_price']) * rate / 100 * (conditionFactors[l['condition']] ?? 1.0) * 100).round() / 100;

  void _recalc() {
    for (final l in lines) {
      if (l['manual'] != true) l['offer_price'] = _offer(l);
    }
  }

  void _addLine(Json l) {
    l['qty'] ??= 1;
    l['condition'] ??= 'NM';
    l['offer_price'] = _offer(l);
    setState(() => lines.add(l));
  }

  void _fromProduct(Json p) => _addLine({
        'product_id': p['id'], 'name': p['name'], 'game': p['game'], 'set_name': p['set_name'],
        'condition': conditions.contains(p['condition']) ? p['condition'] : 'NM',
        'market_price': numOf(p['market_price']) > 0 ? numOf(p['market_price']) : numOf(p['price']),
      });

  // ---------------------------------------------------------------- ajout de lignes
  Future<void> _scan() async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => ScannerPage(
      title: 'Rachat : scanner',
      onCode: (code) {
        final p = store.findByCode(code);
        if (p == null) return 'Code inconnu : $code (utilisez la base en ligne)';
        _fromProduct(p);
        return 'OK : ${p['name']}';
      },
    )));
    setState(() {});
  }

  Future<void> _fromStock() async {
    final p = await pickProduct(context);
    if (p != null) _fromProduct(p);
  }

  Future<void> _fromOnline() async {
    final c = await pickOnlineCard(context);
    if (c == null) return;
    // même carte déjà en stock (même id de base, état NM) : on incrémente la fiche existante
    final existing = store.products.where((p) =>
        '${p['external_id'] ?? ''}'.isNotEmpty && p['external_id'] == c['external_id'] && p['condition'] == 'NM').toList();
    if (existing.isNotEmpty) {
      _fromProduct(existing.first);
      return;
    }
    _addLine({
      'product_id': null, 'category': 'Carte',
      for (final k in ['name', 'game', 'set_name', 'set_code', 'number', 'rarity', 'image_url', 'external_id', 'language',
        'market_price']) k: c[k],
    });
  }

  Future<void> _manual() async {
    final name = await askText(context, 'Article racheté', hint: 'Ex. lot de 100 cartes communes');
    if (name == null || name.isEmpty || !mounted) return;
    final market = await askNumber(context, 'Valeur marché (unité)', decimal: true, suffix: '€');
    if (market == null) return;
    _addLine({'product_id': null, 'name': name, 'category': 'Lot', 'market_price': market});
  }

  // ---------------------------------------------------------------- vendeur
  Future<void> _pickCustomer() async {
    final c = await showModalBottomSheet<Json>(
      context: context,
      isScrollControlled: true,
      backgroundColor: panel,
      builder: (_) => const FractionallySizedBox(heightFactor: 0.85, child: _CustomerPicker()),
    );
    if (c != null) {
      setState(() {
        customer = c;
        newCustomer = null;
        certified = false;
      });
    }
  }

  Future<void> _newCustomer() async {
    final r = await showDialog<Json>(context: context, builder: (_) => _SellerDialog(initial: newCustomer));
    if (r != null) {
      setState(() {
        newCustomer = r;
        customer = null;
        certified = false;
      });
    }
  }

  // ---------------------------------------------------------------- validation
  Future<void> _validate() async {
    if (lines.isEmpty) return;
    if (payout == 'Crédit boutique' && sellerName.isEmpty) {
      toast(context, 'Choisissez le vendeur pour lui verser du crédit boutique.', error: true);
      return;
    }
    if (!hasId && !await confirm(context, "Pièce d'identité manquante",
        "Le livre de police exige l'identité du vendeur. Enregistrer quand même ce rachat ?", ok: 'Continuer')) {
      return;
    }
    if (!mounted) return;
    final ok = await confirm(context, 'Verser ${money(total)} ?',
        '${lines.length} ligne(s) · $payout · vendeur : ${sellerName.isEmpty ? 'non renseigné' : sellerName}',
        ok: 'Valider le rachat');
    if (!ok) return;
    final data = <String, dynamic>{
      'payout': payout,
      'lines': lines.map((l) => Map<String, dynamic>.of(l)..remove('manual')).toList(),
      if (customer != null) 'customer_id': customer!['id'],
      if (newCustomer != null) 'customer': newCustomer,
    };
    final t = total;
    await store.addOp('buy', data, label: 'Rachat ${money(t)} ($payout)${sellerName.isEmpty ? '' : ' · $sellerName'}');
    setState(() {
      lines.clear();
      customer = null;
      newCustomer = null;
      certified = false;
    });
    if (mounted) toast(context, 'Rachat enregistré : ${money(t)} — $payout');
  }

  void _history() {
    final today = nowStr().substring(0, 10);
    final buys = store.history.where((h) => h['type'] == 'buy' && '${h['date']}'.startsWith(today)).toList();
    showModalBottomSheet(
      context: context,
      backgroundColor: panel,
      builder: (_) => ListView(shrinkWrap: true, children: [
        ListTile(title: Text("Rachats d'aujourd'hui sur ce téléphone (${buys.length})")),
        for (final h in buys)
          ListTile(
            dense: true,
            leading: Icon(h['state'] == 'ok' ? Icons.cloud_done : Icons.cloud_upload,
                color: h['state'] == 'ok' ? success : warning),
            title: Text('${h['label']}'),
            subtitle: Text(shortDate(h['date'] as String?)),
          ),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) => Scaffold(
        appBar: AppBar(title: const Text('Rachat'), actions: [
          IconButton(onPressed: _history, icon: const Icon(Icons.receipt_long), tooltip: 'Rachats du jour'),
        ]),
        body: Column(children: [
          Expanded(
            child: ListView(padding: const EdgeInsets.fromLTRB(12, 0, 12, 12), children: [
              // vendeur
              Card(
                color: panel,
                child: ListTile(
                  leading: Icon(Icons.person, color: sellerName.isEmpty ? muted : accent),
                  title: Text(sellerName.isEmpty ? 'Vendeur non renseigné' : sellerName),
                  subtitle: Text(
                      sellerName.isEmpty
                          ? "Obligatoire pour le livre de police"
                          : (hasId ? "Pièce d'identité enregistrée" : "Pièce d'identité manquante"),
                      style: TextStyle(color: sellerName.isNotEmpty && hasId ? success : warning, fontSize: 12)),
                  trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                    IconButton(onPressed: _pickCustomer, icon: const Icon(Icons.search), tooltip: 'Client existant'),
                    IconButton(onPressed: _newCustomer, icon: const Icon(Icons.person_add), tooltip: 'Nouveau vendeur'),
                  ]),
                ),
              ),
              if (customer != null && !hasId)
                TextButton.icon(
                  onPressed: () async {
                    final r = await showDialog<Json>(context: context,
                        builder: (_) => _SellerDialog(initial: {'name': customer!['name'], 'phone': customer!['phone']},
                            idOnly: true));
                    if (r != null) setState(() => newCustomer = r);
                  },
                  icon: const Icon(Icons.badge_outlined),
                  label: const Text("Ajouter sa pièce d'identité"),
                ),
              const SizedBox(height: 6),
              // règlement
              Wrap(spacing: 8, runSpacing: 4, children: [
                for (final p in store.payouts)
                  ChoiceChip(
                    label: Text(p),
                    selected: payout == p,
                    onSelected: (_) => setState(() {
                      payout = p;
                      _recalc();
                    }),
                  ),
              ]),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Text('Offre = prix marché × ${rate.toStringAsFixed(0)} % × état (NM 100 %, EX 85 %, GD 70 %, '
                    'LP 60 %, PL 45 %, PO 30 %)', style: const TextStyle(color: muted, fontSize: 12)),
              ),
              // ajout
              Row(children: [
                Expanded(child: FilledButton.tonalIcon(onPressed: _scan, icon: const Icon(Icons.qr_code_scanner),
                    label: const Text('Scanner'))),
                const SizedBox(width: 6),
                Expanded(child: FilledButton.tonalIcon(onPressed: _fromOnline, icon: const Icon(Icons.travel_explore),
                    label: const Text('Base en ligne'))),
              ]),
              const SizedBox(height: 6),
              Row(children: [
                Expanded(child: OutlinedButton.icon(onPressed: _fromStock, icon: const Icon(Icons.inventory_2),
                    label: const Text('Du stock'))),
                const SizedBox(width: 6),
                Expanded(child: OutlinedButton.icon(onPressed: _manual, icon: const Icon(Icons.edit),
                    label: const Text('Manuel'))),
              ]),
              const SizedBox(height: 8),
              for (final l in lines) _LineCard(
                line: l,
                onChanged: () => setState(() {
                  if (l['manual'] != true) l['offer_price'] = _offer(l);
                }),
                onRemove: () => setState(() => lines.remove(l)),
              ),
              if (lines.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(24),
                  child: Text('Ajoutez les cartes proposées par le vendeur', textAlign: TextAlign.center,
                      style: TextStyle(color: muted)),
                ),
            ]),
          ),
          Container(
            color: panel,
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
            child: Column(children: [
              Row(children: [
                Text('Valeur marché ${money(marketTotal)}', style: const TextStyle(color: muted)),
                const Spacer(),
                Text(money(total), style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: accent)),
              ]),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                value: certified,
                onChanged: (v) => setState(() => certified = v ?? false),
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text('Le vendeur certifie être propriétaire des articles et les céder en l\'état',
                    style: TextStyle(fontSize: 12)),
              ),
              FilledButton(
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(50), backgroundColor: success,
                    foregroundColor: Colors.white),
                onPressed: lines.isEmpty || !certified ? null : _validate,
                child: Text('Valider le rachat · $payout', style: const TextStyle(fontWeight: FontWeight.bold)),
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}

class _LineCard extends StatelessWidget {
  const _LineCard({required this.line, required this.onChanged, required this.onRemove});
  final Json line;
  final VoidCallback onChanged;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final l = line;
    return Card(
      color: panel2,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 4, 8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
              child: Text('${l['name']}${l['product_id'] == null ? '  (nouvelle fiche)' : ''}',
                  style: const TextStyle(fontWeight: FontWeight.bold)),
            ),
            IconButton(onPressed: onRemove, icon: const Icon(Icons.close, size: 20)),
          ]),
          if ('${l['set_name'] ?? ''}'.isNotEmpty)
            Text('${l['set_name']}${'${l['number'] ?? ''}'.isNotEmpty ? ' · #${l['number']}' : ''}',
                style: const TextStyle(color: muted, fontSize: 12)),
          Row(children: [
            DropdownButton<String>(
              value: conditions.contains(l['condition']) ? l['condition'] as String : 'NM',
              items: [for (final c in conditions) DropdownMenuItem(value: c, child: Text(c))],
              onChanged: (v) {
                l['condition'] = v;
                onChanged();
              },
            ),
            IconButton(
                onPressed: numOf(l['qty']) > 1
                    ? () {
                        l['qty'] = numOf(l['qty']) - 1;
                        onChanged();
                      }
                    : null,
                icon: const Icon(Icons.remove_circle_outline)),
            Text('${l['qty']}', style: const TextStyle(fontWeight: FontWeight.bold)),
            IconButton(
                onPressed: () {
                  l['qty'] = numOf(l['qty']) + 1;
                  onChanged();
                },
                icon: const Icon(Icons.add_circle_outline)),
            const Spacer(),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              InkWell(
                onTap: () async {
                  final v = await askNumber(context, 'Prix marché (unité)', initial: numOf(l['market_price']),
                      decimal: true, suffix: '€');
                  if (v != null) {
                    l['market_price'] = v;
                    l['manual'] = false;
                    onChanged();
                  }
                },
                child: Text('marché ${money(numOf(l['market_price']))}', style: const TextStyle(color: muted, fontSize: 12)),
              ),
              InkWell(
                onTap: () async {
                  final v = await askNumber(context, 'Offre (unité)', initial: numOf(l['offer_price']),
                      decimal: true, suffix: '€');
                  if (v != null) {
                    l['offer_price'] = v;
                    l['manual'] = true;
                    onChanged();
                  }
                },
                child: Text('offre ${money(numOf(l['offer_price']))}',
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              ),
            ]),
            const SizedBox(width: 8),
          ]),
        ]),
      ),
    );
  }
}

class _CustomerPicker extends StatefulWidget {
  const _CustomerPicker();

  @override
  State<_CustomerPicker> createState() => _CustomerPickerState();
}

class _CustomerPickerState extends State<_CustomerPicker> {
  String q = '';

  @override
  Widget build(BuildContext context) {
    final w = q.toLowerCase();
    final rows = store.customers.where((c) => w.isEmpty || '${c['name']} ${c['phone']}'.toLowerCase().contains(w)).toList();
    return Column(children: [
      Padding(
        padding: const EdgeInsets.all(16),
        child: TextField(
          autofocus: true,
          decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Nom ou téléphone'),
          onChanged: (v) => setState(() => q = v),
        ),
      ),
      Expanded(
        child: ListView.builder(
          itemCount: rows.length,
          itemBuilder: (_, i) => ListTile(
            leading: const Icon(Icons.person),
            title: Text('${rows[i]['name']}'),
            subtitle: Text('${rows[i]['phone'] ?? ''}', style: const TextStyle(color: muted)),
            trailing: rows[i]['has_id'] == 1 || rows[i]['has_id'] == true
                ? const Icon(Icons.badge, color: success)
                : const Icon(Icons.badge_outlined, color: warning),
            onTap: () => Navigator.pop(context, rows[i]),
          ),
        ),
      ),
    ]);
  }
}

class _SellerDialog extends StatefulWidget {
  const _SellerDialog({this.initial, this.idOnly = false});
  final Json? initial;
  final bool idOnly;

  @override
  State<_SellerDialog> createState() => _SellerDialogState();
}

class _SellerDialogState extends State<_SellerDialog> {
  late final name = TextEditingController(text: '${widget.initial?['name'] ?? ''}');
  late final phone = TextEditingController(text: '${widget.initial?['phone'] ?? ''}');
  late final idNumber = TextEditingController(text: '${widget.initial?['id_number'] ?? ''}');
  late String idType = idTypes.contains(widget.initial?['id_type']) ? widget.initial!['id_type'] as String : idTypes.first;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.idOnly ? "Pièce d'identité" : 'Nouveau vendeur'),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (!widget.idOnly) ...[
            TextField(controller: name, autofocus: true, decoration: const InputDecoration(labelText: 'Nom complet *')),
            TextField(controller: phone, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'Téléphone')),
          ],
          DropdownButtonFormField<String>(
            initialValue: idType,
            decoration: const InputDecoration(labelText: "Pièce d'identité"),
            items: [for (final t in idTypes) DropdownMenuItem(value: t, child: Text(t))],
            onChanged: (v) => setState(() => idType = v ?? idType),
          ),
          TextField(controller: idNumber, decoration: const InputDecoration(labelText: 'Numéro de la pièce')),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
        FilledButton(
          onPressed: () {
            if (!widget.idOnly && name.text.trim().isEmpty) return;
            Navigator.pop(context, <String, dynamic>{
              'name': name.text.trim(), 'phone': phone.text.trim(), 'id_type': idType, 'id_number': idNumber.text.trim(),
            });
          },
          child: const Text('OK'),
        ),
      ],
    );
  }
}
