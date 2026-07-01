# -*- coding: utf-8 -*-
"""
ローカルサーバー: 同じ Wi-Fi のスマホから AI関連株ダッシュボードを見るための簡易サーバー。
起動時にデータを更新し（以後6時間ごと）、LAN の URL を表示し、QRコードを出す。
index.html / fetch_data.py と同じフォルダに置き、launch.bat から起動する。
"""
from __future__ import annotations
import http.server, socketserver, socket, threading, time, os, webbrowser, functools, importlib.util

WEB = os.path.dirname(os.path.abspath(__file__))   # index.html のあるフォルダ
PORT = 8000
REFRESH_SEC = 6 * 3600


def refresh_data():
    try:
        spec = importlib.util.spec_from_file_location("fetch_data", os.path.join(WEB, "fetch_data.py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); mod.main()
    except Exception as e:
        print(f"[warn] price refresh failed ({e}); serving last data.")


def refresher():
    while True:
        time.sleep(REFRESH_SEC); refresh_data()


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        try: return socket.gethostbyname(socket.gethostname())
        except Exception: return "127.0.0.1"


def show_qr(url):
    try:
        import qrcode
        p = os.path.join(WEB, "qr.png"); qrcode.make(url).save(p)
        try: os.startfile(p)
        except Exception: webbrowser.open("file:///" + p.replace("\\", "/"))
    except Exception:
        print("(QR unavailable; type the URL above into your phone.)")


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def end_headers(self):
        if self.path.startswith("/data"): self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    print("最新の株価を取得しています ..."); refresh_data()
    threading.Thread(target=refresher, daemon=True).start()
    url = f"http://{lan_ip()}:{PORT}/"
    print("=" * 52); print(" AI関連株ダッシュボードを起動しました")
    print(" スマホ（同じWi-Fi）で開く:\n\n    " + url + "\n")
    print(" またはQRコードを読み取ってください。閉じるには この窓を閉じます。"); print("=" * 52)
    show_qr(url)
    try: webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception: pass
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), functools.partial(H, directory=WEB)) as httpd:
        httpd.allow_reuse_address = True; httpd.serve_forever()


if __name__ == "__main__":
    main()
