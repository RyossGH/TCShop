import 'package:flutter/material.dart';

import '../store.dart';
import '../widgets.dart';

/// État de la synchronisation avec le PC.
class SyncScreen extends StatelessWidget {
  const SyncScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final ok = store.lastError == null && store.lastSync != null;
        return Scaffold(
          appBar: AppBar(title: const Text('Synchronisation')),
          body: ListView(padding: const EdgeInsets.all(16), children: [
            Card(
              color: panel,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Icon(store.syncing ? Icons.sync : (ok ? Icons.cloud_done : Icons.cloud_off),
                        color: store.syncing ? accent : (ok ? success : warning), size: 32),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(store.shopName, style: Theme.of(context).textTheme.titleLarge),
                        Text('PC : ${store.host}:${store.port}', style: const TextStyle(color: muted)),
                      ]),
                    ),
                  ]),
                  const SizedBox(height: 12),
                  Text(store.syncing
                      ? 'Synchronisation en cours…'
                      : 'Dernière synchro : ${store.lastSync == null ? 'jamais' : shortDate(store.lastSync)}'),
                  Text('${store.pending.length} opération(s) en attente d\'envoi',
                      style: TextStyle(color: store.pending.isEmpty ? muted : warning)),
                  if (store.lastError != null) ...[
                    const SizedBox(height: 8),
                    Text(store.lastError!, style: const TextStyle(color: warning)),
                  ],
                  const SizedBox(height: 14),
                  FilledButton.icon(
                    style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(50)),
                    onPressed: store.syncing
                        ? null
                        : () async {
                            final r = await store.sync(manual: true);
                            if (context.mounted) toast(context, r ? 'Synchronisé' : (store.lastError ?? 'Échec'), error: !r);
                          },
                    icon: const Icon(Icons.sync),
                    label: const Text('Synchroniser maintenant'),
                  ),
                ]),
              ),
            ),
            const Padding(
              padding: EdgeInsets.all(8),
              child: Text('La synchro est automatique toutes les minutes et après chaque opération, dès que le téléphone '
                  'est sur le même Wi-Fi que le PC (avec TCShop ouvert). Hors Wi-Fi, tout est gardé sur le téléphone.',
                  style: TextStyle(color: muted)),
            ),
            if (store.errors.isNotEmpty) ...[
              ListTile(
                title: const Text('Opérations refusées par le PC'),
                trailing: TextButton(onPressed: store.clearErrors, child: const Text('Effacer')),
              ),
              for (final e in store.errors.take(20))
                ListTile(dense: true, leading: const Icon(Icons.error_outline, color: danger), title: Text(e)),
            ],
            const Divider(height: 32),
            ListTile(
              leading: const Icon(Icons.smartphone),
              title: const Text('Nom de ce téléphone'),
              subtitle: Text(store.deviceName),
              onTap: () async {
                final v = await askText(context, 'Nom de ce téléphone', initial: store.deviceName);
                if (v != null) await store.setDeviceName(v);
              },
            ),
            ListTile(
              leading: const Icon(Icons.qr_code_2),
              title: const Text('Réassocier au PC (scanner le QR code)'),
              onTap: () async {
                final code = await ScannerPage.scanOnce(context, title: 'QR code TCShop');
                if (code == null) return;
                try {
                  final r = await store.pair(Uri.parse(code));
                  if (context.mounted) toast(context, r ? 'Associé' : (store.lastError ?? 'PC injoignable'), error: !r);
                } catch (e) {
                  if (context.mounted) toast(context, '$e', error: true);
                }
              },
            ),
            ListTile(
              leading: const Icon(Icons.link_off, color: danger),
              title: const Text('Dissocier ce téléphone'),
              subtitle: store.pending.isNotEmpty
                  ? Text('Attention : ${store.pending.length} opération(s) pas encore envoyée(s)', style: const TextStyle(color: warning))
                  : null,
              onTap: () async {
                if (await confirm(context, 'Dissocier ?', 'Le téléphone ne se synchronisera plus avec ce PC.')) {
                  await store.unpair();
                }
              },
            ),
          ]),
        );
      },
    );
  }
}
