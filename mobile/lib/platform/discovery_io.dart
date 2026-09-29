import 'dart:async';
import 'dart:convert';
import 'dart:io';

const discoveryPort = 8766;

/// Envoie « TCSHOP_DISCOVER » en diffusion ; TCShop sur le PC répond avec son port.
Future<({String host, int port})?> discoverPc({Duration timeout = const Duration(seconds: 3)}) async {
  RawDatagramSocket? sock;
  try {
    sock = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
    sock.broadcastEnabled = true;
    final done = Completer<({String host, int port})?>();
    sock.listen((event) {
      if (event != RawSocketEvent.read) return;
      final dg = sock!.receive();
      if (dg == null) return;
      try {
        final m = jsonDecode(utf8.decode(dg.data)) as Map<String, dynamic>;
        if (m['app'] == 'TCShop' && !done.isCompleted) {
          done.complete((host: dg.address.address, port: (m['port'] as num).toInt()));
        }
      } catch (_) {}
    });
    sock.send(utf8.encode('TCSHOP_DISCOVER'), InternetAddress('255.255.255.255'), discoveryPort);
    return await done.future.timeout(timeout, onTimeout: () => null);
  } catch (_) {
    return null;
  } finally {
    sock?.close();
  }
}
