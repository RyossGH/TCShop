import 'dart:io';

import 'package:path_provider/path_provider.dart';

class KvStorage {
  late Directory _dir;

  Future<void> init() async {
    _dir = await getApplicationDocumentsDirectory();
  }

  Future<String?> read(String key) async {
    final f = File('${_dir.path}/$key');
    return await f.exists() ? f.readAsString() : null;
  }

  Future<void> write(String key, String value) async {
    final f = File('${_dir.path}/$key.tmp');
    await f.writeAsString(value);
    await f.rename('${_dir.path}/$key'); // écriture atomique
  }
}
