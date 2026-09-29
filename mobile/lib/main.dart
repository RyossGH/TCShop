import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'screens/buy_screen.dart';
import 'screens/collections_screen.dart';
import 'screens/orders_screen.dart';
import 'screens/pair_screen.dart';
import 'screens/sale_screen.dart';
import 'screens/stock_screen.dart';
import 'screens/sync_screen.dart';
import 'store.dart';
import 'widgets.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (kIsWeb) {
    // iPhone : lecteur de codes-barres embarqué dans l'appli (fonctionne sans Internet, en convention)
    MobileScannerPlatform.instance.setWebBarcodeReader(WebBarcodeReader.zxingJs);
    MobileScannerPlatform.instance.setBarcodeLibraryScriptUrl('zxing.min.js');
  }
  store = AppStore();
  await store.load();
  runApp(const TCShopApp());
}

class TCShopApp extends StatelessWidget {
  const TCShopApp({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = ColorScheme.fromSeed(seedColor: accent, brightness: Brightness.dark, surface: const Color(0xFF0E1120));
    return MaterialApp(
      title: 'TCShop',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        fontFamily: 'Roboto', // police embarquée : le texte s'affiche aussi hors ligne sur iPhone
        colorScheme: scheme,
        scaffoldBackgroundColor: const Color(0xFF0E1120),
        appBarTheme: const AppBarTheme(backgroundColor: Color(0xFF0E1120), centerTitle: false),
        navigationBarTheme: const NavigationBarThemeData(backgroundColor: panel),
        inputDecorationTheme: const InputDecorationTheme(filled: true, fillColor: panel, border: OutlineInputBorder()),
      ),
      home: ListenableBuilder(
        listenable: store,
        builder: (context, _) => store.paired ? const HomeScreen() : const PairScreen(),
      ),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int index = 0;
  late final AppLifecycleListener _lifecycle;

  @override
  void initState() {
    super.initState();
    // retour dans l'appli (ex. retour à la boutique) : on tente une synchro
    _lifecycle = AppLifecycleListener(onResume: () => store.sync());
    // synchro dès l'ouverture de l'appli (catalogue à jour tout de suite)
    WidgetsBinding.instance.addPostFrameCallback((_) => store.sync());
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const pages = [SaleScreen(), BuyScreen(), StockScreen(), CollectionsScreen(), MoreScreen()];
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final pendingBadge = store.pending.isNotEmpty;
        return Scaffold(
          body: IndexedStack(index: index, children: pages),
          bottomNavigationBar: NavigationBar(
            selectedIndex: index,
            onDestinationSelected: (i) => setState(() => index = i),
            labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
            destinations: [
              const NavigationDestination(icon: Icon(Icons.point_of_sale), label: 'Caisse'),
              const NavigationDestination(icon: Icon(Icons.handshake), label: 'Rachat'),
              const NavigationDestination(icon: Icon(Icons.inventory_2), label: 'Stock'),
              const NavigationDestination(icon: Icon(Icons.collections_bookmark), label: 'Collections'),
              NavigationDestination(
                icon: Badge(
                  isLabelVisible: pendingBadge || store.lastError != null,
                  label: Text(pendingBadge ? '${store.pending.length}' : '!'),
                  child: Icon(store.syncing ? Icons.sync : Icons.menu),
                ),
                label: 'Plus',
              ),
            ],
          ),
        );
      },
    );
  }
}

/// Onglet « Plus » : commandes en ligne et synchronisation.
class MoreScreen extends StatelessWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final open = store.orders.where((o) => nextStatus.containsKey(o['status'])).length;
        return Scaffold(
          appBar: AppBar(title: Text(store.shopName)),
          body: ListView(children: [
            ListTile(
              leading: const Icon(Icons.local_shipping, color: accent),
              title: const Text('Commandes en ligne'),
              subtitle: Text('$open commande(s) en cours', style: const TextStyle(color: muted)),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const OrdersScreen())),
            ),
            ListTile(
              leading: Icon(store.lastError == null ? Icons.cloud_done : Icons.cloud_off,
                  color: store.lastError == null ? success : warning),
              title: const Text('Synchronisation avec le PC'),
              subtitle: Text(
                  store.syncing
                      ? 'En cours…'
                      : '${store.pending.length} en attente · dernière : '
                          '${store.lastSync == null ? 'jamais' : shortDate(store.lastSync)}',
                  style: const TextStyle(color: muted)),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const SyncScreen())),
            ),
          ]),
        );
      },
    );
  }
}
