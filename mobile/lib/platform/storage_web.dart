import 'package:idb_shim/idb_browser.dart';

/// IndexedDB : pas de limite de 5 Mo comme localStorage, et conservé par l'appli installée sur l'écran d'accueil.
class KvStorage {
  late Database _db;
  static const _store = 'kv';

  Future<void> init() async {
    _db = await idbFactoryBrowser.open('tcshop', version: 1, onUpgradeNeeded: (VersionChangeEvent e) {
      e.database.createObjectStore(_store);
    });
  }

  Future<String?> read(String key) async {
    final txn = _db.transaction(_store, idbModeReadOnly);
    final v = await txn.objectStore(_store).getObject(key);
    await txn.completed;
    return v as String?;
  }

  Future<void> write(String key, String value) async {
    final txn = _db.transaction(_store, idbModeReadWrite);
    await txn.objectStore(_store).put(value, key);
    await txn.completed;
  }
}
