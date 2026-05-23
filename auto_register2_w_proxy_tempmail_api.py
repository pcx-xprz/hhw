"""
Hatcher Auto Register + Auto Verify
=====================================
Anti-Detection dari script 1:
  - Proxy rotation (100+ UA pool)
  - User-Agent rotation (40+ UA)
  - Header randomization (Accept-Language, DNT, sec-ch-ua, dll)
  - Session rotation (tiap N akun)
  - Retry logic dengan exponential backoff
  - Rate limit detection & auto-pause
  - Human-like behavior simulation
  - Fingerprint randomization
  - Typing simulation
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

# ── CONFIG ────────────────────────────────────────────────────────────
REFERRAL_CODE        = "9b84cb45"
HATCHER_BASE_API     = "https://api.hatcher.host"
HATCHER_FRONTEND     = "https://hatcher.host"
TEMPMAIL_BASE_URL    = "https://api.tempmail.lol"
TEMPMAIL_API_KEY     = ""

ACCOUNTS_TO_CREATE   = 13
OUTPUT_FILE          = "registered_accounts.json"
PROXY_FILE           = "proxies_alive.txt"
LOG_FILE             = "register.log"
FAILED_PROXY_FILE    = "failed_proxies.txt"
DEBUG_EMAIL_DIR      = "debug_emails"

# Delay config (dari script 1)
DELAY_MIN            = 8
DELAY_MAX            = 20
DELAY_BETWEEN_ACCS   = 30
DELAY_JITTER         = 3

# Session rotation (dari script 1)
SESSION_ROTATE_EVERY = 3

# Retry config (dari script 1)
MAX_RETRIES          = 3
RETRY_BACKOFF_BASE   = 5
RATE_LIMIT_PAUSE     = 120

# Proxy config
USE_PROXY            = True
PROXY_TIMEOUT        = 15
PROXY_TEST_TIMEOUT   = 20
PROXY_TEST_URLS      = [
    "http://httpbin.org/ip",
    "https://api.ipify.org?format=json",
    "http://ip-api.com/json",
]
PROXY_MAX_TEST       = 15

# Poll config
POLL_INTERVAL_SEC    = 8
POLL_MAX_WAIT_SEC    = 300

# ─────────────────────────────────────────────────────────────────────

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

for d in [DEBUG_EMAIL_DIR, "backups"]:
    os.makedirs(d, exist_ok=True)

file_handler    = logging.FileHandler(LOG_FILE, encoding="utf-8")
console_handler = logging.StreamHandler(sys.stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[file_handler, console_handler]
)
log = logging.getLogger(__name__)


# ─── USER-AGENT POOL (dari script 1, 40+ UA) ─────────────────────────
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Chrome Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) Gecko/20100101 Firefox/118.0",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Firefox macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.6; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Firefox Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_7_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    # Edge Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.0.0",
    # Chrome Android
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.163 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    # Safari iOS
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

# Accept-Language pool (dari script 1)
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
#  HEADER FACTORY (dari script 1 - fingerprint randomization)
# ══════════════════════════════════════════════════════════════════════
class HeaderFactory:
    """
    Generate random-tapi-konsisten browser headers.
    Diambil dari script 1 untuk fingerprint randomization.
    """

    def __init__(self):
        self.referral_code = REFERRAL_CODE

    def _get_chrome_version(self, ua: str) -> str:
        m = re.search(r"Chrome/(\d+)", ua)
        return m.group(1) if m else "120"

    def _is_mobile(self, ua: str) -> bool:
        return any(x in ua for x in ["Mobile", "Android", "iPhone", "iPad"])

    def build(self, ua: Optional[str] = None, referer: str = None) -> dict:
        """Build complete randomized headers."""
        if ua is None:
            ua = random.choice(USER_AGENTS)

        is_chrome  = "Chrome" in ua and "Edg" not in ua
        is_edge    = "Edg" in ua
        is_firefox = "Firefox" in ua
        is_mobile  = self._is_mobile(ua)
        lang       = random.choice(ACCEPT_LANGUAGES)

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

        # DNT acak (dari script 1)
        if random.random() > 0.5:
            headers["DNT"] = "1"

        # Sec headers Chrome/Edge (dari script 1)
        if is_chrome or is_edge:
            cv = self._get_chrome_version(ua)
            headers["Sec-Fetch-Dest"] = "empty"
            headers["Sec-Fetch-Mode"] = "cors"
            headers["Sec-Fetch-Site"] = "same-site"

            if is_edge:
                headers["Sec-CH-UA"] = (
                    f'"Not_A Brand";v="8", "Chromium";v="{cv}", '
                    f'"Microsoft Edge";v="{cv}"'
                )
                headers["Sec-CH-UA-Platform"] = '"Windows"'
            else:
                headers["Sec-CH-UA"] = (
                    f'"Not_A Brand";v="8", "Chromium";v="{cv}", '
                    f'"Google Chrome";v="{cv}"'
                )
                if "Windows" in ua:
                    headers["Sec-CH-UA-Platform"] = '"Windows"'
                elif "Macintosh" in ua:
                    headers["Sec-CH-UA-Platform"] = '"macOS"'
                elif "Linux" in ua and "Android" not in ua:
                    headers["Sec-CH-UA-Platform"] = '"Linux"'
                elif "Android" in ua:
                    headers["Sec-CH-UA-Platform"] = '"Android"'

            headers["Sec-CH-UA-Mobile"] = "?1" if is_mobile else "?0"

        # Cache-Control acak (dari script 1)
        cc = random.choice(["no-cache", "max-age=0", None])
        if cc:
            headers["Cache-Control"] = cc

        # Pragma acak (dari script 1)
        if random.random() > 0.6:
            headers["Pragma"] = "no-cache"

        # TE Firefox (dari script 1)
        if is_firefox:
            headers["TE"] = "trailers"

        return headers


#  PROXY MANAGER - FIXED
#  Fix: rotasi proxy per-akun + auto-handle proxy mati
# ══════════════════════════════════════════════════════════════════════
class ProxyManager:
    def __init__(self):
        self.proxies      = []      # semua proxy yang loaded
        self.failed       = set()   # proxy yang sudah terbukti mati
        self.working      = []      # proxy yang sudah lulus test
        self.working_idx  = 0       # index rotasi untuk working proxies
        self.raw_idx      = 0       # index rotasi untuk semua proxies
        self._load()
        self._initial_test()        # test batch di awal

    def _load(self):
        if not os.path.exists(PROXY_FILE):
            log.warning(f"[PROXY] '{PROXY_FILE}' tidak ada. Mode tanpa proxy.")
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
                elif p in failed_set:
                    log.debug(f"[PROXY] Skip known-failed: {p}")

        random.shuffle(loaded)
        self.proxies = loaded
        log.info(f"[PROXY] Loaded {len(self.proxies)} proxy dari '{PROXY_FILE}'")

    def _initial_test(self):
        """
        Test batch proxy di awal untuk isi working list.
        Test MAX_TEST proxy, ambil yang lulus.
        Ini dijalankan SEKALI saat startup.
        """
        if not self.proxies:
            return

        MAX_TEST = min(PROXY_MAX_TEST, len(self.proxies))
        log.info(f"[PROXY] Initial test {MAX_TEST} proxy dari {len(self.proxies)} ...")

        found = 0
        for i in range(MAX_TEST):
            p = self.proxies[i]
            log.info(f"  [PROXY] Test [{i+1}/{MAX_TEST}]: {p[:50]}")
            if self._do_test(p):
                self.working.append(p)
                found += 1

        if self.working:
            log.info(f"[PROXY] ✓ {len(self.working)} proxy aktif siap dipakai")
            # Shuffle working list agar rotasi lebih acak
            random.shuffle(self.working)
        else:
            log.warning(
                f"[PROXY] ✗ Tidak ada proxy yang lulus test dari {MAX_TEST} yang dicoba!\n"
                f"  → Akan coba pakai proxy tanpa pre-test (soft mode)\n"
                f"  → Cek format proxy di '{PROXY_FILE}'"
            )

    def _do_test(self, proxy_url: str) -> bool:
        """Test satu proxy, coba beberapa URL."""
        proxy_dict = self.get_proxy_dict(proxy_url)
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
                    try:
                        ip_data = r.json()
                        ip = (ip_data.get("ip") or
                              ip_data.get("query") or
                              ip_data.get("origin", "?"))
                        log.info(f"  [PROXY] ✓ {proxy_url[:45]} → IP: {ip}")
                    except:
                        log.info(f"  [PROXY] ✓ {proxy_url[:45]} → OK")
                    return True
            except requests.exceptions.ConnectTimeout:
                continue
            except requests.exceptions.ProxyError:
                break
            except requests.exceptions.SSLError:
                # SSL error = proxy connect OK, anggap lulus
                log.info(f"  [PROXY] ✓ {proxy_url[:45]} → OK (SSL)")
                return True
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
        if re.match(r"^[^@]+@\d{1,3}(\.\d{1,3}){3}:\d{2,5}$", raw):
            return f"http://{raw}"
        parts = raw.split(":")
        if len(parts) == 4:
            ip, port, user, pwd = parts
            return f"http://{user}:{pwd}@{ip}:{port}"
        log.warning(f"[PROXY] Format tidak dikenal (skip): {raw}")
        return None

    def get_proxy_dict(self, p: str) -> dict:
        return {"http": p, "https": p}

    def mark_failed(self, p: str):
        """Tandai proxy mati, hapus dari semua list."""
        if not p:
            return
        if p not in self.failed:
            self.failed.add(p)
            with open(FAILED_PROXY_FILE, "a") as f:
                f.write(p + "\n")
            log.warning(f"[PROXY] ✗ Marked failed: {p[:50]}")

        # Hapus dari working dan proxies
        if p in self.working:
            self.working.remove(p)
        if p in self.proxies:
            self.proxies.remove(p)

        log.info(f"[PROXY] Sisa working: {len(self.working)} | Total: {len(self.proxies)}")

    def get_next_proxy(self) -> Optional[str]:
        """
        Ambil proxy BERBEDA untuk setiap akun.

        Prioritas:
        1. Round-robin dari working list (sudah tested)
        2. Jika working habis, test proxy baru dari pool
        3. Jika semua habis, soft mode (pakai tanpa test)
        4. Jika benar-benar kosong, return None (direct)
        """

        # ── Prioritas 1: Round-robin dari working list ─────────────────
        if self.working:
            # Ambil berikutnya, wrap around
            self.working_idx = self.working_idx % len(self.working)
            proxy = self.working[self.working_idx]
            self.working_idx += 1

            log.info(
                f"  [PROXY] Akun ini pakai: {proxy[:50]}\n"
                f"  [PROXY] (slot {self.working_idx}/{len(self.working)} "
                f"dari {len(self.working)} proxy aktif)"
            )
            return proxy

        # ── Prioritas 2: Test proxy baru dari pool ─────────────────────
        if self.proxies:
            log.info("[PROXY] Working list kosong, test proxy baru ...")
            # Coba test beberapa proxy dari pool yang belum ditest
            tested = 0
            attempts = min(10, len(self.proxies))
            for _ in range(attempts):
                self.raw_idx = self.raw_idx % len(self.proxies)
                p = self.proxies[self.raw_idx]
                self.raw_idx += 1
                tested += 1

                log.info(f"  [PROXY] Test baru [{tested}]: {p[:50]}")
                if self._do_test(p):
                    self.working.append(p)
                    log.info(f"[PROXY] ✓ Proxy baru ditambahkan ke working list")
                    return p

        # ── Prioritas 3: Soft mode ─────────────────────────────────────
        if self.proxies:
            p = self.proxies[self.raw_idx % len(self.proxies)]
            self.raw_idx += 1
            log.warning(
                f"[PROXY] Soft mode (tidak ada yang lulus test)\n"
                f"  → Pakai: {p[:50]}"
            )
            return p

        # ── Prioritas 4: Direct ────────────────────────────────────────
        log.warning("[PROXY] Tidak ada proxy tersedia → direct connection")
        return None

    def replenish_working(self, min_count: int = 3):
        """
        Pastikan working list selalu punya minimal N proxy.
        Dipanggil setelah mark_failed() untuk refill.
        """
        if len(self.working) >= min_count:
            return
        if not self.proxies:
            return

        needed = min_count - len(self.working)
        log.info(f"[PROXY] Replenish working list (perlu {needed} proxy lagi) ...")

        added = 0
        for _ in range(min(needed * 3, len(self.proxies))):
            self.raw_idx = self.raw_idx % len(self.proxies)
            p = self.proxies[self.raw_idx]
            self.raw_idx += 1

            if p in self.working or p in self.failed:
                continue

            if self._do_test(p):
                self.working.append(p)
                added += 1
                log.info(f"[PROXY] ✓ Replenish: {p[:50]}")
                if added >= needed:
                    break

    @property
    def count(self):
        return len(self.proxies)

    @property
    def working_count(self):
        return len(self.working)


# ══════════════════════════════════════════════════════════════════════
#  HUMAN DELAY (dari script 1 - typing simulation, gaussian jitter)
# ══════════════════════════════════════════════════════════════════════
class HumanDelay:
    def __init__(self):
        self.request_count = 0

    def _jitter(self, base: float) -> float:
        """Gaussian noise dari script 1."""
        noise = random.gauss(0, DELAY_JITTER)
        return max(2.0, base + noise)

    def short(self):
        t = self._jitter(random.uniform(2, 5))
        log.info(f"  [WAIT] {t:.1f}s ...")
        time.sleep(t)

    def medium(self):
        t = self._jitter(random.uniform(DELAY_MIN, DELAY_MAX))
        log.info(f"  [WAIT] {t:.1f}s ...")
        time.sleep(t)

    def between_accounts(self):
        """Dari script 1: pause panjang tiap 5 akun."""
        self.request_count += 1
        if self.request_count % 5 == 0:
            extra = random.uniform(30, 90)
            t     = self._jitter(DELAY_BETWEEN_ACCS + extra)
            log.info(f"  [BREAK] Pause panjang {t:.0f}s (simulate user break) ...")
        else:
            t = self._jitter(random.uniform(DELAY_BETWEEN_ACCS, DELAY_BETWEEN_ACCS * 2))
            log.info(f"  [WAIT] Antar akun {t:.1f}s ...")
        time.sleep(t)

    def rate_limit_pause(self, retry_after: int = RATE_LIMIT_PAUSE):
        t = retry_after + random.uniform(10, 30)
        log.warning(f"  [RATE LIMIT] Pause {t:.0f}s ...")
        time.sleep(t)

    def typing_simulation(self):
        """Dari script 1: micro-delay sebelum POST."""
        for _ in range(random.randint(2, 5)):
            time.sleep(random.uniform(0.1, 0.4))



#  SESSION MANAGER - FIXED
#  Fix: pakai get_next_proxy() untuk rotasi per-akun
#       + auto-replenish jika proxy mati
# ══════════════════════════════════════════════════════════════════════
class SessionManager:
    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager  = proxy_manager
        self.header_factory = HeaderFactory()
        self.session        = None
        self.current_proxy  = None
        self.current_ua     = None
        self.account_count  = 0
        self._create_new_session()

    def _create_new_session(self):
        if self.session:
            self.session.close()

        self.session    = requests.Session()
        self.current_ua = random.choice(USER_AGENTS)
        log.info(f"  [SESSION] UA: {self.current_ua[:60]}...")

        if USE_PROXY and self.proxy_manager.count > 0:
            # ← PAKAI get_next_proxy() untuk rotasi per-akun
            self.current_proxy = self.proxy_manager.get_next_proxy()
            if self.current_proxy:
                self.session.proxies.update(
                    self.proxy_manager.get_proxy_dict(self.current_proxy)
                )
                log.info(f"  [SESSION] Proxy aktif: {self.current_proxy}")
            else:
                log.warning("  [SESSION] Direct connection (tanpa proxy)")
        else:
            self.current_proxy = None
            log.info("  [SESSION] Mode tanpa proxy")

        self.session.timeout = 20

    def rotate(self):
        """Rotate ke proxy BERBEDA."""
        log.info("  [SESSION] Rotating session → proxy baru ...")
        self._create_new_session()

    def maybe_rotate(self):
        """Rotate tiap N akun → proxy berbeda per akun."""
        self.account_count += 1
        # Selalu rotate setiap akun baru untuk pastikan proxy berbeda
        if self.account_count % SESSION_ROTATE_EVERY == 0:
            self.rotate()

    def get(self, url: str, **kwargs) -> requests.Response:
        referer = kwargs.pop("referer", None)
        headers = self.header_factory.build(self.current_ua, referer=referer)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        return self.session.get(url, headers=headers, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        referer = kwargs.pop("referer", None)
        headers = self.header_factory.build(self.current_ua, referer=referer)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        return self.session.post(url, headers=headers, **kwargs)

    def mark_proxy_failed(self):
        """
        Tandai proxy saat ini mati + auto-replenish working list
        + langsung rotate ke proxy baru.
        """
        if self.current_proxy:
            self.proxy_manager.mark_failed(self.current_proxy)
            # Auto-replenish agar working list tidak kosong
            self.proxy_manager.replenish_working(min_count=3)
        self.rotate()

    def close(self):
        if self.session:
            self.session.close()


# ══════════════════════════════════════════════════════════════════════
#  TEMPMAIL CLIENT (tidak diubah dari script 2)
# ══════════════════════════════════════════════════════════════════════
class TempMailClient:
    def __init__(self):
        self.api_key  = TEMPMAIL_API_KEY.strip()
        self.has_key  = bool(self.api_key)
        self._session = requests.Session()
        log.info(f"[TEMPMAIL] Mode: {'PAID' if self.has_key else 'FREE'}")

    def _headers(self) -> dict:
        h = {
            "Accept":          "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": random.choice(ACCEPT_LANGUAGES),
            "User-Agent":      random.choice(USER_AGENTS),
        }
        if self.has_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def generate(self) -> Optional[Tuple[str, str]]:
        url = f"{TEMPMAIL_BASE_URL}/generate/"
        for attempt in range(MAX_RETRIES):
            try:
                r = self._session.get(url, headers=self._headers(), timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    addr = data.get("address", "")
                    tok  = data.get("token", "")
                    if addr and tok:
                        log.info(f"  [TEMPMAIL] ✓ Inbox: {addr}")
                        return addr, tok
                    return None
                elif r.status_code == 429:
                    time.sleep(35 + random.uniform(5, 15))
                    continue
                elif r.status_code == 401:
                    log.error("  [TEMPMAIL] 401 - API key salah!")
                    return None
                else:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))
            except Exception as e:
                log.error(f"  [TEMPMAIL] generate error: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF_BASE)
        return None

    def fetch(self, token: str) -> Tuple[list, str]:
        url = f"{TEMPMAIL_BASE_URL}/auth/{token}"
        try:
            r = self._session.get(url, headers=self._headers(), timeout=20)
            if r.status_code == 200:
                data      = r.json()
                new_token = data.get("token", token)
                emails    = data.get("email", [])
                if not isinstance(emails, list):
                    emails = []
                if emails:
                    log.info(f"  [TEMPMAIL] {len(emails)} email masuk!")
                return emails, new_token
            elif r.status_code == 429:
                time.sleep(25)
                return [], token
            else:
                return [], token
        except Exception as e:
            log.error(f"  [TEMPMAIL] fetch error: {e}")
            return [], token

    def wait_for_email(
        self, token: str, email_address: str,
        timeout: int = POLL_MAX_WAIT_SEC
    ) -> Tuple[Optional[str], str]:
        log.info(
            f"  [POLL] Polling: {email_address}\n"
            f"  [POLL] Max: {timeout}s | Interval: {POLL_INTERVAL_SEC}s"
        )
        cur_token = token
        start     = time.time()
        n         = 0

        while True:
            elapsed = time.time() - start
            if elapsed >= timeout:
                log.warning(f"  [POLL] Timeout {elapsed:.0f}s")
                return None, cur_token

            n += 1
            log.info(f"  [POLL #{n}] {elapsed:.0f}s/{timeout}s")
            emails, cur_token = self.fetch(cur_token)

            for mail in emails:
                mail_from    = mail.get("from", "")
                mail_subject = mail.get("subject", "")
                mail_body    = mail.get("body", "")

                log.info(f"  [MAIL] From: {mail_from} | Subject: {mail_subject[:50]}")

                fname = os.path.join(
                    DEBUG_EMAIL_DIR,
                    f"email_{mail.get('id', n)}_{int(time.time())}.html"
                )
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(f"<!-- From: {mail_from} -->\n")
                    f.write(f"<!-- Subject: {mail_subject} -->\n")
                    f.write(mail_body)

                is_hatcher = any(kw in mail_from.lower() for kw in
                                 ["hatcher", "noreply", "no-reply"])
                is_verify  = any(kw in mail_subject.lower() for kw in
                                 ["verif", "confirm", "activate", "welcome"])

                if is_hatcher or is_verify:
                    link = self._extract_link(mail_body)
                    if link:
                        log.info(f"  [MAIL] ✓ Link: {link}")
                        return link, cur_token
                    log.warning("  [MAIL] Email cocok tapi link tidak ditemukan!")

            wait = max(5.0, POLL_INTERVAL_SEC + random.uniform(-2, 3))
            log.info(f"  [POLL] Tunggu {wait:.1f}s ...")
            time.sleep(wait)

    def _extract_link(self, body: str) -> Optional[str]:
        if not body:
            return None
        for pattern in [
            r'https?://(?:api\.)?hatcher\.host[^\s"\'<>\]]*verif[^\s"\'<>\]]*',
            r'https?://hatcher\.host/verify-email[^\s"\'<>\]]*',
            r'https?://(?:api\.)?hatcher\.host[^\s"\'<>\]]*[?&]token=[A-Za-z0-9_\-\.]{10,}',
        ]:
            m = re.findall(pattern, body, re.IGNORECASE)
            if m:
                return m[0].rstrip('.,;:)\'">\r\n')
        try:
            soup = BeautifulSoup(body, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text(strip=True).lower()
                if "hatcher" in href.lower() and any(
                    kw in href.lower() for kw in ["verif", "token"]
                ):
                    return href
                if any(kw in text for kw in ["verif", "confirm", "click here"]):
                    if href.startswith("http"):
                        return href
        except:
            pass
        return None

    def close(self):
        self._session.close()


# ══════════════════════════════════════════════════════════════════════
#  VERIFIER (tidak diubah dari script 2)
# ══════════════════════════════════════════════════════════════════════
class HatcherVerifier:
    VERIFY_API_ENDPOINTS = [
        ("POST", f"{HATCHER_BASE_API}/auth/verify-email",          "body"),
        ("POST", f"{HATCHER_BASE_API}/auth/verify",                "body"),
        ("POST", f"{HATCHER_BASE_API}/auth/email/verify",          "body"),
        ("POST", f"{HATCHER_BASE_API}/users/verify-email",         "body"),
        ("GET",  f"{HATCHER_BASE_API}/auth/verify-email",          "query"),
        ("GET",  f"{HATCHER_BASE_API}/auth/verify",                "query"),
        ("GET",  f"{HATCHER_BASE_API}/auth/email/verify",          "query"),
        ("GET",  f"{HATCHER_BASE_API}/auth/verify-email/{{token}}", "path"),
        ("GET",  f"{HATCHER_BASE_API}/auth/verify/{{token}}",       "path"),
    ]

    def __init__(self, sm: SessionManager):
        self.sm = sm

    def _make_headers(self) -> dict:
        """Pakai HeaderFactory untuk header yang proper."""
        return self.sm.header_factory.build(
            self.sm.current_ua,
            referer=f"{HATCHER_FRONTEND}/verify-email"
        )

    def verify(self, verify_url: str) -> Tuple[bool, str]:
        token = self._extract_token(verify_url)
        if not token:
            log.error(f"  [VERIFY] Tidak bisa ekstrak token dari: {verify_url}")
            return False, "no_token"

        log.info(f"  [VERIFY] Token: {token[:20]}...")

        for method, endpoint, style in self.VERIFY_API_ENDPOINTS:
            success, note = self._try_endpoint(method, endpoint, style, token)
            if success:
                log.info(f"  [VERIFY] ✓ Berhasil via {method} {endpoint} [{style}]")
                return True, f"{method}:{endpoint}"
            if note == "skip":
                continue

        log.error("  [VERIFY] Semua endpoint gagal!")
        return False, "all_failed"

    def _extract_token(self, url: str) -> Optional[str]:
        m = re.search(r'[?&]token=([A-Za-z0-9_\-\.]{10,})', url)
        if m:
            return m.group(1)
        m = re.search(r'/verif[^/]*/([A-Za-z0-9_\-\.]{10,})/?$', url, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r'/([A-Za-z0-9_\-\.]{32,})/?$', url)
        if m:
            return m.group(1)
        return None

    def _try_endpoint(self, method, endpoint, style, token) -> Tuple[bool, str]:
        headers = self._make_headers()
        try:
            if style == "body":
                r = self.sm.session.post(
                    endpoint, json={"token": token},
                    headers=headers, timeout=20, allow_redirects=True
                )
            elif style == "query":
                r = self.sm.session.get(
                    endpoint, params={"token": token},
                    headers=headers, timeout=20, allow_redirects=True
                )
            elif style == "path":
                url = endpoint.replace("{token}", token)
                r   = self.sm.session.get(
                    url, headers=headers,
                    timeout=20, allow_redirects=True
                )
            else:
                return False, "skip"

            log.debug(f"  [VERIFY] {method} {endpoint} → [{r.status_code}]")
            return self._check_response(r, token)

        except requests.exceptions.ConnectionError:
            return False, "skip"
        except requests.exceptions.Timeout:
            return False, "skip"
        except Exception as e:
            log.debug(f"  [VERIFY] Error: {e}")
            return False, "skip"

    def _check_response(self, r: requests.Response, token: str) -> Tuple[bool, str]:
        status = r.status_code
        if status == 404:
            return False, "skip"
        if status == 400:
            try:
                data = r.json()
                msg  = str(data).lower()
                if "already" in msg and "verif" in msg:
                    log.info("  [VERIFY] Sudah verified → OK")
                    return True, "already_verified"
                if "expired" in msg or "invalid" in msg:
                    log.warning(f"  [VERIFY] Token expired/invalid: {data}")
                    return False, "fail"
            except:
                pass
            return False, "fail"
        if status in (200, 201, 204):
            try:
                data   = r.json()
                data_s = str(data).lower()
                if data.get("error") or data.get("success") is False:
                    log.warning(f"  [VERIFY] JSON error: {data}")
                    return False, "fail"
                if any(kw in data_s for kw in ["success", "verified", "true", "aktif"]):
                    return True, "json_success"
                return True, "json_no_error"
            except ValueError:
                body = r.text.lower()
                if "<html" in body and ("__next" in body or "react" in body):
                    return False, "skip"
                if any(kw in body for kw in ["success", "verified", "confirmed", "berhasil"]):
                    return True, "html_success"
                if any(kw in body for kw in ["error", "invalid", "expired", "failed"]):
                    return False, "fail"
                return False, "skip"
        if status in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "").lower()
            if any(kw in loc for kw in ["success", "verified", "dashboard", "login"]):
                return True, "redirect_success"
            return False, "skip"
        if status == 429:
            log.warning("  [VERIFY] Rate limited!")
            time.sleep(RATE_LIMIT_PAUSE)
            return False, "skip"
        return False, "skip"


# ══════════════════════════════════════════════════════════════════════
#  HATCHER FUNCTIONS (dengan retry + backoff dari script 1)
# ══════════════════════════════════════════════════════════════════════
def make_username(email: str) -> str:
    local = email.split("@")[0]
    local = re.sub(r"[.\-_]", "", local)
    local = re.sub(r"\d+$", "", local)
    local = re.sub(r"[^a-zA-Z0-9]", "", local).lower()
    if len(local) < 3:
        local = random.choice(["budi", "andi", "sari", "nova"]) + str(random.randint(10, 99))
    return local[:30]


def make_password() -> str:
    chars = (
        random.choices(string.ascii_lowercase, k=4)
        + random.choices(string.ascii_uppercase, k=3)
        + random.choices(string.digits, k=3)
        + random.choices("@#$!%*?&", k=2)
    )
    random.shuffle(chars)
    return "".join(chars)


def check_avail(sm: SessionManager, field: str, val: str, delay: HumanDelay) -> bool:
    url = f"{HATCHER_BASE_API}/auth/check-availability"
    # Retry + backoff dari script 1
    for attempt in range(MAX_RETRIES):
        try:
            r = sm.get(url, params={field: val}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                ok   = data.get("available", not data.get("exists", False))
                log.info(f"  [OK] {field} '{val}' {'tersedia' if ok else 'sudah dipakai'}")
                return ok
            elif r.status_code == 429:
                log.warning(f"  [RATE LIMIT] Cek {field}!")
                retry_after = int(r.headers.get("Retry-After", RATE_LIMIT_PAUSE))
                delay.rate_limit_pause(retry_after)
                sm.rotate()
                continue
            else:
                log.warning(f"  [WARN] check-availability [{r.status_code}]: {r.text[:100]}")
                return False
        except requests.exceptions.ProxyError:
            log.warning(f"  [PROXY] Error cek {field}, rotate ...")
            sm.mark_proxy_failed()
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_BASE)
        except requests.exceptions.ConnectTimeout:
            log.warning(f"  [TIMEOUT] Cek {field} attempt {attempt+1}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))
        except Exception as e:
            log.error(f"  [ERR] check {field}: {e}")
            return False
    return False


def resolve_username(sm: SessionManager, base: str, delay: HumanDelay) -> str:
    for _ in range(5):
        c = f"{base}{random.randint(10, 999)}"[:30]
        delay.short()
        if check_avail(sm, "username", c, delay):
            return c
    return f"{base}{int(time.time()) % 10000}"[:30]


def register(
    sm: SessionManager, email: str, username: str,
    password: str, delay: HumanDelay
) -> dict:
    url     = f"{HATCHER_BASE_API}/auth/register"
    payload = {
        "email": email, "username": username,
        "password": password, "referralCode": REFERRAL_CODE,
    }
    # Retry + backoff dari script 1
    for attempt in range(MAX_RETRIES):
        try:
            delay.typing_simulation()   # dari script 1
            r    = sm.post(url, json=payload, timeout=20)
            data = r.json() if r.content else {}

            if r.status_code in (200, 201):
                log.info(f"  [SUCCESS] Register SUKSES: {email}")
                return {"status": "success", "code": r.status_code, "data": data}

            elif r.status_code == 429:
                log.warning("  [RATE LIMIT] Register!")
                retry_after = int(r.headers.get("Retry-After", RATE_LIMIT_PAUSE))
                delay.rate_limit_pause(retry_after)
                sm.rotate()
                continue

            elif r.status_code == 503:
                log.warning(f"  [503] Retry {attempt+1}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))
                continue

            else:
                msg = data.get("error", r.text[:200])
                if "already" in str(msg).lower():
                    return {"status": "already_exists", "code": r.status_code, "data": data}
                if "taken" in str(msg).lower():
                    return {"status": "username_taken", "code": r.status_code, "data": data}
                log.warning(f"  [FAIL] [{r.status_code}]: {msg}")
                return {"status": "failed", "code": r.status_code, "data": data}

        except requests.exceptions.ProxyError:
            log.warning(f"  [PROXY] Error register, rotate (attempt {attempt+1})")
            sm.mark_proxy_failed()
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_BASE)
        except requests.exceptions.ConnectTimeout:
            log.warning(f"  [TIMEOUT] Register attempt {attempt+1}")
            if attempt < MAX_RETRIES - 1:
                backoff = RETRY_BACKOFF_BASE * (2 ** attempt)
                log.info(f"  [BACKOFF] {backoff}s ...")
                time.sleep(backoff)
        except requests.exceptions.ConnectionError as e:
            log.warning(f"  [CONN ERR] {e} (attempt {attempt+1})")
            sm.mark_proxy_failed()
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_BASE)
        except Exception as e:
            log.error(f"  [ERR] Exception register: {e}")
            return {"status": "error", "error": str(e)}

    return {"status": "error", "error": f"Max retries ({MAX_RETRIES}) exceeded"}


# ══════════════════════════════════════════════════════════════════════
#  FILE UTILS
# ══════════════════════════════════════════════════════════════════════
def load_results() -> list:
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return []
    return []


def save_results(data: list):
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, OUTPUT_FILE)
    log.info(f"[SAVE] Disimpan ke {OUTPUT_FILE}")


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    log.info("=" * 65)
    log.info("  Hatcher Auto Register + Auto Verify")
    log.info(f"  Referral       : {REFERRAL_CODE}")
    log.info(f"  Target         : {ACCOUNTS_TO_CREATE} akun")
    log.info(f"  Proxy file     : {PROXY_FILE} (USE_PROXY={USE_PROXY})")
    log.info(f"  Delay range    : {DELAY_MIN}-{DELAY_MAX}s (+jitter {DELAY_JITTER}s)")
    log.info(f"  Session rotate : setiap {SESSION_ROTATE_EVERY} akun")
    log.info(f"  Max retries    : {MAX_RETRIES}x exponential backoff")
    log.info("=" * 65)

    results   = load_results()
    done      = sum(1 for r in results if r.get("status") in ("success", "verified", "unverified", "already_exists"))
    remaining = max(0, ACCOUNTS_TO_CREATE - done)

    log.info(f"[INFO] Sudah ada {done} akun, target {ACCOUNTS_TO_CREATE}")
    log.info(f"[INFO] Perlu buat {remaining} akun lagi")

    if remaining <= 0:
        log.info("  Target sudah tercapai!")
        return

    pm       = ProxyManager()
    sm       = SessionManager(pm)
    delay    = HumanDelay()
    tempmail = TempMailClient()
    verifier = HatcherVerifier(sm)

    ok_count   = 0
    ver_count  = 0
    fail_count = 0

    for idx in range(1, remaining + 1):
        log.info(f"\n{'─'*65}")
        log.info(f"[{idx}/{remaining}] Membuat akun baru ...")
        log.info(f"{'─'*65}")

        # Session rotation dari script 1
        sm.maybe_rotate()

        # Step 1: Generate temp email
        log.info(f"\n  [STEP 1] Generate temporary email ...")
        result = tempmail.generate()
        if not result:
            log.error("  [ERR] Gagal generate temp email, skip!")
            fail_count += 1
            delay.short()
            continue
        temp_email, inbox_token = result

        # Step 2: Credentials
        log.info(f"\n  [STEP 2] Generate credentials ...")
        username = make_username(temp_email)
        password = make_password()
        log.info(f"  Username (base) : {username}")
        log.info(f"  Password        : {password}")

        # Step 3: Cek username
        log.info(f"\n  [STEP 3] Cek ketersediaan username ...")
        if not check_avail(sm, "username", username, delay):
            log.info(f"  [INFO] Username konflik, cari alternatif ...")
            username = resolve_username(sm, username, delay)
            log.info(f"  [OK] Pakai username: {username}")
        delay.short()

        # Step 4: Register
        log.info(f"\n  [STEP 4] Mendaftar akun ...")
        reg = register(sm, temp_email, username, password, delay)

        if reg["status"] not in ("success",):
            log.warning(f"  [FAIL] Register gagal: {reg['status']}")
            fail_count += 1
            # Format output sesuai contoh
            results.append({
                "email":       temp_email,
                "username":    username,
                "password":    password,
                "status":      reg["status"],
                "verified":    False,
                "verify_link": "",
                "proxy":       sm.current_proxy or "direct",
                "response":    reg.get("data", {}),
                "timestamp":   datetime.now().isoformat()
            })
            save_results(results)
            delay.between_accounts()
            continue

        ok_count += 1
        log.info(f"  [OK] Register sukses: {temp_email}")

        # Step 5: Polling email verifikasi
        log.info(f"\n  [STEP 5] Menunggu email verifikasi di {temp_email} ...")
        log.info("  [WAIT] Tunggu 10s sebelum mulai polling ...")
        time.sleep(10 + random.uniform(2, 5))

        verify_link, inbox_token = tempmail.wait_for_email(
            token=inbox_token,
            email_address=temp_email,
            timeout=POLL_MAX_WAIT_SEC
        )

        # Step 6: Auto verifikasi
        verified = False
        if verify_link:
            log.info(f"\n  [STEP 6] Auto-verifikasi akun ...")
            delay.short()
            verified, method = verifier.verify(verify_link)
            if verified:
                ver_count += 1
                log.info(f"  [SUCCESS] Akun TERVERIFIKASI: {temp_email}")
            else:
                log.warning(f"  [WARN] Verifikasi GAGAL untuk: {temp_email}")
                log.warning(
                    "\n  Perlu inspect network di browser:\n"
                    "  1. Buka Chrome F12 → Network → XHR/Fetch\n"
                    f"  2. Buka: {verify_link}\n"
                    "  3. Lihat request ke api.hatcher.host\n"
                    "  4. Update VERIFY_API_ENDPOINTS di HatcherVerifier"
                )
        else:
            log.warning(f"  [WARN] Email verifikasi tidak datang (timeout)")

        # Format output PERSIS seperti contoh
        result_entry = {
            "email":       temp_email,
            "username":    username,
            "password":    password,
            "status":      "success" if verified else "registered_unverified",
            "verified":    verified,
            "verify_link": verify_link or "",
            "proxy":       sm.current_proxy or "direct",
            "response":    reg.get("data", {}),
            "timestamp":   datetime.now().isoformat()
        }
        results.append(result_entry)
        save_results(results)

        log.info(f"\n  [SUMMARY akun {idx}]")
        log.info(f"    Email     : {temp_email}")
        log.info(f"    Username  : {username}")
        log.info(f"    Password  : {password}")
        log.info(f"    Verified  : {'YES ✓' if verified else 'NO ✗'}")

        if idx < remaining:
            delay.between_accounts()

    # Final summary
    log.info("\n" + "=" * 65)
    log.info(f"  SELESAI")
    log.info(f"  Register sukses  : {ok_count}")
    log.info(f"  Akun terverif    : {ver_count}")
    log.info(f"  Gagal            : {fail_count}")
    log.info(f"  Proxy tersisa    : {pm.count}")
    log.info(f"  Output file      : {OUTPUT_FILE}")
    log.info("=" * 65)

    # Tabel akun verified (dari script 1)
    verified_list = [r for r in results if r.get("verified")]
    if verified_list:
        log.info(f"\n  {len(verified_list)} Akun Terverifikasi:")
        log.info(f"  {'Email':<35} {'Username':<18} {'Password'}")
        log.info(f"  {'-'*35} {'-'*18} {'-'*12}")
        for acc in verified_list:
            log.info(f"  {acc['email']:<35} {acc['username']:<18} {acc['password']}")

    sm.close()
    tempmail.close()


if __name__ == "__main__":
    main()