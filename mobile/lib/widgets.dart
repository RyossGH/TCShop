import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'store.dart';

const accent = Color(0xFF7C5CFF);
const panel = Color(0xFF161A2E);
const panel2 = Color(0xFF1D2239);
const muted = Color(0xFF8B91B0);
const success = Color(0xFF22C55E);
const warning = Color(0xFFF59E0B);
const danger = Color(0xFFEF4444);

Color statusColor(String? s) => switch (s) {
      'À préparer' => warning,
      'Préparée' => const Color(0xFF38BDF8),
      'Expédiée' => accent,
      'Livrée' => success,
      'Annulée' => muted,
      _ => Colors.white,
    };

void toast(BuildContext context, String msg, {bool error = false}) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? danger : null,
      behavior: SnackBarBehavior.floating,
      duration: Duration(seconds: error ? 4 : 2),
    ));
}

// ====================================================================== images
class ProductImage extends StatelessWidget {
  const ProductImage(this.product, {super.key, this.size = 48});
  final Json product;
  final double size;

  @override
  Widget build(BuildContext context) {
    final url = store.api.imageUrl(product['image_url'] as String?);
    final placeholder = Container(
      width: size,
      height: size * 1.3,
      decoration: BoxDecoration(color: panel2, borderRadius: BorderRadius.circular(6)),
      child: Icon(product['track_stock'] == 0 ? Icons.event : Icons.style, color: muted, size: size * 0.5),
    );
    if (url == null) return placeholder;
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: Image.network(url, width: size, height: size * 1.3, fit: BoxFit.contain,
          errorBuilder: (_, __, ___) => placeholder),
    );
  }
}

class StockBadge extends StatelessWidget {
  const StockBadge(this.product, {super.key});
  final Json product;

  @override
  Widget build(BuildContext context) {
    if (product['track_stock'] == 0) return const Text('∞', style: TextStyle(color: muted));
    final q = numOf(product['quantity']).toInt();
    final min = numOf(product['min_stock']).toInt();
    final c = q <= 0 ? danger : (min > 0 && q <= min ? warning : success);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: c.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(10)),
      child: Text('$q', style: TextStyle(color: c, fontWeight: FontWeight.bold)),
    );
  }
}

class ProductTile extends StatelessWidget {
  const ProductTile(this.product, {super.key, this.onTap, this.trailing});
  final Json product;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final p = product;
    final sub = [p['variant'], p['set_name'], p['category'] == 'Carte' ? '${p['condition']} ${p['language']}' : null,
      p['location']].where((e) => '${e ?? ''}'.trim().isNotEmpty).join(' · ');
    return ListTile(
      onTap: onTap,
      leading: ProductImage(p, size: 36),
      title: Text('${p['name']}', maxLines: 2, overflow: TextOverflow.ellipsis),
      subtitle: sub.isEmpty ? null : Text(sub, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: muted)),
      trailing: trailing ??
          Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text(money(numOf(p['price'])), style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            StockBadge(p),
          ]),
    );
  }
}

// ====================================================================== scanner
class ScannerPage extends StatefulWidget {
  const ScannerPage({super.key, this.title = 'Scanner', this.onCode});

  /// Si onCode est fourni : scan en continu (la page reste ouverte). Sinon : renvoie le premier code lu.
  final String title;
  final String? Function(String code)? onCode;

  static Future<String?> scanOnce(BuildContext context, {String title = 'Scanner'}) =>
      Navigator.push<String>(context, MaterialPageRoute(builder: (_) => ScannerPage(title: title)));

  @override
  State<ScannerPage> createState() => _ScannerPageState();
}

class _ScannerPageState extends State<ScannerPage> {
  final controller = MobileScannerController(detectionSpeed: DetectionSpeed.normal);
  bool _done = false;
  String? _lastCode;
  DateTime _lastAt = DateTime(2000);
  String? _message;
  int _count = 0;

  void _onDetect(BarcodeCapture capture) {
    final code = capture.barcodes.isNotEmpty ? capture.barcodes.first.rawValue : null;
    if (code == null || code.isEmpty) return;
    if (widget.onCode == null) {
      if (_done) return;
      _done = true;
      HapticFeedback.mediumImpact();
      Navigator.pop(context, code);
      return;
    }
    // continu : le même code n'est repris qu'après une petite pause (pour compter plusieurs exemplaires)
    final now = DateTime.now();
    if (code == _lastCode && now.difference(_lastAt) < const Duration(milliseconds: 1500)) return;
    _lastCode = code;
    _lastAt = now;
    HapticFeedback.mediumImpact();
    final msg = widget.onCode!(code);
    setState(() {
      _count++;
      _message = msg ?? code;
    });
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text(widget.title),
        actions: [IconButton(icon: const Icon(Icons.flash_on), onPressed: () => controller.toggleTorch())],
      ),
      body: Stack(children: [
        MobileScanner(controller: controller, onDetect: _onDetect),
        Center(
          child: Container(
            width: 280,
            height: 180,
            decoration: BoxDecoration(border: Border.all(color: accent, width: 3), borderRadius: BorderRadius.circular(16)),
          ),
        ),
        if (widget.onCode != null)
          Positioned(
            left: 16,
            right: 16,
            bottom: 24,
            child: Card(
              color: panel,
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Row(children: [
                  const Icon(Icons.qr_code_scanner, color: accent),
                  const SizedBox(width: 12),
                  Expanded(child: Text(_message ?? 'Visez un code-barres…', maxLines: 2)),
                  Text('$_count', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                ]),
              ),
            ),
          ),
      ]),
      floatingActionButton: widget.onCode != null
          ? FloatingActionButton.extended(
              onPressed: () => Navigator.pop(context),
              icon: const Icon(Icons.check),
              label: const Text('Terminé'),
            )
          : null,
    );
  }
}

// ====================================================================== sélection d'un article
Future<Json?> pickProduct(BuildContext context, {bool inStockOnly = false}) {
  return showModalBottomSheet<Json>(
    context: context,
    isScrollControlled: true,
    backgroundColor: panel,
    builder: (_) => FractionallySizedBox(heightFactor: 0.9, child: _ProductPicker(inStockOnly: inStockOnly)),
  );
}

class _ProductPicker extends StatefulWidget {
  const _ProductPicker({required this.inStockOnly});
  final bool inStockOnly;

  @override
  State<_ProductPicker> createState() => _ProductPickerState();
}

class _ProductPickerState extends State<_ProductPicker> {
  String q = '';

  @override
  Widget build(BuildContext context) {
    final rows = store.search(q, inStockOnly: widget.inStockOnly);
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: TextField(
            autofocus: true,
            decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Nom, marque, extension, SKU…'),
            onChanged: (v) => setState(() => q = v),
          ),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: rows.length,
            itemBuilder: (_, i) => ProductTile(rows[i], onTap: () => Navigator.pop(context, rows[i])),
          ),
        ),
      ]),
    );
  }
}

// ====================================================================== saisies
Future<num?> askNumber(BuildContext context, String title,
    {num? initial, String suffix = '', bool decimal = false, String? hint}) async {
  final ctrl = TextEditingController(text: initial == null ? '' : (decimal ? initial.toStringAsFixed(2) : '$initial'));
  final r = await showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: ctrl,
        autofocus: true,
        keyboardType: TextInputType.numberWithOptions(decimal: decimal, signed: false),
        decoration: InputDecoration(suffixText: suffix, hintText: hint),
        onSubmitted: (v) => Navigator.pop(ctx, v),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Annuler')),
        FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text), child: const Text('OK')),
      ],
    ),
  );
  if (r == null) return null;
  return num.tryParse(r.replaceAll(',', '.').trim());
}

Future<String?> askText(BuildContext context, String title, {String initial = '', String? hint}) async {
  final ctrl = TextEditingController(text: initial);
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: TextField(controller: ctrl, autofocus: true, decoration: InputDecoration(hintText: hint),
          onSubmitted: (v) => Navigator.pop(ctx, v)),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Annuler')),
        FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text.trim()), child: const Text('OK')),
      ],
    ),
  );
}

Future<bool> confirm(BuildContext context, String title, String message, {String ok = 'Confirmer'}) async {
  final r = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Annuler')),
        FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(ok)),
      ],
    ),
  );
  return r ?? false;
}
