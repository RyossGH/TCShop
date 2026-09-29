import 'package:flutter/material.dart';

import '../store.dart';
import '../widgets.dart';

/// Premier lancement : associer le téléphone à TCShop sur le PC.
class PairScreen extends StatefulWidget {
  const PairScreen({super.key});

  @override
  State<PairScreen> createState() => _PairScreenState();
}

class _PairScreenState extends State<PairScreen> {
  bool busy = false;
  String? error;

  Future<void> _scan() async {
    final code = await ScannerPage.scanOnce(context, title: 'QR code affiché par TCShop');
    if (code == null) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final ok = await store.pair(Uri.parse(code));
      if (!ok) error = store.lastError;
    } catch (e) {
      error = '$e';
    }
    if (mounted) setState(() => busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Image.asset('assets/logo.png', height: 120),
            const SizedBox(height: 16),
            const Text('TCShop Mobile', textAlign: TextAlign.center,
                style: TextStyle(fontSize: 30, fontWeight: FontWeight.w800, color: accent)),
            const SizedBox(height: 24),
            const Text(
              'Sur le PC : TCShop → Paramètres → TCShop Mobile → « Associer un téléphone ».\n\n'
              'Mettez le téléphone sur le même Wi-Fi que le PC, puis scannez le QR code affiché.',
              textAlign: TextAlign.center,
              style: TextStyle(color: muted, fontSize: 15),
            ),
            const SizedBox(height: 32),
            FilledButton.icon(
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(56)),
              onPressed: busy ? null : _scan,
              icon: busy
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.qr_code_scanner),
              label: Text(busy ? 'Connexion au PC…' : 'Scanner le QR code'),
            ),
            if (error != null) ...[
              const SizedBox(height: 16),
              Text(error!, textAlign: TextAlign.center, style: const TextStyle(color: warning)),
              if (store.paired)
                TextButton(onPressed: () => setState(() {}), child: const Text('Continuer quand même (hors ligne)')),
            ],
          ]),
        ),
      ),
    );
  }
}
