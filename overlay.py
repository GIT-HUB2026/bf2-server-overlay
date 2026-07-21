"""BF2 SERVER OVERLAY - live BF2Hub server info popup (always-on-top).

Ranked populated servers (name / players / map) + the three deranked
dogfight servers (name / players). Data scraped from bf2hub.com.
Run with --once for a console parse test (no GUI).
"""
import ctypes
import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from queue import Queue, Empty
from urllib.request import Request, urlopen

VERSION = "1.2"
CREDIT = "Made by ribbycag3 - free to share 2026"
APP_NAME = "BF2 Server Overlay"
EXE_NAME = "BF2 SERVER OVERLAY.exe"
LOGO_B64 = "iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAADYklEQVR4nL2Vz2tcVRTHP+e+mSZtflRjCa0l4kKwRJFKJJixUIi6EdTVIBTRXZCY4KKrKjKZP0BEUguKK10USUFcFjGaRTNpIf6CBgVroaZoi8YGGtM6895Xznvz0skkKa48zIW5953zueece+65RruoErBqkk9HNHFIqAihL1tJVgyr1+zkjzvZuFjrpKxyNGMz8VGN7Wuw6yDYw5Bcb5CsFAm3XKdO0llINwn9oJ8K/HN1zj78I7fdCla264gmHzeSgQj7vZOOi1/YO2tbogKe1fGuddYfFeFggl2u2fS3FVVCten5Jo9LGj8M9kARzc7ZqZu+NqSxYjcH1KrXz5JavXtKk88nsOzwLR6X9Pr9IpRqNn1mp7y1y6DGu/soHItY/bhBz3Mx9fML9sFV/1ZAMswk9PQqfZ8irEw5zFg1Lmn8RWHDhqXpEBaDegzO3uDa+W6iABq4TZ8NsPz5b+w/BnzizIJDRzQxGmGLS1TrFSq2xFIe0BDwksFfwnoDioRuChu9h/65eZs+AbztOy4AR5hcdFbNbDYMa7IXVGxQuOyoPPlND/827EYCK0JTMbwGXAJ2g/XkZ5DrZwwVnRkMc6X6gr273p5Dg2AQGQo1O3k6wS44tLne4TqLHIgx0sPNGFZ3ZjCShwL86R88De1wpb8QShp/s4A+gtALXBHhs0xjSq22znJmwTDFxOnhVKluKqscLTAjvArcAn1vcPoc957NwjK12sYka0bUFe5WTpmYRyqRvCX0pcEhsBNPcP3BtKK8LLeRECGLCF3bpULgB+meJDU7dcYIywkUhaxIeCX3ttXWWc4MdcLPCdy3fSrUCfSA7RnS2L6E5GtDa4Jug2ee1MRweon8KjdtneXMILTuJTKksT05bpDB5gbhkmHngAu7ieIFe/8bCF8Zmgf7JWo6VGYp9TZjyCPKKsyL+ogmB71wKzvkLAtg+2+pjTBnOKuprHS3kiZeHlRllyukI0uyn1s2NuDNeTqausLc1hm5TrhzAJrdy8oLG6ppE/L/lo1c8nm6VklLxkdqi2Zznba2+cZhaGxqm1n42SW4I1OWd76jGu+uY6NQuDJv7323sf/dGv0qHRd/2KHRP6bjXXu5/UiM9ovwa9qLW1rt//A0tXmeT/PHNIN5B/tvj+m/YVy+q921b0wAAAAASUVORK5CYII="

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)
DATA_DIR = os.path.join(os.environ.get("APPDATA", APP_DIR), APP_NAME) if FROZEN else APP_DIR
STATE_FILE = os.path.join(DATA_DIR, "state.json")

RANKED_URL = "https://www.bf2hub.com/servers/ranked/"
DOGFIGHT_ADDRS = [
    "138.197.130.124:16569",
    "173.234.79.175:11000",
    "45.76.81.207:16571",
]
SERVER_URL = "https://www.bf2hub.com/server/{}/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BF2ServerOverlay/1.0"
REFRESH_SECONDS = 30
MAX_RANKED_ROWS = 14
HOVER_TTL = 30
MAX_TEAM_ROWS = 40

BG = "#0b0f14"
PANEL = "#131a22"
ROW_ALT = "#0f151c"
ACC = "#3dff6e"
ACC2 = "#b0ffc8"
TXT = "#e8eef4"
DIM = "#76828f"
RED = "#ff5563"

ROW_RE = re.compile(r'<tr class="(?:odd|even)">(.*?)</tr>', re.S)
HOST_RE = re.compile(r'hostname"><a href="/server/([^"]+)/">(.*?)</a>')
COUNT_RE = re.compile(r'<td class="c">(\d+)/(\d+)</td>')
MAP_RE = re.compile(r'mapname">(.*?)</td>')
H3_RE = re.compile(r"<h3>(.*?)</h3>", re.S)
PLAYER_ROW_RE = re.compile(r'<tr class="row')
TEAM_SPLIT_RE = re.compile(r'class="pl_team_\d"')
ARMY_RE = re.compile(r'title="([A-Z]{2,3})"')
ROWCELL_RE = re.compile(r'<tr class="row[12][^"]*">(.*?)</tr>', re.S)
NCELL_RE = re.compile(r'<td class="n">(.*?)</td>', re.S)
PING_RE = re.compile(r'<td class="p">([^<]*)</td>')
TAG_RE = re.compile(r"<[^>]+>")


def fetch(url):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", "replace")


def parse_ranked(page):
    servers = []
    for block in ROW_RE.findall(page):
        host = HOST_RE.search(block)
        count = COUNT_RE.search(block)
        if not (host and count):
            continue
        map_m = MAP_RE.search(block)
        servers.append({
            "addr": host.group(1),
            "name": html.unescape(host.group(2)).strip(),
            "players": int(count.group(1)),
            "max": int(count.group(2)),
            "map": html.unescape(map_m.group(1)).strip() if map_m else "?",
        })
    return servers


def parse_server(page, addr):
    h3 = H3_RE.search(page)
    return {
        "addr": addr,
        "name": html.unescape(h3.group(1)).strip() if h3 else addr,
        "players": len(PLAYER_ROW_RE.findall(page)),
    }


def parse_players(page):
    """Both team columns of a server-detail page: [{'army', 'players': [(name, active)]}]."""
    parts = TEAM_SPLIT_RE.split(page)
    teams = []
    for part in parts[1:3]:
        army = ARMY_RE.search(part)
        players = []
        for row in ROWCELL_RE.findall(part):
            ncell = NCELL_RE.search(row)
            if not ncell:
                continue
            name = html.unescape(TAG_RE.sub("", ncell.group(1))).strip()
            ping = PING_RE.search(row)
            players.append((name, bool(ping and ping.group(1).strip() != "-")))
        teams.append({"army": army.group(1) if army else "?", "players": players})
    return teams


def gather():
    """Fetch ranked list + dogfight pages concurrently. Returns data dict."""
    data = {"ranked": None, "ranked_err": None, "dogfight": [], "dogfight_err": None,
            "at": time.strftime("%H:%M:%S")}

    def get_ranked():
        try:
            servers = parse_ranked(fetch(RANKED_URL))
            populated = [s for s in servers if s["players"] > 0]
            populated.sort(key=lambda s: s["players"], reverse=True)
            data["ranked"] = populated
        except Exception as e:
            data["ranked_err"] = str(e)

    results = {}

    def get_dogfight(addr):
        try:
            results[addr] = parse_server(fetch(SERVER_URL.format(addr)), addr)
        except Exception as e:
            results[addr] = e

    threads = [threading.Thread(target=get_ranked, daemon=True)]
    threads += [threading.Thread(target=get_dogfight, args=(a,), daemon=True)
                for a in DOGFIGHT_ADDRS]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    errs = []
    for addr in DOGFIGHT_ADDRS:
        r = results.get(addr)
        if isinstance(r, dict):
            data["dogfight"].append(r)
        else:
            errs.append(f"{addr}: {r if r else 'timeout'}")
    if errs:
        data["dogfight_err"] = " | ".join(errs)
    return data


def trunc(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


def another_instance_running():
    """Windows named mutex — True if an overlay already holds it."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW(None, False, "BF2ServerOverlay_SingleInstance")
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def focus_existing():
    u32 = ctypes.windll.user32
    hwnd = u32.FindWindowW(None, "BF2 LIVE SERVERS")
    if hwnd:
        u32.SetForegroundWindow(hwnd)


def self_install():
    """First run of the frozen exe from outside the install dir: copy the exe
    to %LOCALAPPDATA%\\Programs and (re)point a Desktop shortcut at it."""
    if not FROZEN:
        return
    exe = sys.executable
    install_dir = os.path.join(os.environ["LOCALAPPDATA"], "Programs", APP_NAME)
    target = os.path.join(install_dir, EXE_NAME)
    if os.path.normcase(exe) == os.path.normcase(target):
        return
    try:
        os.makedirs(install_dir, exist_ok=True)
        shutil.copy2(exe, target)
        ps = ("$w=New-Object -ComObject WScript.Shell;"
              "$d=$w.SpecialFolders('Desktop');"
              "$l=$w.CreateShortcut(\"$d\\BF2 SERVER OVERLAY.lnk\");"
              f"$l.TargetPath='{target}';"
              f"$l.WorkingDirectory='{install_dir}';"
              f"$l.IconLocation='{target},0';"
              "$l.Save()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       creationflags=0x08000000, timeout=30)
    except Exception:
        pass


class Overlay:
    def __init__(self, root):
        self.root = root
        self.q = Queue()
        self.fetching = False
        self.next_at = time.time()
        self.drag = None
        self.pop = None
        self.pop_addr = None
        self.pop_name = ""
        self.pop_row = None
        self.hover_addr = None
        self.hover_after = None
        self.hide_after = None
        self.pcache = {}
        self.pfetching = set()

        root.title("BF2 LIVE SERVERS")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.94)
        root.configure(bg=BG)
        self._restore_pos()

        f_title = ("Segoe UI", 10, "bold")
        self.f_label = ("Segoe UI", 8, "bold")
        self.f_row = ("Segoe UI", 10)
        self.f_num = ("Consolas", 10, "bold")

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=10, pady=(8, 4))
        title = tk.Label(header, text="BF2 LIVE SERVERS", font=f_title, fg=ACC, bg=BG)
        title.pack(side="left")
        ver = tk.Label(header, text=f"v{VERSION}", font=("Segoe UI", 8), fg=DIM, bg=BG)
        ver.pack(side="left", padx=(4, 0))
        try:
            self.logo_img = tk.PhotoImage(data=LOGO_B64)
            tk.Label(header, image=self.logo_img, bg=BG).pack(side="left", padx=(6, 0))
        except Exception:
            pass
        close = tk.Label(header, text=" ✕ ", font=f_title, fg=DIM, bg=BG, cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self._close())
        refresh = tk.Label(header, text=" ⟳ ", font=f_title, fg=DIM, bg=BG, cursor="hand2")
        refresh.pack(side="right")
        refresh.bind("<Button-1>", lambda e: self.start_fetch())
        self.countdown = tk.Label(header, text="", font=("Consolas", 9), fg=DIM, bg=BG)
        self.countdown.pack(side="right")

        for w in (header, title):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)

        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        self.status = tk.Label(root, text="", font=("Segoe UI", 8), fg=DIM, bg=BG)
        self.status.pack(fill="x", padx=10, pady=(0, 6))
        self._status("loading…")

        root.bind("<Escape>", lambda e: self._close())

        self.start_fetch()
        self._poll()
        self._tick()

    # -- window position ------------------------------------------------
    def _restore_pos(self):
        x = y = None
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                st = json.load(f)
            x, y = int(st["x"]), int(st["y"])
        except Exception:
            pass
        if x is None:
            self.root.update_idletasks()
            x = self.root.winfo_screenwidth() - 520
            y = 60
        self.root.geometry(f"+{x}+{y}")

    def _save_pos(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({"x": self.root.winfo_x(), "y": self.root.winfo_y()}, f)
        except Exception:
            pass

    def _drag_start(self, e):
        self.drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        if self.drag:
            self.root.geometry(f"+{e.x_root - self.drag[0]}+{e.y_root - self.drag[1]}")

    def _drag_end(self, e):
        self.drag = None
        self._save_pos()

    def _close(self):
        self._save_pos()
        self.root.destroy()

    def _status(self, text):
        self.status.configure(text=f"{text} · {CREDIT}")

    # -- data ------------------------------------------------------------
    def start_fetch(self):
        if self.fetching:
            return
        self.fetching = True
        self._status("refreshing…")
        threading.Thread(target=lambda: self.q.put(gather()), daemon=True).start()

    def _poll(self):
        try:
            item = self.q.get_nowait()
        except Empty:
            pass
        else:
            if isinstance(item, tuple) and item[0] == "players":
                _, addr, res = item
                self.pfetching.discard(addr)
                self.pcache[addr] = (time.time(), res)
                if self.pop_addr == addr:
                    self._pop_render(self.pop_name, res, self.pop_row)
            else:
                self.fetching = False
                self.next_at = time.time() + REFRESH_SECONDS
                self.root.after(REFRESH_SECONDS * 1000, self.start_fetch)
                self._render(item)
        self.root.after(250, self._poll)

    def _tick(self):
        left = max(0, int(self.next_at - time.time()))
        self.countdown.configure(text=f"⟳ {left}s" if not self.fetching else "⟳ …")
        self.root.after(1000, self._tick)

    # -- rendering --------------------------------------------------------
    def _render(self, data):
        for w in self.body.winfo_children():
            w.destroy()

        self._section("UNRANKED · DOGFIGHT")
        if data["dogfight"]:
            for i, s in enumerate(data["dogfight"]):
                self._row(i, s, False, name_w=40)
        if data["dogfight_err"]:
            self._error(data["dogfight_err"])

        self._section("RANKED · POPULATED", pad_top=8)
        if data["ranked_err"]:
            self._error(data["ranked_err"])
        elif data["ranked"] is not None:
            shown = data["ranked"][:MAX_RANKED_ROWS]
            for i, s in enumerate(shown):
                self._row(i, s, True, name_w=27)
            extra = data["ranked"][MAX_RANKED_ROWS:]
            if extra:
                more = tk.Label(self.body, text=f"+{len(extra)} more servers · "
                                f"{sum(s['players'] for s in extra)} players",
                                font=("Segoe UI", 9), fg=DIM, bg=BG, anchor="w")
                more.pack(fill="x", pady=(2, 0))
            if not shown:
                self._error("no populated servers", dim=True)

        self._status(f"bf2hub.com · updated {data['at']}")

    def _section(self, text, pad_top=0):
        lbl = tk.Label(self.body, text=text, font=self.f_label, fg=ACC2, bg=BG, anchor="w")
        lbl.pack(fill="x", pady=(pad_top, 2))

    def _row(self, i, s, ranked, name_w):
        bg = PANEL if i % 2 == 0 else ROW_ALT
        row = tk.Frame(self.body, bg=bg)
        row.pack(fill="x")
        tk.Label(row, text=trunc(s["name"], name_w), font=self.f_row, fg=TXT, bg=bg,
                 anchor="w", width=name_w).pack(side="left", padx=(6, 4), pady=1)
        if ranked:
            count = f"{s['players']}/{s['max']}"
            tk.Label(row, text=trunc(s["map"], 20), font=self.f_row, fg=DIM, bg=bg,
                     anchor="w", width=20).pack(side="right", padx=(4, 6))
        else:
            count = str(s["players"])
        tk.Label(row, text=count, font=self.f_num, fg=ACC if s["players"] > 0 else DIM,
                 bg=bg, anchor="e", width=6).pack(side="right", padx=4)
        for w in [row] + row.winfo_children():
            w.bind("<Enter>", lambda e, a=s["addr"], n=s["name"], r=row:
                   self._hover_enter(a, n, r))
            w.bind("<Leave>", lambda e: self._hover_leave())

    def _error(self, msg, dim=False):
        tk.Label(self.body, text=trunc(msg, 60), font=("Segoe UI", 9),
                 fg=DIM if dim else RED, bg=BG, anchor="w").pack(fill="x")

    # -- hover player popup ------------------------------------------------
    def _hover_enter(self, addr, name, roww):
        if self.hide_after:
            self.root.after_cancel(self.hide_after)
            self.hide_after = None
        if self.hover_after:
            self.root.after_cancel(self.hover_after)
        self.hover_addr = addr
        self.hover_after = self.root.after(
            250, lambda: self._hover_show(addr, name, roww))

    def _hover_leave(self):
        if self.hover_after:
            self.root.after_cancel(self.hover_after)
            self.hover_after = None
        if self.hide_after:
            self.root.after_cancel(self.hide_after)
        self.hide_after = self.root.after(150, self._hide_pop)

    def _hide_pop(self):
        self.hide_after = None
        self.hover_addr = None
        self.pop_addr = None
        if self.pop:
            self.pop.withdraw()

    def _hover_show(self, addr, name, roww):
        self.hover_after = None
        if self.hover_addr != addr:
            return
        self.pop_addr = addr
        self.pop_name = name
        self.pop_row = roww
        cached = self.pcache.get(addr)
        if cached and time.time() - cached[0] <= HOVER_TTL:
            self._pop_render(name, cached[1], roww)
            return
        self._pop_render(name, None, roww)
        if addr not in self.pfetching:
            self.pfetching.add(addr)

            def work():
                try:
                    teams = parse_players(fetch(SERVER_URL.format(addr)))
                    self.q.put(("players", addr, teams))
                except Exception as e:
                    self.q.put(("players", addr, str(e)))
            threading.Thread(target=work, daemon=True).start()

    def _pop_render(self, name, res, roww):
        if self.pop is None:
            self.pop = tk.Toplevel(self.root)
            self.pop.overrideredirect(True)
            self.pop.attributes("-topmost", True)
            self.pop.attributes("-alpha", 0.96)
            self.pop.configure(bg=ACC)
            self.pop.withdraw()
            self.pop_inner = tk.Frame(self.pop, bg=BG)
            self.pop_inner.pack(padx=1, pady=1)
        for w in self.pop_inner.winfo_children():
            w.destroy()
        tk.Label(self.pop_inner, text=trunc(name, 44), font=("Segoe UI", 9, "bold"),
                 fg=ACC, bg=BG, anchor="w").pack(fill="x", padx=8, pady=(6, 2))
        if res is None:
            tk.Label(self.pop_inner, text="loading players…", font=("Segoe UI", 9),
                     fg=DIM, bg=BG).pack(padx=8, pady=(0, 6), anchor="w")
        elif isinstance(res, str):
            tk.Label(self.pop_inner, text=trunc("error: " + res, 44),
                     font=("Segoe UI", 9), fg=RED, bg=BG).pack(padx=8, pady=(0, 6), anchor="w")
        elif sum(len(t["players"]) for t in res) == 0:
            tk.Label(self.pop_inner, text="no players online", font=("Segoe UI", 9),
                     fg=DIM, bg=BG).pack(padx=8, pady=(0, 6), anchor="w")
        else:
            cols = tk.Frame(self.pop_inner, bg=BG)
            cols.pack(padx=8, pady=(0, 6), anchor="n")
            for t in res:
                col = tk.Frame(cols, bg=BG)
                col.pack(side="left", anchor="n", padx=(0, 12))
                tk.Label(col, text=f"{t['army']} · {len(t['players'])}",
                         font=self.f_label, fg=ACC2, bg=BG).pack(anchor="w")
                for pname, active in t["players"][:MAX_TEAM_ROWS]:
                    tk.Label(col, text=trunc(pname, 20), font=("Segoe UI", 9),
                             fg=TXT if active else DIM, bg=BG).pack(anchor="w")
                extra = len(t["players"]) - MAX_TEAM_ROWS
                if extra > 0:
                    tk.Label(col, text=f"+{extra} more", font=("Segoe UI", 9),
                             fg=DIM, bg=BG).pack(anchor="w")
        self._place_pop(roww)
        self.pop.deiconify()

    def _place_pop(self, roww):
        self.pop.update_idletasks()
        pw, ph = self.pop.winfo_reqwidth(), self.pop.winfo_reqheight()
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw = self.root.winfo_width()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = rx + rw + 6
        if x + pw > sw:
            x = rx - pw - 6
        if x < 0:
            x = max(0, sw - pw)
        try:
            y = roww.winfo_rooty()
        except Exception:
            y = ry
        if y + ph > sh:
            y = max(0, sh - ph - 10)
        self.pop.geometry(f"+{x}+{y}")


def main():
    if "--players" in sys.argv:
        addr = sys.argv[sys.argv.index("--players") + 1]
        for t in parse_players(fetch(SERVER_URL.format(addr))):
            print(f"{t['army']} - {len(t['players'])} players")
            for n, active in t["players"]:
                print("  ", n, "" if active else "(idle)")
        return
    if "--once" in sys.argv:
        data = gather()
        print("DOGFIGHT:")
        for s in data["dogfight"]:
            print(f"  {s['players']:>3}  {s['name']}  ({s['addr']})")
        if data["dogfight_err"]:
            print("  ERR:", data["dogfight_err"])
        print("RANKED POPULATED:")
        for s in (data["ranked"] or [])[:20]:
            print(f"  {s['players']:>3}/{s['max']:<3} {s['name'][:40]:<40} {s['map']}")
        if data["ranked_err"]:
            print("  ERR:", data["ranked_err"])
        return
    if another_instance_running():
        focus_existing()
        return
    self_install()
    root = tk.Tk()
    Overlay(root)
    root.mainloop()


if __name__ == "__main__":
    main()
