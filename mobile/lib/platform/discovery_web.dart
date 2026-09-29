/// Dans le navigateur, l'appli est servie par le PC lui-même : pas de recherche réseau possible ni utile.
Future<({String host, int port})?> discoverPc({Duration timeout = const Duration(seconds: 3)}) async => null;
