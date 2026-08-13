// Lucifer Flutter app entry point
import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'ui/home_page.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await dotenv.load(fileName: ".env");
  runApp(const LuciferApp());
}

class LuciferApp extends StatelessWidget {
  const LuciferApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Lucifer',
      theme: ThemeData.dark().copyWith(
        colorScheme: ColorScheme.dark(
          primary: Color(0xFFE53935), // Lucifer red
          secondary: Color(0xFFFF6F00),
        ),
        useMaterial3: true,
      ),
      home: const HomePage(),
      debugShowCheckedModeBanner: false,
    );
  }
}
