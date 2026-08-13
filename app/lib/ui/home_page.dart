// Lucifer home screen: mic button -> record -> backend -> play reply.
import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:record/record.dart';
import 'package:audioplayers/audioplayers.dart';
import 'backend_client.dart';
import 'wake_word.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _client = LuciferClient(
    const String.fromEnvironment('BACKEND_URL',
        defaultValue: 'http://192.168.29.146:8723'),
  );
  final _recorder = AudioRecorder();
  final _player = AudioPlayer();
  final _wake = WakeWordService();

  String _userText = '';
  String _luciferText = '';
  bool _listening = false;
  bool _wakeReady = false;

  @override
  void initState() {
    super.initState();
    _initWakeWord();
  }

  Future<void> _initWakeWord() async {
    try {
      await _wake.init();
      _wake.onWake = () => _toggleListen();
      setState(() => _wakeReady = true);
    } catch (e) {
      // No Porcupine key -> run in tap-to-talk mode only.
      setState(() => _wakeReady = false);
    }
  }

  Future<void> _toggleListen() async {
    if (_listening) {
      final path = await _recorder.stop();
      if (path == null) return;
      final bytes = await File(path).readAsBytes();
      setState(() => _listening = false);
      final (text, reply, audioB64) = await _client.voice(bytes);
      setState(() {
        _userText = text;
        _luciferText = reply;
      });
      if (audioB64.isNotEmpty) {
        final data = base64Decode(audioB64);
        await _player.play(BytesSource(data));
      }
    } else {
      if (await _recorder.hasPermission()) {
        await _recorder.start(
          const RecordConfig(encoder: AudioEncoder.wav, sampleRate: 16000),
          path: '/tmp/lucifer_${DateTime.now().millisecondsSinceEpoch}.wav',
        );
        setState(() => _listening = true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('🔥 LUCIFER'),
        centerTitle: true,
        backgroundColor: Colors.transparent,
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('You: $_userText', style: const TextStyle(color: Colors.white70)),
            const SizedBox(height: 16),
            Text('Lucifer: $_luciferText',
                style: const TextStyle(color: Colors.redAccent, fontSize: 18)),
            const SizedBox(height: 40),
            GestureDetector(
              onTap: _toggleListen,
              child: Icon(
                _listening ? Icons.graphic_eq : Icons.mic,
                size: 80,
                color: _listening ? Colors.red : Colors.white,
              ),
            ),
            const SizedBox(height: 12),
            Text(_wakeReady ? 'Say "Lucifer" to wake' : 'Tap mic to talk',
                style: const TextStyle(color: Colors.grey)),
          ],
        ),
      ),
    );
  }
}
