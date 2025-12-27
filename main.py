import threading
from app import app  # 'app' teri Flask file ka naam hai
from kivy.app import App
from kivy.uix.vkeyboard import VKeyboard
from kivy.core.window import Window
from kivy.uix.webview import WebView # Android backend ke liye

# Flask ko alag thread mein chalana padta hai
def start_flask():
    app.run(host='127.0.0.1', port=5000, debug=False)

class EmergencyApp(App):
    def build(self):
        threading.Thread(target=start_flask, daemon=True).start()
        # Ye part Android ki screen par tera dashboard dikhayega
        return WebView(url="http://127.0.0.1:5000/")

if __name__ == '__main__':
    EmergencyApp().run()
