"""
Hatcher Auto Register + Auto Verify + Auto Create Agent
=========================================================
- 1 proxy = 1 akun, tidak reuse proxy
- Tidak pernah direct connection
- Auto ganti proxy jika mati di tengah proses
- Random UA & Accept-Language per akun
- Auto create agent setelah register sukses
- UI berwarna (Windows & Ubuntu WSL compatible)
- Prompt jumlah akun saat startup
- Output APPEND ke file (tidak pernah hapus/reset)
"""

import requests
import json
import time
import random
import string
import re
import logging
import os
import sys
from datetime import datetime
from typing import Optional, Tuple
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ══════════════════════════════════════════════════════════════════════
#  WARNA & UI  (Windows CMD/PowerShell + Ubuntu WSL compatible)
# ══════════════════════════════════════════════════════════════════════
def _enable_windows_ansi():
    """Aktifkan ANSI di Windows CMD/PowerShell."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

_enable_windows_ansi()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class C:
    """ANSI color codes — bekerja di Windows 10+, Linux, WSL."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

    # Foreground
    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    # Bright foreground
    BRED    = "\033[91m"
    BGREEN  = "\033[92m"
    BYELLOW = "\033[93m"
    BBLUE   = "\033[94m"
    BMAGENTA= "\033[95m"
    BCYAN   = "\033[96m"
    BWHITE  = "\033[97m"

    # Background
    BG_BLACK  = "\033[40m"
    BG_RED    = "\033[41m"
    BG_GREEN  = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE   = "\033[44m"
    BG_MAGENTA= "\033[45m"
    BG_CYAN   = "\033[46m"

def cp(text: str, color: str, bold: bool = False) -> str:
    """Wrap text dengan warna ANSI."""
    b = C.BOLD if bold else ""
    return f"{b}{color}{text}{C.RESET}"

def cprint(text: str, color: str = C.WHITE, bold: bool = False):
    """Print berwarna ke stdout."""
    print(cp(text, color, bold))

def csep(char: str = "─", width: int = 65, color: str = C.BLUE) -> str:
    return cp(char * width, color)

def cbox(title: str, color: str = C.CYAN) -> str:
    w   = 63
    bar = cp("═" * w, color, True)
    mid = cp(f"║  {title:<{w-4}}║", color, True)
    return f"{cp('╔', color, True)}{bar}{cp('╗', color, True)}\n{mid}\n{cp('╚', color, True)}{bar}{cp('╝', color, True)}"



# ══════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════
REFERRAL_CODE        = "9b84cb45"
HATCHER_BASE_API     = "https://api.hatcher.host"
HATCHER_FRONTEND     = "https://hatcher.host"
TEMPMAIL_BASE_URL    = "https://api.tempmail.lol"
TEMPMAIL_API_KEY     = ""

OUTPUT_FILE          = "registered_accounts.json"
AGENT_OUTPUT_FILE    = "agent_results.json"
PROXY_FILE           = "proxies_alive.txt"
LOG_FILE             = "register.log"
FAILED_PROXY_FILE    = "failed_proxies.txt"
DEBUG_EMAIL_DIR      = "debug_emails"

DELAY_MIN            = 8
DELAY_MAX            = 20
DELAY_BETWEEN_ACCS   = 30
DELAY_JITTER         = 3
MAX_RETRIES          = 3
RETRY_BACKOFF_BASE   = 5
RATE_LIMIT_PAUSE     = 120

USE_PROXY            = True
PROXY_TEST_TIMEOUT   = 12   # diperkecil: proxy lambat langsung gugur (hemat waktu)
# Test URL wajib HTTPS agar proxy yang tidak support SSL langsung gugur
PROXY_TEST_URLS      = [
    "https://api.ipify.org?format=json",   # HTTPS — wajib lolos SSL
    "https://httpbin.org/ip",              # HTTPS fallback
    "http://ip-api.com/json",             # HTTP fallback terakhir
]
PROXY_MAX_TEST       = 15

POLL_INTERVAL_SEC    = 8
POLL_MAX_WAIT_SEC    = 300

# Agent config
AGENT_NAME_TEMPLATE  = "{username} agent"
AGENT_DESCRIPTION    = "Auto-created AI agent"
AGENT_SYSTEM_PROMPT  = (
    "You are a helpful and friendly AI assistant. "
    "Answer questions clearly and concisely."
)
AGENT_MODEL          = "gpt-4o-mini"
AGENT_IS_PUBLIC      = True

# ══════════════════════════════════════════════════════════════════════
#  LOGGING — output ke file saja (console pakai cprint berwarna)
# ══════════════════════════════════════════════════════════════════════
for _d in [DEBUG_EMAIL_DIR, "backups"]:
    os.makedirs(_d, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")]
)
log = logging.getLogger(__name__)



# ══════════════════════════════════════════════════════════════════════
#  PRINT HELPERS  (colored console output)
# ══════════════════════════════════════════════════════════════════════
def p_info(msg: str):
    log.info(msg)
    print(f"  {cp('[INFO]', C.BCYAN, True)}  {msg}")

def p_ok(msg: str):
    log.info(msg)
    print(f"  {cp('[OK]', C.BGREEN, True)}    {msg}")

def p_warn(msg: str):
    log.warning(msg)
    print(f"  {cp('[WARN]', C.BYELLOW, True)}  {msg}")

def p_err(msg: str):
    log.error(msg)
    print(f"  {cp('[ERR]', C.BRED, True)}    {msg}")

def p_step(step: int, total: int, msg: str):
    log.info(f"[STEP {step}/{total}] {msg}")
    label = cp(f"[STEP {step}/{total}]", C.BMAGENTA, True)
    print(f"\n  {label} {cp(msg, C.WHITE, True)}")

def p_proxy(msg: str):
    log.info(msg)
    print(f"  {cp('[PROXY]', C.BBLUE, True)} {msg}")

def p_agent(msg: str):
    log.info(msg)
    print(f"  {cp('[AGENT]', C.BMAGENTA, True)} {msg}")

def p_wait(msg: str):
    log.info(msg)
    print(f"  {cp('[WAIT]', C.DIM + C.WHITE)}  {msg}")

def p_sep(char: str = "─", width: int = 65, color: str = C.BLUE):
    print(csep(char, width, color))

def p_account_header(idx: int, total: int):
    print(f"\n{csep('═', 65, C.CYAN)}")
    label = cp(f"  AKUN [{idx}/{total}]", C.BWHITE, True)
    print(f"{cp('  ▶', C.BGREEN, True)} {label}")
    print(csep("─", 65, C.BLUE))



# ══════════════════════════════════════════════════════════════════════
#  BANNER
# ══════════════════════════════════════════════════════════════════════
def print_banner():
    os.system("cls" if sys.platform == "win32" else "clear")
    banner = f"""
{cp('╔══════════════════════════════════════════════════════════════════╗', C.BCYAN, True)}
{cp('║', C.BCYAN, True)}  {cp('██╗  ██╗ █████╗ ████████╗ ██████╗██╗  ██╗███████╗██████╗  ', C.BGREEN, True)}{cp('║', C.BCYAN, True)}
{cp('║', C.BCYAN, True)}  {cp('██║  ██║██╔══██╗╚══██╔══╝██╔════╝██║  ██║██╔════╝██╔══██╗ ', C.BGREEN, True)}{cp('║', C.BCYAN, True)}
{cp('║', C.BCYAN, True)}  {cp('███████║███████║   ██║   ██║     ███████║█████╗  ██████╔╝ ', C.BGREEN, True)}{cp('║', C.BCYAN, True)}
{cp('║', C.BCYAN, True)}  {cp('██╔══██║██╔══██║   ██║   ██║     ██╔══██║██╔══╝  ██╔══██╗ ', C.BGREEN, True)}{cp('║', C.BCYAN, True)}
{cp('║', C.BCYAN, True)}  {cp('██║  ██║██║  ██║   ██║   ╚██████╗██║  ██║███████╗██║  ██║ ', C.BGREEN, True)}{cp('║', C.BCYAN, True)}
{cp('║', C.BCYAN, True)}  {cp('╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝', C.BGREEN, True)}{cp('║', C.BCYAN, True)}
{cp('║', C.BCYAN, True)}  {cp('Auto Register  +  Auto Verify  +  Auto Create Agent', C.BYELLOW, True)}          {cp('║', C.BCYAN, True)}
{cp('║', C.BCYAN, True)}  {cp('1 Proxy = 1 Akun  |  No Direct Connection  |  Auto Retry', C.DIM + C.WHITE)}     {cp('║', C.BCYAN, True)}
{cp('╚══════════════════════════════════════════════════════════════════╝', C.BCYAN, True)}
"""
    print(banner)

# ══════════════════════════════════════════════════════════════════════
#  PROMPT JUMLAH AKUN
# ══════════════════════════════════════════════════════════════════════
def ask_account_count() -> int:
    """Tanya user mau buat berapa akun di sesi ini."""
    print(csep("─", 65, C.BLUE))
    print(f"  {cp('⚙  KONFIGURASI SESI', C.BYELLOW, True)}")
    print(csep("─", 65, C.BLUE))
    print(f"  {cp('Referral Code :', C.DIM + C.WHITE)} {cp(REFERRAL_CODE, C.BCYAN, True)}")
    print(f"  {cp('Proxy File    :', C.DIM + C.WHITE)} {cp(PROXY_FILE, C.BBLUE, True)}")
    print(f"  {cp('Output File   :', C.DIM + C.WHITE)} {cp(OUTPUT_FILE, C.BWHITE)} {cp('(append mode)', C.BGREEN)}")
    print(f"  {cp('Agent Output  :', C.DIM + C.WHITE)} {cp(AGENT_OUTPUT_FILE, C.BWHITE)} {cp('(append mode)', C.BGREEN)}")
    print(csep("─", 65, C.BLUE))

    while True:
        try:
            prompt = cp("\n  ➤  Berapa akun yang ingin dibuat sesi ini? ", C.BYELLOW, True)
            raw = input(prompt).strip()
            n   = int(raw)
            if n <= 0:
                print(cp("  ✗  Masukkan angka lebih dari 0!", C.BRED))
                continue
            print(f"\n  {cp('✓  Target sesi ini:', C.BGREEN, True)} {cp(str(n) + ' akun', C.BWHITE, True)}")
            print(csep("─", 65, C.BLUE))
            return n
        except ValueError:
            print(cp("  ✗  Input tidak valid, masukkan angka bulat!", C.BRED))
        except (KeyboardInterrupt, EOFError):
            print(cp("\n\n  Script dihentikan oleh user.", C.BYELLOW))
            sys.exit(0)



# ══════════════════════════════════════════════════════════════════════
#  USER-AGENT & ACCEPT-LANGUAGE POOLS
# ══════════════════════════════════════════════════════════════════════
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
]

ACCEPT_LANGUAGES = [
    "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "id-ID,id;q=0.9,en;q=0.8",
    "en-US,en;q=0.9,id;q=0.8",
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9,id-ID;q=0.8,id;q=0.7",
    "id,en-US;q=0.9,en;q=0.8",
    "id-ID,id;q=0.8,en-US;q=0.5,en;q=0.3",
    "en-US,en;q=0.8,id-ID;q=0.6,id;q=0.4",
]



# ══════════════════════════════════════════════════════════════════════
#  HEADER FACTORY
# ══════════════════════════════════════════════════════════════════════
class HeaderFactory:
    def __init__(self):
        self.referral_code = REFERRAL_CODE

    def _get_chrome_version(self, ua: str) -> str:
        m = re.search(r"Chrome/(\d+)", ua)
        return m.group(1) if m else "120"

    def _is_mobile(self, ua: str) -> bool:
        return any(x in ua for x in ["Mobile", "Android", "iPhone", "iPad"])

    def build(self, ua: Optional[str] = None, referer: str = None,
              accept_language: Optional[str] = None) -> dict:
        if ua is None:
            ua = random.choice(USER_AGENTS)
        is_chrome  = "Chrome" in ua and "Edg" not in ua
        is_edge    = "Edg" in ua
        is_firefox = "Firefox" in ua
        is_mobile  = self._is_mobile(ua)
        lang = accept_language if accept_language else random.choice(ACCEPT_LANGUAGES)
        if referer is None:
            referer = f"{HATCHER_FRONTEND}/register?ref={self.referral_code}"

        headers = {
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": lang,
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type":    "application/json",
            "Origin":          HATCHER_FRONTEND,
            "Referer":         referer,
            "User-Agent":      ua,
            "Connection":      "keep-alive",
        }
        if random.random() > 0.5:
            headers["DNT"] = "1"
        if is_chrome or is_edge:
            cv = self._get_chrome_version(ua)
            headers.update({"Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors",
                            "Sec-Fetch-Site": "same-site"})
            brand = "Microsoft Edge" if is_edge else "Google Chrome"
            headers["Sec-CH-UA"] = f'"Not_A Brand";v="8", "Chromium";v="{cv}", "{brand}";v="{cv}"'
            if "Windows" in ua:    headers["Sec-CH-UA-Platform"] = '"Windows"'
            elif "Macintosh" in ua: headers["Sec-CH-UA-Platform"] = '"macOS"'
            elif "Android" in ua:   headers["Sec-CH-UA-Platform"] = '"Android"'
            else:                   headers["Sec-CH-UA-Platform"] = '"Linux"'
            headers["Sec-CH-UA-Mobile"] = "?1" if is_mobile else "?0"
        cc = random.choice(["no-cache", "max-age=0", None])
        if cc:
            headers["Cache-Control"] = cc
        if random.random() > 0.6:
            headers["Pragma"] = "no-cache"
        if is_firefox:
            headers["TE"] = "trailers"
        return headers



# ══════════════════════════════════════════════════════════════════════
#  PROXY MANAGER
# ══════════════════════════════════════════════════════════════════════
class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.failed  = set()
        self.used    = set()
        self.working = []
        self._load()
        self._initial_test()

    def _load(self):
        if not os.path.exists(PROXY_FILE):
            p_err(f"'{PROXY_FILE}' tidak ada! Script wajib proxy.")
            return
        failed_set = set()
        if os.path.exists(FAILED_PROXY_FILE):
            with open(FAILED_PROXY_FILE) as f:
                failed_set = {l.strip() for l in f if l.strip()}
        loaded = []
        with open(PROXY_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                p = self._normalize(line)
                if p and p not in failed_set:
                    loaded.append(p)
        random.shuffle(loaded)
        self.proxies = loaded
        p_proxy(f"Loaded {cp(str(len(self.proxies)), C.BWHITE, True)} proxy dari '{PROXY_FILE}'")

    def _initial_test(self):
        if not self.proxies:
            return
        MAX_TEST = min(PROXY_MAX_TEST, len(self.proxies))
        p_proxy(f"Testing {cp(str(MAX_TEST), C.BYELLOW, True)} proxy awal...")
        for i in range(MAX_TEST):
            p = self.proxies[i]
            short = p[:50]
            if self._do_test(p):
                self.working.append(p)
                p_proxy(f"{cp('✓', C.BGREEN, True)} [{i+1}/{MAX_TEST}] {cp(short, C.DIM+C.WHITE)} → {cp('HIDUP', C.BGREEN, True)}")
            else:
                p_proxy(f"{cp('✗', C.BRED, True)} [{i+1}/{MAX_TEST}] {cp(short, C.DIM+C.WHITE)} → {cp('MATI', C.BRED)}")
        if self.working:
            p_ok(f"{len(self.working)} proxy aktif siap dipakai")
            random.shuffle(self.working)
        else:
            p_warn(f"Tidak ada proxy yang lulus test! Cek '{PROXY_FILE}'")

    def _do_test(self, proxy_url: str) -> bool:
        """
        Test proxy dengan request HTTPS ke api.hatcher.host terlebih dahulu.
        Proxy yang tidak bisa handle SSL/HTTPS langsung gugur — tidak boleh lolos.
        """
        proxy_dict = self.get_proxy_dict(proxy_url)

        # ── Prioritas: test langsung ke target domain ─────────────────
        # Ini paling relevan — kalau bisa konek ke hatcher, pasti bisa dipakai
        try:
            r = requests.get(
                "https://api.hatcher.host/health",
                proxies=proxy_dict,
                timeout=PROXY_TEST_TIMEOUT,
                headers={"User-Agent": random.choice(USER_AGENTS)},
                verify=False  # kita disable SSL verify, tapi koneksi HTTPS harus tetap bisa
            )
            # Status apapun (200, 404, 405, dll) = proxy bisa reach target = LULUS
            return True
        except requests.exceptions.SSLError:
            # Proxy tidak bisa handle HTTPS sama sekali → GUGUR
            return False
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout):
            pass  # Timeout ke hatcher, coba fallback
        except requests.exceptions.ProxyError:
            return False  # Proxy error fatal → GUGUR
        except Exception:
            pass  # Error lain, coba fallback

        # ── Fallback: test ke IP-check HTTPS ─────────────────────────
        for test_url in PROXY_TEST_URLS:
            try:
                r = requests.get(
                    test_url,
                    proxies=proxy_dict,
                    timeout=PROXY_TEST_TIMEOUT,
                    headers={"User-Agent": random.choice(USER_AGENTS)},
                    verify=False
                )
                if r.status_code == 200:
                    return True
            except requests.exceptions.SSLError:
                # Proxy tidak bisa handle SSL → GUGUR langsung
                return False
            except requests.exceptions.ConnectTimeout:
                continue
            except requests.exceptions.ProxyError:
                return False
            except Exception:
                continue

        return False

    def _normalize(self, raw: str) -> Optional[str]:
        raw = raw.strip()
        if not raw:
            return None
        if raw.startswith(("http://", "https://", "socks4://", "socks5://")):
            return raw
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d{2,5}$", raw):
            return f"http://{raw}"
        parts = raw.split(":")
        if len(parts) == 4:
            ip, port, user, pwd = parts
            return f"http://{user}:{pwd}@{ip}:{port}"
        return None

    def get_proxy_dict(self, p: str) -> dict:
        return {"http": p, "https": p}

    def mark_failed(self, p: str):
        if not p or p in self.failed:
            return
        self.failed.add(p)
        with open(FAILED_PROXY_FILE, "a") as f:
            f.write(p + "\n")
        p_warn(f"Proxy mati → {cp(p[:50], C.DIM+C.WHITE)}")
        if p in self.working: self.working.remove(p)
        if p in self.proxies:  self.proxies.remove(p)
        self.used.discard(p)
        p_proxy(f"Sisa working: {cp(str(len(self.working)), C.BYELLOW)} | Total: {cp(str(len(self.proxies)), C.BWHITE)}")



    def get_fresh_proxy(self) -> Optional[str]:
        """Ambil proxy BARU yang belum pernah dipakai akun manapun."""
        available = [p for p in self.working if p not in self.used]
        if available:
            proxy = random.choice(available)
            self.used.add(proxy)
            p_proxy(f"Pakai fresh proxy: {cp(proxy[:50], C.BBLUE, True)}")
            return proxy

        # working habis, test dari pool
        untried = [p for p in self.proxies if p not in self.used and p not in self.failed]
        if untried:
            random.shuffle(untried)
            for p in untried[:min(20, len(untried))]:
                p_proxy(f"Test fresh proxy: {cp(p[:50], C.DIM+C.WHITE)}")
                if self._do_test(p):
                    if p not in self.working: self.working.append(p)
                    self.used.add(p)
                    p_proxy(f"{cp('✓', C.BGREEN, True)} Fresh proxy OK: {cp(p[:50], C.BBLUE, True)}")
                    return p
                else:
                    self.mark_failed(p)

        # paksa test ulang sisa pool
        all_remaining = [p for p in self.proxies if p not in self.failed]
        if all_remaining:
            p_warn("Semua proxy sudah terpakai, test ulang sisa pool...")
            random.shuffle(all_remaining)
            for p in all_remaining[:min(30, len(all_remaining))]:
                if self._do_test(p):
                    if p not in self.working: self.working.append(p)
                    self.used.add(p)
                    p_proxy(f"{cp('✓', C.BGREEN, True)} Re-test OK: {cp(p[:50], C.BBLUE, True)}")
                    return p
                else:
                    self.mark_failed(p)

        p_err("KRITIS: Tidak ada proxy tersedia! Direct connection DILARANG.")
        return None

    def find_alive_proxy_for_retry(self, exclude: str = None) -> Optional[str]:
        """Cari proxy hidup untuk melanjutkan proses yang gagal."""
        p_warn("Mencari proxy hidup untuk retry...")
        candidates = [p for p in self.proxies if p not in self.failed and p != exclude]
        random.shuffle(candidates)
        for p in candidates[:min(15, len(candidates))]:
            p_proxy(f"Test retry: {cp(p[:50], C.DIM+C.WHITE)}")
            if self._do_test(p):
                if p not in self.working: self.working.append(p)
                p_proxy(f"{cp('✓', C.BGREEN, True)} Proxy retry OK: {cp(p[:50], C.BBLUE, True)}")
                return p
            else:
                self.mark_failed(p)
        p_err("Tidak ada proxy hidup untuk retry!")
        return None

    def replenish_working(self, min_count: int = 3):
        if len(self.working) >= min_count or not self.proxies:
            return
        needed = min_count - len(self.working)
        candidates = [p for p in self.proxies if p not in self.working and p not in self.failed]
        added = 0
        for p in candidates[:min(needed * 3, len(candidates))]:
            if self._do_test(p):
                self.working.append(p)
                added += 1
                if added >= needed:
                    break

    @property
    def count(self):
        return len(self.proxies)



# ══════════════════════════════════════════════════════════════════════
#  HUMAN DELAY
# ══════════════════════════════════════════════════════════════════════
class HumanDelay:
    def __init__(self):
        self.request_count = 0

    def _jitter(self, base: float) -> float:
        return max(2.0, base + random.gauss(0, DELAY_JITTER))

    def short(self):
        t = self._jitter(random.uniform(2, 5))
        p_wait(f"Tunggu {cp(f'{t:.1f}s', C.BYELLOW)}...")
        time.sleep(t)

    def medium(self):
        t = self._jitter(random.uniform(DELAY_MIN, DELAY_MAX))
        p_wait(f"Tunggu {cp(f'{t:.1f}s', C.BYELLOW)}...")
        time.sleep(t)

    def between_accounts(self):
        self.request_count += 1
        if self.request_count % 5 == 0:
            t = self._jitter(DELAY_BETWEEN_ACCS + random.uniform(30, 90))
            p_wait(f"{cp('Pause panjang', C.BYELLOW)} {cp(f'{t:.0f}s', C.BRED, True)} (simulate user break)...")
        else:
            t = self._jitter(random.uniform(DELAY_BETWEEN_ACCS, DELAY_BETWEEN_ACCS * 2))
            p_wait(f"Jeda antar akun {cp(f'{t:.0f}s', C.BYELLOW)}...")
        time.sleep(t)

    def rate_limit_pause(self, retry_after: int = RATE_LIMIT_PAUSE):
        t = retry_after + random.uniform(10, 30)
        p_warn(f"Rate limited! Pause {cp(f'{t:.0f}s', C.BRED, True)}...")
        time.sleep(t)

    def typing_simulation(self):
        for _ in range(random.randint(2, 5)):
            time.sleep(random.uniform(0.1, 0.4))


# ══════════════════════════════════════════════════════════════════════
#  SESSION MANAGER
# ══════════════════════════════════════════════════════════════════════
class SessionManager:
    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager  = proxy_manager
        self.header_factory = HeaderFactory()
        self.session        = None
        self.current_proxy  = None
        self.current_ua     = None
        self.current_lang   = None
        self.account_count  = 0
        self._create_new_session()

    def _create_new_session(self, proxy_override: str = None):
        if self.session:
            self.session.close()
        self.current_ua   = random.choice(USER_AGENTS)
        self.current_lang = random.choice(ACCEPT_LANGUAGES)
        p_info(f"UA   : {cp(self.current_ua[:65]+'...', C.DIM+C.WHITE)}")
        p_info(f"Lang : {cp(self.current_lang, C.DIM+C.WHITE)}")

        self.session = requests.Session()
        # Disable SSL verification globally untuk session ini
        # (diperlukan karena banyak proxy tidak support SSL chain dengan benar)
        self.session.verify = False
        if proxy_override:
            self.current_proxy = proxy_override
        elif USE_PROXY:
            self.current_proxy = self.proxy_manager.get_fresh_proxy()
        else:
            self.current_proxy = None

        if self.current_proxy:
            self.session.proxies.update(self.proxy_manager.get_proxy_dict(self.current_proxy))
            p_proxy(f"Session proxy: {cp(self.current_proxy[:60], C.BBLUE, True)}")
        else:
            p_err("FATAL: Tidak ada proxy tersedia. Proses dihentikan!")
            raise RuntimeError("Tidak ada proxy. Tambahkan proxy ke proxies_alive.txt!")
        self.session.timeout = 20

    def rotate_for_new_account(self):
        self.account_count += 1
        p_info(f"Rotate session untuk akun #{cp(str(self.account_count), C.BWHITE, True)}")
        self._create_new_session()

    def switch_proxy_on_failure(self):
        failed = self.current_proxy
        if failed:
            self.proxy_manager.mark_failed(failed)
            self.proxy_manager.replenish_working(min_count=3)
        new_proxy = self.proxy_manager.find_alive_proxy_for_retry(exclude=failed)
        if not new_proxy:
            p_err("Tidak ada proxy hidup! Proses berhenti.")
            raise RuntimeError("Proxy habis semua!")
        self.proxy_manager.used.add(new_proxy)
        self.current_proxy = new_proxy
        self.session.close()
        self.session = requests.Session()
        self.session.verify = False
        self.session.proxies.update(self.proxy_manager.get_proxy_dict(new_proxy))
        self.session.timeout = 20
        p_proxy(f"{cp('✓', C.BGREEN, True)} Switched ke proxy baru: {cp(new_proxy[:55], C.BBLUE, True)}")

    def get(self, url: str, **kwargs) -> requests.Response:
        referer = kwargs.pop("referer", None)
        h = self.header_factory.build(self.current_ua, referer=referer, accept_language=self.current_lang)
        if "headers" in kwargs: h.update(kwargs.pop("headers"))
        return self.session.get(url, headers=h, verify=False, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        referer = kwargs.pop("referer", None)
        h = self.header_factory.build(self.current_ua, referer=referer, accept_language=self.current_lang)
        if "headers" in kwargs: h.update(kwargs.pop("headers"))
        return self.session.post(url, headers=h, verify=False, **kwargs)

    def mark_proxy_failed(self):
        self.switch_proxy_on_failure()

    def close(self):
        if self.session:
            self.session.close()



# ══════════════════════════════════════════════════════════════════════
#  TEMPMAIL CLIENT
# ══════════════════════════════════════════════════════════════════════
class TempMailClient:
    def __init__(self):
        self.api_key  = TEMPMAIL_API_KEY.strip()
        self.has_key  = bool(self.api_key)
        self._session = requests.Session()
        p_info(f"TempMail mode: {cp('PAID', C.BGREEN, True) if self.has_key else cp('FREE', C.BYELLOW)}")

    def _headers(self) -> dict:
        h = {"Accept": "application/json", "Accept-Encoding": "gzip, deflate, br",
             "Accept-Language": random.choice(ACCEPT_LANGUAGES),
             "User-Agent": random.choice(USER_AGENTS)}
        if self.has_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def generate(self) -> Optional[Tuple[str, str]]:
        url = f"{TEMPMAIL_BASE_URL}/generate/"
        for attempt in range(MAX_RETRIES):
            try:
                r = self._session.get(url, headers=self._headers(), timeout=20, verify=False)
                if r.status_code == 200:
                    data = r.json()
                    addr, tok = data.get("address", ""), data.get("token", "")
                    if addr and tok:
                        p_ok(f"Inbox: {cp(addr, C.BCYAN, True)}")
                        return addr, tok
                    return None
                elif r.status_code == 429:
                    time.sleep(35 + random.uniform(5, 15))
                    continue
                elif r.status_code == 401:
                    p_err("TempMail 401 - API key salah!")
                    return None
                else:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))
            except Exception as e:
                p_err(f"TempMail generate error: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF_BASE)
        return None

    def fetch(self, token: str) -> Tuple[list, str]:
        url = f"{TEMPMAIL_BASE_URL}/auth/{token}"
        try:
            r = self._session.get(url, headers=self._headers(), timeout=20, verify=False)
            if r.status_code == 200:
                data      = r.json()
                new_token = data.get("token", token)
                emails    = data.get("email", [])
                if not isinstance(emails, list): emails = []
                if emails:
                    p_info(f"{cp(str(len(emails)), C.BGREEN, True)} email masuk!")
                return emails, new_token
            elif r.status_code == 429:
                time.sleep(25)
                return [], token
            return [], token
        except Exception as e:
            p_err(f"TempMail fetch error: {e}")
            return [], token

    def wait_for_email(self, token: str, email_address: str,
                       timeout: int = POLL_MAX_WAIT_SEC) -> Tuple[Optional[str], str]:
        p_info(f"Polling inbox: {cp(email_address, C.BCYAN)} | Max {cp(str(timeout)+'s', C.BYELLOW)}")
        cur_token = token
        start     = time.time()
        n         = 0
        while True:
            elapsed = time.time() - start
            if elapsed >= timeout:
                p_warn(f"Timeout polling ({elapsed:.0f}s)")
                return None, cur_token
            n += 1
            bar   = f"[{int(elapsed)}/{timeout}s]"
            print(f"  {cp('[POLL]', C.BBLUE)} {cp(f'#{n}', C.BWHITE)} {cp(bar, C.DIM+C.WHITE)}", end="\r")
            emails, cur_token = self.fetch(cur_token)
            for mail in emails:
                mail_from = mail.get("from", "")
                mail_subj = mail.get("subject", "")
                mail_body = mail.get("body", "")
                print()
                p_info(f"Mail from: {cp(mail_from, C.BCYAN)} | Subject: {cp(mail_subj[:50], C.BWHITE)}")
                fname = os.path.join(DEBUG_EMAIL_DIR, f"email_{mail.get('id', n)}_{int(time.time())}.html")
                with open(fname, "w", encoding="utf-8") as fw:
                    fw.write(f"<!-- From: {mail_from} -->\n<!-- Subject: {mail_subj} -->\n{mail_body}")
                is_hatcher = any(kw in mail_from.lower() for kw in ["hatcher", "noreply", "no-reply"])
                is_verify  = any(kw in mail_subj.lower() for kw in ["verif", "confirm", "activate", "welcome"])
                if is_hatcher or is_verify:
                    link = self._extract_link(mail_body)
                    if link:
                        p_ok(f"Link verifikasi ditemukan!")
                        return link, cur_token
                    p_warn("Email cocok tapi link tidak ditemukan!")
            wait = max(5.0, POLL_INTERVAL_SEC + random.uniform(-2, 3))
            time.sleep(wait)

    def _extract_link(self, body: str) -> Optional[str]:
        if not body: return None
        for pattern in [
            r'https?://(?:api\.)?hatcher\.host[^\s"\'<>\]]*verif[^\s"\'<>\]]*',
            r'https?://hatcher\.host/verify-email[^\s"\'<>\]]*',
            r'https?://(?:api\.)?hatcher\.host[^\s"\'<>\]]*[?&]token=[A-Za-z0-9_\-\.]{10,}',
        ]:
            m = re.findall(pattern, body, re.IGNORECASE)
            if m: return m[0].rstrip('.,;:)\'">\r\n')
        try:
            soup = BeautifulSoup(body, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text(strip=True).lower()
                if "hatcher" in href.lower() and any(kw in href.lower() for kw in ["verif", "token"]):
                    return href
                if any(kw in text for kw in ["verif", "confirm", "click here"]):
                    if href.startswith("http"): return href
        except Exception:
            pass
        return None

    def close(self):
        self._session.close()



# ══════════════════════════════════════════════════════════════════════
#  VERIFIER
# ══════════════════════════════════════════════════════════════════════
class HatcherVerifier:
    VERIFY_API_ENDPOINTS = [
        ("POST", f"{HATCHER_BASE_API}/auth/verify-email",           "body"),
        ("POST", f"{HATCHER_BASE_API}/auth/verify",                 "body"),
        ("POST", f"{HATCHER_BASE_API}/auth/email/verify",           "body"),
        ("POST", f"{HATCHER_BASE_API}/users/verify-email",          "body"),
        ("GET",  f"{HATCHER_BASE_API}/auth/verify-email",           "query"),
        ("GET",  f"{HATCHER_BASE_API}/auth/verify",                 "query"),
        ("GET",  f"{HATCHER_BASE_API}/auth/email/verify",           "query"),
        ("GET",  f"{HATCHER_BASE_API}/auth/verify-email/{{token}}", "path"),
        ("GET",  f"{HATCHER_BASE_API}/auth/verify/{{token}}",       "path"),
    ]

    def __init__(self, sm: SessionManager):
        self.sm = sm

    def _make_headers(self) -> dict:
        return self.sm.header_factory.build(
            self.sm.current_ua,
            referer=f"{HATCHER_FRONTEND}/verify-email",
            accept_language=self.sm.current_lang)

    def verify(self, verify_url: str) -> Tuple[bool, str]:
        token = self._extract_token(verify_url)
        if not token:
            p_err(f"Tidak bisa ekstrak token dari: {verify_url}")
            return False, "no_token"
        p_info(f"Token: {cp(token[:25]+'...', C.DIM+C.WHITE)}")
        for method, endpoint, style in self.VERIFY_API_ENDPOINTS:
            success, note = self._try_endpoint(method, endpoint, style, token)
            if success:
                p_ok(f"Verified via {cp(method, C.BGREEN)} {cp(endpoint[:55], C.DIM+C.WHITE)}")
                return True, f"{method}:{endpoint}"
            if note == "skip":
                continue
        p_err("Semua endpoint verify gagal!")
        return False, "all_failed"

    def _extract_token(self, url: str) -> Optional[str]:
        m = re.search(r'[?&]token=([A-Za-z0-9_\-\.]{10,})', url)
        if m: return m.group(1)
        m = re.search(r'/verif[^/]*/([A-Za-z0-9_\-\.]{10,})/?$', url, re.IGNORECASE)
        if m: return m.group(1)
        m = re.search(r'/([A-Za-z0-9_\-\.]{32,})/?$', url)
        if m: return m.group(1)
        return None

    def _try_endpoint(self, method, endpoint, style, token) -> Tuple[bool, str]:
        headers = self._make_headers()
        try:
            if style == "body":
                r = self.sm.session.post(endpoint, json={"token": token}, headers=headers,
                                         timeout=20, allow_redirects=True, verify=False)
            elif style == "query":
                r = self.sm.session.get(endpoint, params={"token": token}, headers=headers,
                                        timeout=20, allow_redirects=True, verify=False)
            elif style == "path":
                r = self.sm.session.get(endpoint.replace("{token}", token), headers=headers,
                                        timeout=20, allow_redirects=True, verify=False)
            else:
                return False, "skip"
            return self._check_response(r, token)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return False, "skip"
        except Exception:
            return False, "skip"

    def _check_response(self, r: requests.Response, token: str) -> Tuple[bool, str]:
        s = r.status_code
        if s == 404: return False, "skip"
        if s == 400:
            try:
                data = r.json(); msg = str(data).lower()
                if "already" in msg and "verif" in msg: return True, "already_verified"
                if "expired" in msg or "invalid" in msg: return False, "fail"
            except Exception:
                pass
            return False, "fail"
        if s in (200, 201, 204):
            try:
                data = r.json(); ds = str(data).lower()
                if data.get("error") or data.get("success") is False: return False, "fail"
                if any(kw in ds for kw in ["success", "verified", "true", "aktif"]): return True, "json_success"
                return True, "json_no_error"
            except ValueError:
                body = r.text.lower()
                if "<html" in body and ("__next" in body or "react" in body): return False, "skip"
                if any(kw in body for kw in ["success", "verified", "confirmed"]): return True, "html_success"
                if any(kw in body for kw in ["error", "invalid", "expired"]): return False, "fail"
                return False, "skip"
        if s in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "").lower()
            if any(kw in loc for kw in ["success", "verified", "dashboard", "login"]): return True, "redirect"
            return False, "skip"
        if s == 429:
            p_warn("Rate limited saat verify!")
            time.sleep(RATE_LIMIT_PAUSE)
            return False, "skip"
        return False, "skip"



# ══════════════════════════════════════════════════════════════════════
#  REGISTER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════
def make_username(email: str) -> str:
    local = re.sub(r"[^a-zA-Z0-9]", "", email.split("@")[0]).lower()
    local = re.sub(r"\d+$", "", local)
    if len(local) < 3:
        local = random.choice(["budi","andi","sari","nova"]) + str(random.randint(10, 99))
    return local[:30]

def make_password() -> str:
    chars = (random.choices(string.ascii_lowercase, k=4)
           + random.choices(string.ascii_uppercase, k=3)
           + random.choices(string.digits, k=3)
           + random.choices("@#$!%*?&", k=2))
    random.shuffle(chars)
    return "".join(chars)

def check_avail(sm: SessionManager, field: str, val: str, delay: HumanDelay) -> bool:
    url = f"{HATCHER_BASE_API}/auth/check-availability"
    for attempt in range(MAX_RETRIES):
        try:
            r = sm.get(url, params={field: val}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                ok   = data.get("available", not data.get("exists", False))
                status = cp("✓ tersedia", C.BGREEN, True) if ok else cp("✗ dipakai", C.BRED)
                p_info(f"{field} '{cp(val, C.BWHITE)}' → {status}")
                return ok
            elif r.status_code == 429:
                delay.rate_limit_pause(int(r.headers.get("Retry-After", RATE_LIMIT_PAUSE)))
                sm.mark_proxy_failed(); continue
            else:
                p_warn(f"check-availability [{r.status_code}]")
                return False
        except requests.exceptions.ProxyError:
            sm.mark_proxy_failed()
            if attempt < MAX_RETRIES - 1: time.sleep(RETRY_BACKOFF_BASE)
        except requests.exceptions.ConnectTimeout:
            if attempt < MAX_RETRIES - 1: time.sleep(RETRY_BACKOFF_BASE * (2**attempt))
        except Exception as e:
            p_err(f"check {field}: {e}"); return False
    return False

def resolve_username(sm: SessionManager, base: str, delay: HumanDelay) -> str:
    for _ in range(5):
        c = f"{base}{random.randint(10, 999)}"[:30]
        delay.short()
        if check_avail(sm, "username", c, delay):
            return c
    return f"{base}{int(time.time()) % 10000}"[:30]

def register(sm: SessionManager, email: str, username: str,
             password: str, delay: HumanDelay) -> dict:
    url     = f"{HATCHER_BASE_API}/auth/register"
    payload = {"email": email, "username": username,
               "password": password, "referralCode": REFERRAL_CODE}
    for attempt in range(MAX_RETRIES):
        try:
            delay.typing_simulation()
            r    = sm.post(url, json=payload, timeout=20)
            data = r.json() if r.content else {}
            if r.status_code in (200, 201):
                p_ok(f"Register sukses: {cp(email, C.BCYAN, True)}")
                return {"status": "success", "code": r.status_code, "data": data}
            elif r.status_code == 429:
                delay.rate_limit_pause(int(r.headers.get("Retry-After", RATE_LIMIT_PAUSE)))
                sm.mark_proxy_failed(); continue
            elif r.status_code == 503:
                p_warn(f"503 Server Error, retry {attempt+1}")
                if attempt < MAX_RETRIES - 1: time.sleep(RETRY_BACKOFF_BASE * (2**attempt))
                continue
            else:
                msg = data.get("error", r.text[:200])
                if "already" in str(msg).lower():
                    return {"status": "already_exists", "code": r.status_code, "data": data}
                if "taken" in str(msg).lower():
                    return {"status": "username_taken", "code": r.status_code, "data": data}
                p_warn(f"Register [{r.status_code}]: {msg}")
                return {"status": "failed", "code": r.status_code, "data": data}
        except requests.exceptions.ProxyError:
            p_warn(f"Proxy error register, ganti proxy (attempt {attempt+1})")
            sm.mark_proxy_failed()
            if attempt < MAX_RETRIES - 1: time.sleep(RETRY_BACKOFF_BASE)
        except requests.exceptions.ConnectTimeout:
            p_warn(f"Timeout register attempt {attempt+1}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_BASE * (2**attempt))
        except requests.exceptions.ConnectionError as e:
            p_warn(f"Connection error: {e}")
            sm.mark_proxy_failed()
            if attempt < MAX_RETRIES - 1: time.sleep(RETRY_BACKOFF_BASE)
        except Exception as e:
            p_err(f"Exception register: {e}")
            return {"status": "error", "error": str(e)}
    return {"status": "error", "error": f"Max retries ({MAX_RETRIES}) exceeded"}



# ══════════════════════════════════════════════════════════════════════
#  AUTO CREATE AGENT
# ══════════════════════════════════════════════════════════════════════
def _auth_headers_agent(token: str, ua: str, lang: str) -> dict:
    return {"Content-Type": "application/json", "Accept": "application/json",
            "Origin": "https://hatcher.host", "Referer": "https://hatcher.host/create",
            "User-Agent": ua, "Accept-Language": lang, "Authorization": f"Bearer {token}"}

def agent_login(session: requests.Session, email: str, password: str,
                ua: str, lang: str) -> Optional[dict]:
    url = f"{HATCHER_BASE_API}/auth/login"
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "Origin": "https://hatcher.host", "Referer": "https://hatcher.host/login",
               "User-Agent": ua, "Accept-Language": lang}
    try:
        r = session.post(url, headers=headers, json={"email": email, "password": password},
                         timeout=20, verify=False)
        data = r.json() if r.content else {}
        if r.status_code == 200 and data.get("success"):
            token = data["data"]["token"]
            user  = data["data"]["user"]
            p_agent(f"Login OK: {cp(email, C.BCYAN)} (id={cp(str(user['id']), C.BWHITE)})")
            return {"token": token, "refreshToken": data["data"].get("refreshToken"), "user": user}
        p_warn(f"Login agent gagal [{r.status_code}]: {data.get('error', r.text[:80])}")
        return None
    except Exception as e:
        p_err(f"Login agent exception: {e}"); return None

def agent_create(session: requests.Session, token: str, username: str,
                 ua: str, lang: str) -> Optional[dict]:
    url     = f"{HATCHER_BASE_API}/agents"
    payload = {"name": AGENT_NAME_TEMPLATE.format(username=username), "isPublic": AGENT_IS_PUBLIC}
    try:
        r = session.post(url, headers=_auth_headers_agent(token, ua, lang), json=payload,
                         timeout=20, verify=False)
        data = r.json() if r.content else {}
        if r.status_code in (200, 201) and data.get("success"):
            agent = data["data"]
            p_agent(f"Agent dibuat: '{cp(agent['name'], C.BGREEN, True)}' (id={agent['id']})")
            return agent
        err = data.get("error", r.text)
        if r.status_code == 400 and "maximum" in err.lower() and "agent" in err.lower():
            p_warn("Limit agent free tier, ambil existing...")
            r2 = session.get(url, headers=_auth_headers_agent(token, ua, lang),
                             timeout=15, verify=False)
            d2 = r2.json() if r2.content else {}
            if d2.get("success") and d2.get("data"):
                ex = d2["data"][0]
                p_agent(f"Existing agent: '{cp(ex['name'], C.BYELLOW)}' (id={ex['id']})")
                ex["_existing"] = True
                return ex
        p_warn(f"Create agent gagal [{r.status_code}]: {err[:80]}")
        return None
    except Exception as e:
        p_err(f"Create agent exception: {e}"); return None

def agent_start(session: requests.Session, token: str, agent_id: str,
                ua: str, lang: str) -> bool:
    url = f"{HATCHER_BASE_API}/agents/{agent_id}/start"
    try:
        r = session.post(url, headers=_auth_headers_agent(token, ua, lang), json={},
                         timeout=30, verify=False)
        data = r.json() if r.content else {}
        if r.status_code == 200 and data.get("success"):
            status = data["data"].get("status", "unknown")
            p_agent(f"Agent started: {cp(status, C.BGREEN, True)}")
            return True
        p_warn(f"Start agent gagal [{r.status_code}]: {data.get('error', '')[:60]}")
        return False
    except Exception as e:
        p_err(f"Start agent exception: {e}"); return False

def agent_configure(session: requests.Session, token: str, agent_id: str,
                    username: str, ua: str, lang: str) -> bool:
    url = f"{HATCHER_BASE_API}/agents/{agent_id}"
    payload = {"description": AGENT_DESCRIPTION,
               "config": {"systemPrompt": AGENT_SYSTEM_PROMPT, "model": AGENT_MODEL},
               "isPublic": AGENT_IS_PUBLIC}
    try:
        r = session.patch(url, headers=_auth_headers_agent(token, ua, lang), json=payload,
                          timeout=20, verify=False)
        data = r.json() if r.content else {}
        if r.status_code == 200 and data.get("success"):
            p_agent(f"Agent configured: model={cp(AGENT_MODEL, C.BCYAN)}")
            return True
        p_warn(f"Config agent gagal [{r.status_code}]")
        return False
    except Exception as e:
        p_err(f"Configure agent exception: {e}"); return False

def auto_create_agent_for_account(session: requests.Session, email: str, password: str,
                                   username: str, proxy_str: str, ua: str, lang: str,
                                   delay: HumanDelay) -> dict:
    result = {"agent_status": "pending", "agent_id": None, "agent_name": None,
              "agent_slug": None, "agent_url": None, "agent_configured": False,
              "agent_proxy": proxy_str}
    print(f"\n  {csep('─', 50, C.MAGENTA)}")
    p_agent(f"Mulai create agent untuk {cp(email, C.BCYAN)}")
    print(f"  {csep('─', 50, C.MAGENTA)}")

    p_agent("Step 1/4 Login...")
    delay.short()
    auth = agent_login(session, email, password, ua, lang)
    if not auth:
        result["agent_status"] = "login_failed"
        p_err("Login gagal, skip create agent")
        return result

    token = auth["token"]
    delay.short()

    p_agent("Step 2/4 Create agent...")
    agent = agent_create(session, token, username, ua, lang)
    if not agent:
        result["agent_status"] = "create_failed"
        p_err("Create agent gagal")
        return result

    result["agent_id"]     = agent["id"]
    result["agent_name"]   = agent["name"]
    result["agent_slug"]   = agent["slug"]
    result["agent_url"]    = f"https://hatcher.host/agent/{agent['slug']}"
    result["agent_reused"] = agent.get("_existing", False)
    delay.short()

    p_agent("Step 3/4 Start/hatch agent...")
    if agent.get("status") == "active":
        p_agent(f"Agent sudah {cp('ACTIVE', C.BGREEN, True)}, skip start")
        started = True
    else:
        started = agent_start(session, token, agent["id"], ua, lang)
    if not started:
        result["agent_status"] = "start_failed"
        p_err("Start agent gagal")
        return result

    p_wait("Tunggu container siap 5s...")
    time.sleep(5)

    p_agent("Step 4/4 Configure agent...")
    configured = agent_configure(session, token, agent["id"], username, ua, lang)
    result["agent_status"]     = "active"
    result["agent_configured"] = configured

    p_ok(f"Agent aktif! URL: {cp(result['agent_url'], C.BCYAN, True)}")
    return result



# ══════════════════════════════════════════════════════════════════════
#  FILE UTILS  — APPEND MODE (tidak pernah hapus/reset output)
# ══════════════════════════════════════════════════════════════════════
def load_results() -> list:
    """Load existing results untuk di-append."""
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def save_results(data: list):
    """Simpan seluruh list (existing + baru) — TIDAK pernah hapus entry lama."""
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, OUTPUT_FILE)
    log.info(f"[SAVE] {len(data)} total entries di {OUTPUT_FILE}")

def load_agent_results() -> list:
    if os.path.exists(AGENT_OUTPUT_FILE):
        with open(AGENT_OUTPUT_FILE, encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def save_agent_results(data: list):
    tmp = AGENT_OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, AGENT_OUTPUT_FILE)
    log.info(f"[SAVE] {len(data)} total agent entries di {AGENT_OUTPUT_FILE}")



# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    print_banner()

    # ── Prompt jumlah akun ───────────────────────────────────────────
    accounts_this_session = ask_account_count()

    # ── Info file output ─────────────────────────────────────────────
    existing_results = load_results()
    existing_agents  = load_agent_results()
    existing_count   = len(existing_results)

    print(f"\n  {cp('📁 Output Files', C.BYELLOW, True)}")
    print(f"  {cp('registered_accounts.json', C.BWHITE)} → {cp(str(existing_count) + ' akun existing', C.BGREEN)} (akan di-append)")
    print(f"  {cp('agent_results.json', C.BWHITE)} → {cp(str(len(existing_agents)) + ' agent existing', C.BGREEN)} (akan di-append)")
    print(f"\n  {cp('⚡ Sesi ini akan membuat:', C.BYELLOW, True)} {cp(str(accounts_this_session) + ' akun BARU', C.BWHITE, True)}")
    print(csep("═", 65, C.CYAN))

    # ── Init Proxy ───────────────────────────────────────────────────
    pm = ProxyManager()
    if pm.count == 0:
        p_err(f"Tidak ada proxy! Buat '{PROXY_FILE}' dengan daftar proxy.")
        return

    try:
        sm = SessionManager(pm)
    except RuntimeError as e:
        p_err(str(e))
        return

    delay    = HumanDelay()
    tempmail = TempMailClient()
    verifier = HatcherVerifier(sm)

    # Gunakan list existing sebagai base untuk append
    results       = existing_results
    agent_results = existing_agents

    ok_count   = 0
    ver_count  = 0
    agent_ok   = 0
    fail_count = 0

    print()
    for idx in range(1, accounts_this_session + 1):
        p_account_header(idx, accounts_this_session)

        # Rotate — proxy baru per akun
        try:
            sm.rotate_for_new_account()
        except RuntimeError as e:
            p_err(str(e)); break

        account_proxy = sm.current_proxy
        account_ua    = sm.current_ua
        account_lang  = sm.current_lang

        # ── Step 1: Temp email ───────────────────────────────────────
        p_step(1, 7, "Generate temporary email")
        result = tempmail.generate()
        if not result:
            p_err("Gagal generate temp email, skip!"); fail_count += 1; delay.short(); continue
        temp_email, inbox_token = result

        # ── Step 2: Credentials ──────────────────────────────────────
        p_step(2, 7, "Generate credentials")
        username = make_username(temp_email)
        password = make_password()
        print(f"  {cp('Email    :', C.DIM+C.WHITE)} {cp(temp_email, C.BCYAN)}")
        print(f"  {cp('Username :', C.DIM+C.WHITE)} {cp(username, C.BWHITE)}")
        print(f"  {cp('Password :', C.DIM+C.WHITE)} {cp(password, C.BWHITE)}")

        # ── Step 3: Cek username ─────────────────────────────────────
        p_step(3, 7, "Cek ketersediaan username")
        if not check_avail(sm, "username", username, delay):
            p_info("Username konflik, cari alternatif...")
            username = resolve_username(sm, username, delay)
            p_ok(f"Pakai username: {cp(username, C.BWHITE, True)}")
        delay.short()

        # ── Step 4: Register ─────────────────────────────────────────
        p_step(4, 7, "Mendaftar akun")
        reg = register(sm, temp_email, username, password, delay)

        if reg["status"] != "success":
            p_err(f"Register gagal: {cp(reg['status'], C.BRED, True)}")
            fail_count += 1
            results.append({
                "email": temp_email, "username": username, "password": password,
                "status": reg["status"], "verified": False, "verify_link": "",
                "proxy": account_proxy or "direct", "response": reg.get("data", {}),
                "timestamp": datetime.now().isoformat()
            })
            save_results(results)
            delay.between_accounts(); continue

        ok_count += 1

        # ── Step 5: Poll email verifikasi ────────────────────────────
        p_step(5, 7, "Tunggu email verifikasi")
        p_wait("Tunggu 10s sebelum polling...")
        time.sleep(10 + random.uniform(2, 5))
        verify_link, inbox_token = tempmail.wait_for_email(
            token=inbox_token, email_address=temp_email, timeout=POLL_MAX_WAIT_SEC)
        print()  # newline setelah progress polling

        # ── Step 6: Verifikasi ───────────────────────────────────────
        verified = False
        if verify_link:
            p_step(6, 7, "Auto-verifikasi akun")
            delay.short()
            verified, method = verifier.verify(verify_link)
            if verified:
                ver_count += 1
                p_ok(f"{cp('✓ AKUN TERVERIFIKASI', C.BGREEN, True)}: {cp(temp_email, C.BCYAN)}")
            else:
                p_warn(f"Verifikasi GAGAL: {temp_email}")
        else:
            p_warn("Email verifikasi tidak datang (timeout)")

        # Simpan register result
        result_entry = {
            "email": temp_email, "username": username, "password": password,
            "status": "success" if verified else "registered_unverified",
            "verified": verified, "verify_link": verify_link or "",
            "proxy": account_proxy or "direct", "response": reg.get("data", {}),
            "timestamp": datetime.now().isoformat()
        }
        results.append(result_entry)
        save_results(results)

        # ── Step 7: Auto Create Agent ────────────────────────────────
        p_step(7, 7, "Auto Create Agent")
        delay.short()
        agent_result = auto_create_agent_for_account(
            session=sm.session, email=temp_email, password=password,
            username=username, proxy_str=account_proxy or "direct",
            ua=account_ua, lang=account_lang, delay=delay)

        agent_entry = {"email": temp_email, "username": username,
                       "verified": verified, "proxy": account_proxy or "direct",
                       "timestamp": datetime.now().isoformat(), **agent_result}
        agent_results.append(agent_entry)
        save_agent_results(agent_results)

        if agent_result["agent_status"] == "active":
            agent_ok += 1
        else:
            p_warn(f"Agent gagal: {agent_result['agent_status']}")

        # ── Mini summary tiap akun ───────────────────────────────────
        print(f"\n  {csep('─', 55, C.CYAN)}")
        print(f"  {cp('▶ SUMMARY AKUN #' + str(idx), C.BWHITE, True)}")
        print(f"  {cp('Email   :', C.DIM+C.WHITE)} {cp(temp_email, C.BCYAN)}")
        print(f"  {cp('User    :', C.DIM+C.WHITE)} {cp(username, C.BWHITE)}")
        print(f"  {cp('Pass    :', C.DIM+C.WHITE)} {cp(password, C.BWHITE)}")
        print(f"  {cp('Verified:', C.DIM+C.WHITE)} {cp('YES ✓', C.BGREEN, True) if verified else cp('NO ✗', C.BRED)}")
        print(f"  {cp('Agent   :', C.DIM+C.WHITE)} {cp(agent_result.get('agent_url', '-'), C.BCYAN)}")
        print(f"  {cp('Proxy   :', C.DIM+C.WHITE)} {cp((account_proxy or 'direct')[:55], C.BBLUE)}")
        print(f"  {csep('─', 55, C.CYAN)}")

        if idx < accounts_this_session:
            delay.between_accounts()

    # ══════════════════════════════════════════════════════════════════
    #  FINAL SUMMARY
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{csep('═', 65, C.BCYAN)}")
    print(f"  {cp('SELESAI — RINGKASAN SESI', C.BWHITE, True)}")
    print(csep("─", 65, C.BLUE))
    total_in_file = len(results)
    print(f"  {cp('Sesi ini target  :', C.DIM+C.WHITE)} {cp(str(accounts_this_session), C.BWHITE, True)}")
    print(f"  {cp('Register sukses  :', C.DIM+C.WHITE)} {cp(str(ok_count), C.BGREEN, True)}")
    print(f"  {cp('Akun terverified :', C.DIM+C.WHITE)} {cp(str(ver_count), C.BGREEN, True)}")
    print(f"  {cp('Agent berhasil   :', C.DIM+C.WHITE)} {cp(str(agent_ok), C.BGREEN, True)}")
    print(f"  {cp('Gagal            :', C.DIM+C.WHITE)} {cp(str(fail_count), C.BRED, True)}")
    print(f"  {cp('Proxy terpakai   :', C.DIM+C.WHITE)} {cp(str(len(pm.used)), C.BBLUE)}")
    print(csep("─", 65, C.BLUE))
    print(f"  {cp('Total di file output :', C.DIM+C.WHITE)} {cp(str(total_in_file) + ' akun', C.BYELLOW, True)} ({cp('accumulated', C.BGREEN)})")
    print(f"  {cp('Output register  :', C.DIM+C.WHITE)} {cp(OUTPUT_FILE, C.BWHITE)}")
    print(f"  {cp('Output agent     :', C.DIM+C.WHITE)} {cp(AGENT_OUTPUT_FILE, C.BWHITE)}")
    print(f"  {cp('Log file         :', C.DIM+C.WHITE)} {cp(LOG_FILE, C.BWHITE)}")
    print(csep("═", 65, C.BCYAN))

    # Tabel akun verified sesi ini
    session_verified = [r for r in results[-accounts_this_session:] if r.get("verified")]
    if session_verified:
        print(f"\n  {cp('✓ Akun Terverifikasi (sesi ini):', C.BGREEN, True)}")
        print(f"  {cp('─'*63, C.DIM+C.WHITE)}")
        hdr = f"  {cp('Email', C.BYELLOW):<42} {cp('Username', C.BYELLOW):<20} {cp('Password', C.BYELLOW)}"
        print(hdr)
        print(f"  {cp('─'*63, C.DIM+C.WHITE)}")
        for acc in session_verified:
            print(f"  {cp(acc['email'], C.BCYAN):<42} {cp(acc['username'], C.BWHITE):<20} {cp(acc['password'], C.BWHITE)}")
        print(f"  {cp('─'*63, C.DIM+C.WHITE)}")

    # Tabel agent aktif sesi ini
    session_agents = [r for r in agent_results[-accounts_this_session:] if r.get("agent_status") == "active"]
    if session_agents:
        print(f"\n  {cp('✓ Agent Aktif (sesi ini):', C.BGREEN, True)}")
        print(f"  {cp('─'*63, C.DIM+C.WHITE)}")
        for r in session_agents:
            proxy = (r.get("proxy") or "direct")[:22]
            print(f"  {cp(r['email'], C.BCYAN):<40} {cp(r.get('agent_url', '-'), C.BMAGENTA)}")
        print(f"  {cp('─'*63, C.DIM+C.WHITE)}")

    sm.close()
    tempmail.close()
    print(f"\n  {cp('Terima kasih! Script selesai.', C.BGREEN, True)}\n")


if __name__ == "__main__":
    main()
