import 'package:flutter/material.dart';

import '../store.dart';
import '../widgets.dart';

/// Commandes en ligne (tous canaux) : création sur le téléphone + suivi (préparée, expédiée…).
class OrdersScreen extends StatefulWidget {
  const OrdersScreen({super.key});

  @override
  State<OrdersScreen> createState() => _OrdersScreenState();
}

class _OrdersScreenState extends State<OrdersScreen> {
  bool openOnly = true;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final list = store.orders.where((o) => !openOnly || nextStatus.containsKey(o['status'])).toList();
        return Scaffold(
          appBar: AppBar(title: const Text('Commandes en ligne')),
          body: Column(children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: true, label: Text('En cours')),
                  ButtonSegment(value: false, label: Text('Toutes (30 j)')),
                ],
                selected: {openOnly},
                onSelectionChanged: (s) => setState(() => openOnly = s.first),
              ),
            ),
            const SizedBox(height: 6),
            Expanded(
              child: list.isEmpty
                  ? const Center(child: Text('Aucune commande', style: TextStyle(color: muted)))
                  : ListView.builder(
                      padding: const EdgeInsets.only(bottom: 90),
                      itemCount: list.length,
                      itemBuilder: (_, i) {
                        final o = list[i];
                        return Card(
                          color: panel,
                          margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
                          child: ListTile(
                            onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => OrderDetail(order: o))),
                            title: Text('${o['customer_name'] == '' ? '—' : o['customer_name']} · ${o['channel']}'),
                            subtitle: Text(
                                '${o['local'] == true ? 'Pas encore synchronisée' : o['number']} · ${shortDate(o['date'] as String?)}'
                                '${'${o['external_ref'] ?? ''}'.isNotEmpty ? ' · réf. ${o['external_ref']}' : ''}',
                                style: const TextStyle(color: muted)),
                            trailing: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  Text(money(numOf(o['total'])), style: const TextStyle(fontWeight: FontWeight.bold)),
                                  Text('${o['status']}', style: TextStyle(color: statusColor(o['status'] as String?), fontSize: 12)),
                                ]),
                          ),
                        );
                      },
                    ),
            ),
          ]),
          floatingActionButton: FloatingActionButton.extended(
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const NewOrderScreen())),
            icon: const Icon(Icons.add),
            label: const Text('Nouvelle commande'),
          ),
        );
      },
    );
  }
}

// ====================================================================== détail
class OrderDetail extends StatelessWidget {
  const OrderDetail({super.key, required this.order});
  final Json order;

  Future<void> _setStatus(BuildContext context, Json o, String status) async {
    String? tracking;
    if (status == 'Expédiée') {
      final choice = await showDialog<String>(
        context: context,
        builder: (ctx) => SimpleDialog(title: const Text('Numéro de suivi'), children: [
          SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 'scan'), child: const Text('Scanner le code du colis')),
          SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 'type'), child: const Text('Saisir le numéro')),
          SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 'none'), child: const Text('Sans numéro de suivi')),
        ]),
      );
      if (choice == null || !context.mounted) return;
      if (choice == 'scan') tracking = await ScannerPage.scanOnce(context, title: 'Code du colis');
      if (choice == 'type' && context.mounted) tracking = await askText(context, 'Numéro de suivi');
    } else if (status == 'Annulée') {
      if (!await confirm(context, 'Annuler la commande ?', 'Les articles seront remis en stock sur le PC.')) return;
    }
    final data = <String, dynamic>{'status': status};
    if (o['id'] != null) {
      data['order_id'] = o['id'];
    } else {
      data['order_uuid'] = o['uuid'];
    }
    if (tracking != null && tracking.isNotEmpty) data['tracking'] = tracking;
    await store.addOp('order_status', data, label: 'Commande ${o['customer_name']} → $status');
    if (context.mounted) toast(context, 'Commande : $status');
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final o = store.orders.firstWhere(
            (x) => (order['id'] != null && x['id'] == order['id']) || (order['uuid'] != null && x['uuid'] == order['uuid']),
            orElse: () => order);
        final items = ((o['items'] as List?) ?? const []).cast<Map>();
        final nxt = nextStatus[o['status']];
        return Scaffold(
          appBar: AppBar(title: Text(o['local'] == true ? 'Nouvelle commande' : '${o['number']}')),
          body: ListView(padding: const EdgeInsets.all(16), children: [
            Row(children: [
              Chip(label: Text('${o['status']}'), backgroundColor: statusColor(o['status'] as String?).withValues(alpha: 0.2)),
              const SizedBox(width: 8),
              Chip(label: Text('${o['channel']}')),
            ]),
            const SizedBox(height: 8),
            Text('${o['customer_name']}', style: Theme.of(context).textTheme.titleLarge),
            if ('${o['address'] ?? ''}'.isNotEmpty) Text('${o['address']}', style: const TextStyle(color: muted)),
            if ('${o['external_ref'] ?? ''}'.isNotEmpty) Text('Réf. ${o['external_ref']}', style: const TextStyle(color: muted)),
            if ('${o['tracking'] ?? ''}'.isNotEmpty) Text('Suivi : ${o['tracking']}'),
            const Divider(height: 28),
            for (final it in items)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: Text('${it['name']}'),
                subtitle: Text('Empl. ${store.productById(it['product_id'])?['location'] ?? '—'}',
                    style: const TextStyle(color: muted)),
                trailing: Text('${it['qty']} × ${money(numOf(it['unit_price']))}'),
              ),
            const Divider(height: 28),
            Row(children: [
              Text('Port ${money(numOf(o['shipping']))}', style: const TextStyle(color: muted)),
              const Spacer(),
              Text(money(numOf(o['total'])), style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
            ]),
            const SizedBox(height: 24),
            if (nxt != null)
              FilledButton.icon(
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                onPressed: () => _setStatus(context, o, nxt),
                icon: const Icon(Icons.arrow_forward),
                label: Text('Marquer « $nxt »'),
              ),
            if (o['status'] != 'Annulée' && o['status'] != 'Livrée')
              TextButton(onPressed: () => _setStatus(context, o, 'Annulée'),
                  child: const Text('Annuler la commande', style: TextStyle(color: danger))),
          ]),
        );
      },
    );
  }
}

// ====================================================================== création
class NewOrderScreen extends StatefulWidget {
  const NewOrderScreen({super.key});

  @override
  State<NewOrderScreen> createState() => _NewOrderScreenState();
}

class _NewOrderScreenState extends State<NewOrderScreen> {
  final lines = <Json>[];
  late String channel = store.channels.first;
  final customer = TextEditingController();
  final ref = TextEditingController();
  final address = TextEditingController();
  final shipping = TextEditingController();

  num get itemsTotal => lines.fold<num>(0, (s, l) => s + numOf(l['qty']) * numOf(l['unit_price']));
  num get ship => num.tryParse(shipping.text.replaceAll(',', '.')) ?? 0;

  void _add(Json p) => setState(() {
        final ex = lines.where((l) => l['product_id'] == p['id']).toList();
        if (ex.isNotEmpty) {
          ex.first['qty'] = numOf(ex.first['qty']) + 1;
        } else {
          lines.add({'product_id': p['id'], 'name': AppStore.productLabel(p), 'qty': 1, 'unit_price': numOf(p['price'])});
        }
      });

  Future<void> _scan() async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => ScannerPage(
      title: 'Articles de la commande',
      onCode: (code) {
        final p = store.findByCode(code);
        if (p == null) return 'Code inconnu : $code';
        _add(p);
        return 'OK : ${p['name']}';
      },
    )));
    setState(() {});
  }

  Future<void> _save() async {
    if (lines.isEmpty) {
      toast(context, 'Ajoutez au moins un article', error: true);
      return;
    }
    await store.addOp('order', {
      'channel': channel, 'customer_name': customer.text.trim(), 'external_ref': ref.text.trim(),
      'address': address.text.trim(), 'shipping': ship, 'lines': lines,
    }, label: 'Commande $channel ${money(itemsTotal + ship)}');
    if (mounted) {
      toast(context, 'Commande enregistrée — stock réservé');
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Nouvelle commande')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        DropdownButtonFormField<String>(
          initialValue: channel,
          decoration: const InputDecoration(labelText: 'Canal de vente'),
          items: [for (final c in store.channels) DropdownMenuItem(value: c, child: Text(c))],
          onChanged: (v) => setState(() => channel = v ?? channel),
        ),
        TextField(controller: customer, decoration: const InputDecoration(labelText: 'Client / pseudo')),
        TextField(controller: ref, decoration: const InputDecoration(labelText: 'Référence de la commande (facultatif)')),
        TextField(controller: address, maxLines: 2, decoration: const InputDecoration(labelText: 'Adresse (facultatif)')),
        TextField(controller: shipping, keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Frais de port', suffixText: '€'), onChanged: (_) => setState(() {})),
        const SizedBox(height: 16),
        Row(children: [
          Expanded(child: FilledButton.icon(onPressed: _scan, icon: const Icon(Icons.qr_code_scanner), label: const Text('Scanner'))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton.icon(
            onPressed: () async {
              final p = await pickProduct(context, inStockOnly: true);
              if (p != null) _add(p);
            },
            icon: const Icon(Icons.search), label: const Text('Chercher'))),
        ]),
        for (final l in lines)
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text('${l['name']}', maxLines: 2, overflow: TextOverflow.ellipsis),
            subtitle: Text('${l['qty']} × ${money(numOf(l['unit_price']))} · toucher pour le prix',
                style: const TextStyle(color: muted)),
            onTap: () async {
              final v = await askNumber(context, 'Prix unitaire', initial: numOf(l['unit_price']), decimal: true, suffix: '€');
              if (v != null) setState(() => l['unit_price'] = v);
            },
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              IconButton(icon: const Icon(Icons.remove_circle_outline), onPressed: () => setState(() {
                    if (numOf(l['qty']) <= 1) {
                      lines.remove(l);
                    } else {
                      l['qty'] = numOf(l['qty']) - 1;
                    }
                  })),
              IconButton(icon: const Icon(Icons.add_circle_outline),
                  onPressed: () => setState(() => l['qty'] = numOf(l['qty']) + 1)),
            ]),
          ),
        const SizedBox(height: 16),
        Text('Total : ${money(itemsTotal + ship)}', textAlign: TextAlign.right,
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
        const SizedBox(height: 16),
        FilledButton(style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)), onPressed: _save,
            child: const Text('Enregistrer la commande')),
      ]),
    );
  }
}
