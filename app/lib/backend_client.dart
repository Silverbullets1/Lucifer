// Lucifer backend client — talks to the FastAPI server.
// Voice path: record audio -> POST /voice -> play returned wav.
// Stream path: WebSocket /ws for low-latency back-and-forth.
import 'dart:convert';
import 'dart:io';
import 'package:dio/dio.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

class LuciferClient {
  final String baseUrl;
  late final Dio _dio;

  LuciferClient(this.baseUrl) : _dio = Dio(BaseOptions(baseUrl: baseUrl));

  /// Text chat (no audio). Used for quick testing / text mode.
  Future<String> chat(String text) async {
    final res = await _dio.post('/chat', data: {'text': text});
    return (res.data as Map)['reply'] as String;
  }

  /// Voice round-trip: send raw wav bytes, get back base64 wav audio.
  Future<(String text, String reply, String audioBase64)> voice(List<int> wavBytes) async {
    final form = FormData.fromMap({
      'audio': MultipartFile.fromBytes(wavBytes, filename: 'chunk.wav'),
    });
    final res = await _dio.post('/voice', data: form);
    final data = res.data as Map;
    return (
      (data['text'] ?? '') as String,
      (data['reply'] ?? '') as String,
      (data['audio_b64'] ?? '') as String,
    );
  }

  /// Streaming websocket: emits STT/LLM json + binary audio frames.
  WebSocketChannel connect() {
    final uri = Uri.parse(baseUrl.replaceFirst('http', 'ws') + '/ws');
    return WebSocketChannel.connect(uri);
  }
}
