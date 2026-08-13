// Wake word via Picovoice Porcupine. Free tier supports a custom "Lucifer"
// keyword (train at console.picovoice.ai). Falls back to tap-to-talk if no key.
import 'package:porcupine_flutter/porcupine_manager.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

class WakeWordService {
  PorcupineManager? _manager;
  void Function()? onWake;

  Future<void> init() async {
    final key = dotenv.env['PORCUPINE_KEY'] ?? '';
    if (key.isEmpty) throw Exception('no porcupine key');
    _manager = await PorcupineManager.fromKeywordPaths(
      key,
      [/* path to lucifer_android.ppn / lucifer_ios.ppn */],
      (keywordIndex) => onWake?.call(),
    );
    await _manager?.start();
  }

  Future<void> dispose() async => await _manager?.stop();
}
