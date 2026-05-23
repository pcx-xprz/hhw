"""
Hatcher Auto Register + Auto Verify + Auto Create Agent
=========================================================
Gabungan dari auto_register2_w_proxy_tempmail_api.py + auto_create_agent.py

Perubahan:
  - 1 proxy untuk 1 akun (proxy yg sudah dipakai tidak akan dipakai akun lain)
  - Tidak pernah direct connection — wajib proxy semua
  - Jika proxy mati saat proses, auto cari proxy hidup dari pool untuk lanjut
  - Random User-Agent dan Accept-Language per akun
  - Setelah sukses register, langsung auto create agent di akun tersebut
    menggunakan proxy yang sama dengan yang dipakai saat register
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
AGENT_OUTPUT_FILE    = "agent_results.json"
PROXY_FILE           = "proxies_alive.txt"
LOG_FILE             = "register.log"
FAILED_PROXY_FILE    = "failed_proxies.txt"
DEBUG_EMAIL_DIR      = "debug_emails"

DELAY_MIN            = 8
DELAY_MAX            = 20
DELAY_BETWEEN_ACCS   = 30
DELAY_JITTER         = 3

SESSION_ROTATE_EVERY = 3

MAX_RETRIES          = 3
RETRY_BACKOFF_BASE   = 5
RATE_LIMIT_PAUSE     = 120

USE_PROXY            = True
PROXY_TIMEOUT        = 15
PROXY_TEST_TIMEOUT   = 20
PROXY_TEST_URLS      = [
    "http://httpbin.org/ip",
    "https://api.ipify.org?format=json",
    "http://ip-api.com/json",
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

# ─── USER-AGENT POOL ─────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) Gecko/20100101 Firefox/118.0",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.6; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_7_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.0.0",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.163 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
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
        """Build randomized headers. accept_language per-akun jika disuplai."""
        if ua is None:
            ua = random.choice(USER_AGENTS)

        is_chrome  = "Chrome" in ua and "Edg" not in ua
        is_edge    = "Edg" in ua
        is_firefox = "Firefox" in ua
        is_mobile  = self._is_mobile(ua)
        # Gunakan accept_language yang disuplai (per-akun) atau random
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
#  - 1 proxy untuk 1 akun (pakai used_proxies set, tidak pernah reuse)
#  - Tidak pernah direct connection
#  - Jika proxy mati, auto cari proxy hidup dari pool
# ══════════════════════════════════════════════════════════════════════
class ProxyManager:
    def __init__(self):
        self.proxies     = []     # semua proxy yang loaded
        self.failed      = set()  # proxy terbukti mati
        self.used        = set()  # proxy yang sudah dipakai per akun (tidak reuse)
        self.working     = []     # proxy yang sudah lulus test
        self.raw_idx     = 0
        self._load()
        self._initial_test()

    def _load(self):
        if not os.path.exists(PROXY_FILE):
            log.error(f"[PROXY] '{PROXY_FILE}' tidak ada. Script butuh proxy file!")
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
        if not self.proxies:
            return
        MAX_TEST = min(PROXY_MAX_TEST, len(self.proxies))
        log.info(f"[PROXY] Initial test {MAX_TEST} proxy ...")

        found = 0
        for i in range(MAX_TEST):
            p = self.proxies[i]
            log.info(f"  [PROXY] Test [{i+1}/{MAX_TEST}]: {p[:50]}")
            if self._do_test(p):
                self.working.append(p)
                found += 1

        if self.working:
            log.info(f"[PROXY] ✓ {len(self.working)} proxy aktif siap dipakai")
            random.shuffle(self.working)
        else:
            log.warning(f"[PROXY] ✗ Tidak ada proxy yang lulus test awal! Cek '{PROXY_FILE}'")

    def _do_test(self, proxy_url: str) -> bool:
        proxy_dict = self.get_proxy_dict(proxy_url)
        for test_url in PROXY_TEST_URLS:
            try:
                r = requests.get(
                    test_url, proxies=proxy_dict,
                    timeout=PROXY_TEST_TIMEOUT,
                    headers={"User-Agent": random.choice(USER_AGENTS)},
                    verify=False
                )
                if r.status_code == 200:
                    try:
                        ip_data = r.json()
                        ip = (ip_data.get("ip") or ip_data.get("query") or
                              ip_data.get("origin", "?"))
                        log.info(f"  [PROXY] ✓ {proxy_url[:45]} → IP: {ip}")
                    except Exception:
                        log.info(f"  [PROXY] ✓ {proxy_url[:45]} → OK")
                    return True
            except requests.exceptions.ConnectTimeout:
                continue
            except requests.exceptions.ProxyError:
                break
            except requests.exceptions.SSLError:
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
        if not p:
            return
        if p not in self.failed:
            self.failed.add(p)
            with open(FAILED_PROXY_FILE, "a") as f:
                f.write(p + "\n")
            log.warning(f"[PROXY] ✗ Marked failed: {p[:50]}")

        if p in self.working:
            self.working.remove(p)
        if p in self.proxies:
            self.proxies.remove(p)
        # Hapus dari used juga agar tidak dianggap "dipakai" padahal mati
        self.used.discard(p)
        log.info(f"[PROXY] Sisa working: {len(self.working)} | Total: {len(self.proxies)}")


    def get_fresh_proxy(self) -> Optional[str]:
        """
        Ambil proxy BARU yang belum pernah dipakai akun manapun.
        Tidak pernah direct connection — jika semua habis/mati, test pool baru.
        Return None HANYA jika benar-benar tidak ada proxy sama sekali (hard stop).
        """
        # ── Cari dari working list yang belum dipakai ──────────────────
        available_working = [p for p in self.working if p not in self.used]
        if available_working:
            proxy = random.choice(available_working)
            self.used.add(proxy)
            log.info(
                f"  [PROXY] Akun ini pakai (fresh): {proxy[:50]}\n"
                f"  [PROXY] (used={len(self.used)}, working={len(self.working)}, total={len(self.proxies)})"
            )
            return proxy

        # ── Working habis/semua sudah dipakai, test proxy baru dari pool ──
        log.info("[PROXY] Cari proxy fresh dari pool, mulai test ...")
        untried = [p for p in self.proxies if p not in self.used and p not in self.failed]

        if untried:
            random.shuffle(untried)
            for p in untried[:min(20, len(untried))]:
                log.info(f"  [PROXY] Test fresh proxy: {p[:50]}")
                if self._do_test(p):
                    if p not in self.working:
                        self.working.append(p)
                    self.used.add(p)
                    log.info(f"[PROXY] ✓ Fresh proxy ditemukan dan dipakai: {p[:50]}")
                    return p
                else:
                    self.mark_failed(p)

        # ── Tidak ada proxy fresh, paksa test ulang semua sisa pool ──────
        all_remaining = [p for p in self.proxies if p not in self.failed]
        if all_remaining:
            log.warning("[PROXY] Semua proxy sudah terpakai, test ulang sisa pool ...")
            random.shuffle(all_remaining)
            for p in all_remaining[:min(30, len(all_remaining))]:
                log.info(f"  [PROXY] Re-test: {p[:50]}")
                if self._do_test(p):
                    if p not in self.working:
                        self.working.append(p)
                    self.used.add(p)
                    log.info(f"[PROXY] ✓ Re-test proxy OK, dipakai: {p[:50]}")
                    return p
                else:
                    self.mark_failed(p)

        # ── Benar-benar tidak ada proxy ────────────────────────────────
        log.error("[PROXY] KRITIS: Tidak ada proxy tersedia sama sekali!")
        log.error("[PROXY] Direct connection DILARANG. Tambahkan proxy ke proxies_alive.txt!")
        return None

    def find_alive_proxy_for_retry(self, exclude: str = None) -> Optional[str]:
        """
        Cari proxy hidup dari pool untuk melanjutkan proses yang sedang berjalan.
        Dipanggil ketika proxy mati di tengah proses.
        Exclude proxy yang baru saja mati.
        """
        log.info("[PROXY] Mencari proxy hidup untuk lanjutkan proses ...")
        candidates = [
            p for p in self.proxies
            if p not in self.failed and p != exclude
        ]
        random.shuffle(candidates)

        for p in candidates[:min(15, len(candidates))]:
            log.info(f"  [PROXY] Test for retry: {p[:50]}")
            if self._do_test(p):
                if p not in self.working:
                    self.working.append(p)
                log.info(f"[PROXY] ✓ Proxy untuk retry: {p[:50]}")
                return p
            else:
                self.mark_failed(p)

        log.error("[PROXY] Tidak ada proxy hidup untuk retry!")
        return None

    def replenish_working(self, min_count: int = 3):
        if len(self.working) >= min_count:
            return
        if not self.proxies:
            return
        needed = min_count - len(self.working)
        log.info(f"[PROXY] Replenish working list (perlu {needed} proxy lagi) ...")
        added = 0
        candidates = [p for p in self.proxies if p not in self.working and p not in self.failed]
        for p in candidates[:min(needed * 3, len(candidates))]:
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
#  HUMAN DELAY
# ══════════════════════════════════════════════════════════════════════
class HumanDelay:
    def __init__(self):
        self.request_count = 0

    def _jitter(self, base: float) -> float:
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
        for _ in range(random.randint(2, 5)):
            time.sleep(random.uniform(0.1, 0.4))


# ══════════════════════════════════════════════════════════════════════
#  SESSION MANAGER
#  - Setiap akun mendapat proxy BARU (1 proxy = 1 akun)
#  - Jika proxy mati di tengah proses, auto switch ke proxy hidup
#  - Tidak pernah direct connection
#  - UA dan Accept-Language random per-akun (di-assign saat buat session)
# ══════════════════════════════════════════════════════════════════════
class SessionManager:
    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager    = proxy_manager
        self.header_factory   = HeaderFactory()
        self.session          = None
        self.current_proxy    = None
        self.current_ua       = None
        self.current_lang     = None   # Accept-Language per-akun
        self.account_count    = 0
        self._create_new_session()

    def _create_new_session(self, proxy_override: str = None):
        """
        Buat session baru.
        proxy_override: jika ada, pakai proxy ini (untuk retry dengan proxy baru).
        """
        if self.session:
            self.session.close()

        # Random UA dan Accept-Language per-session (per-akun)
        self.current_ua   = random.choice(USER_AGENTS)
        self.current_lang = random.choice(ACCEPT_LANGUAGES)
        log.info(f"  [SESSION] UA      : {self.current_ua[:60]}...")
        log.info(f"  [SESSION] Lang    : {self.current_lang}")

        self.session = requests.Session()

        if proxy_override:
            self.current_proxy = proxy_override
        elif USE_PROXY:
            # Ambil proxy BARU yang belum pernah dipakai
            self.current_proxy = self.proxy_manager.get_fresh_proxy()
        else:
            self.current_proxy = None

        if self.current_proxy:
            self.session.proxies.update(
                self.proxy_manager.get_proxy_dict(self.current_proxy)
            )
            log.info(f"  [SESSION] Proxy   : {self.current_proxy}")
        else:
            # Proxy tidak tersedia — hentikan proses (tidak boleh direct)
            log.error("  [SESSION] FATAL: Tidak ada proxy tersedia. Proses dihentikan!")
            raise RuntimeError("Tidak ada proxy tersedia. Tambahkan proxy ke proxies_alive.txt!")

        self.session.timeout = 20

    def rotate_for_new_account(self):
        """Panggil setiap kali mau proses akun baru. Proxy baru per akun."""
        self.account_count += 1
        log.info(f"  [SESSION] Rotate untuk akun baru (akun #{self.account_count}) ...")
        self._create_new_session()

    def switch_proxy_on_failure(self):
        """
        Proxy mati di tengah proses. Tandai mati, cari proxy hidup baru.
        Session tetap, hanya proxy diganti.
        """
        failed_proxy = self.current_proxy
        if failed_proxy:
            self.proxy_manager.mark_failed(failed_proxy)
            self.proxy_manager.replenish_working(min_count=3)

        # Cari proxy hidup untuk melanjutkan proses ini
        new_proxy = self.proxy_manager.find_alive_proxy_for_retry(exclude=failed_proxy)
        if not new_proxy:
            log.error("  [SESSION] Tidak ada proxy hidup untuk melanjutkan! Proses berhenti.")
            raise RuntimeError("Proxy habis semua. Tidak bisa lanjut tanpa proxy!")

        # Tandai proxy baru sebagai "used" untuk akun ini
        self.proxy_manager.used.add(new_proxy)
        self.current_proxy = new_proxy

        # Rebuild session dengan proxy baru
        self.session.close()
        self.session = requests.Session()
        self.session.proxies.update(self.proxy_manager.get_proxy_dict(new_proxy))
        self.session.timeout = 20
        log.info(f"  [SESSION] ✓ Switched ke proxy baru: {new_proxy[:50]}")

    def get(self, url: str, **kwargs) -> requests.Response:
        referer = kwargs.pop("referer", None)
        headers = self.header_factory.build(
            self.current_ua, referer=referer,
            accept_language=self.current_lang
        )
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        return self.session.get(url, headers=headers, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        referer = kwargs.pop("referer", None)
        headers = self.header_factory.build(
            self.current_ua, referer=referer,
            accept_language=self.current_lang
        )
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        return self.session.post(url, headers=headers, **kwargs)

    def mark_proxy_failed(self):
        """Tandai proxy saat ini mati dan switch ke proxy hidup baru."""
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
            accept_language=self.sm.current_lang
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
                    url, headers=headers, timeout=20, allow_redirects=True
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
            except Exception:
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
#  HATCHER REGISTER FUNCTIONS
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
                sm.mark_proxy_failed()
                continue
            else:
                log.warning(f"  [WARN] check-availability [{r.status_code}]: {r.text[:100]}")
                return False
        except requests.exceptions.ProxyError:
            log.warning(f"  [PROXY] Error cek {field}, ganti proxy ...")
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
    for attempt in range(MAX_RETRIES):
        try:
            delay.typing_simulation()
            r    = sm.post(url, json=payload, timeout=20)
            data = r.json() if r.content else {}

            if r.status_code in (200, 201):
                log.info(f"  [SUCCESS] Register SUKSES: {email}")
                return {"status": "success", "code": r.status_code, "data": data}

            elif r.status_code == 429:
                log.warning("  [RATE LIMIT] Register!")
                retry_after = int(r.headers.get("Retry-After", RATE_LIMIT_PAUSE))
                delay.rate_limit_pause(retry_after)
                sm.mark_proxy_failed()
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
            log.warning(f"  [PROXY] Error register, ganti proxy (attempt {attempt+1})")
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
#  AUTO CREATE AGENT FUNCTIONS
#  Diambil dari auto_create_agent.py — dijalankan setelah register sukses
#  Menggunakan session & proxy yang SAMA dengan register
# ══════════════════════════════════════════════════════════════════════
def _auth_headers_agent(token: str, ua: str, lang: str) -> dict:
    """Build auth headers untuk request agent dengan UA & lang per-akun."""
    return {
        "Content-Type":    "application/json",
        "Accept":          "application/json",
        "Origin":          "https://hatcher.host",
        "Referer":         "https://hatcher.host/create",
        "User-Agent":      ua,
        "Accept-Language": lang,
        "Authorization":   f"Bearer {token}",
    }


def agent_login(session: requests.Session, email: str, password: str,
                ua: str, lang: str) -> Optional[dict]:
    """
    POST /auth/login — login dengan akun yang baru diregist.
    Gunakan session & proxy yang sama dengan register.
    """
    url = f"{HATCHER_BASE_API}/auth/login"
    base_headers = {
        "Content-Type":    "application/json",
        "Accept":          "application/json",
        "Origin":          "https://hatcher.host",
        "Referer":         "https://hatcher.host/login",
        "User-Agent":      ua,
        "Accept-Language": lang,
    }
    payload = {"email": email, "password": password}
    try:
        r = session.post(url, headers=base_headers, json=payload, timeout=20)
        data = r.json() if r.content else {}
        if r.status_code == 200 and data.get("success"):
            token = data["data"]["token"]
            user  = data["data"]["user"]
            log.info(f"  [OK] Login agent sukses: {email} (id={user['id']})")
            return {"token": token, "refreshToken": data["data"].get("refreshToken"), "user": user}
        else:
            err = data.get("error", r.text)
            log.warning(f"  [FAIL] Login agent gagal [{r.status_code}]: {err}")
            return None
    except Exception as e:
        log.error(f"  [ERR] Login agent exception: {e}")
        return None


def agent_create(session: requests.Session, token: str, username: str,
                 ua: str, lang: str) -> Optional[dict]:
    """POST /agents — buat agent baru."""
    url     = f"{HATCHER_BASE_API}/agents"
    name    = AGENT_NAME_TEMPLATE.format(username=username)
    payload = {"name": name, "isPublic": AGENT_IS_PUBLIC}
    try:
        r = session.post(url, headers=_auth_headers_agent(token, ua, lang),
                         json=payload, timeout=20)
        data = r.json() if r.content else {}
        if r.status_code in (200, 201) and data.get("success"):
            agent = data["data"]
            log.info(f"  [OK] Agent dibuat: '{agent['name']}' (id={agent['id']})")
            return agent

        err = data.get("error", r.text)
        # Sudah punya agent (free tier limit 1)
        if r.status_code == 400 and "maximum" in err.lower() and "agent" in err.lower():
            log.warning("  [WARN] Akun sudah punya agent (limit free tier)")
            log.info("  [INFO] Ambil agent existing via GET /agents ...")
            r2 = session.get(url, headers=_auth_headers_agent(token, ua, lang), timeout=15)
            d2 = r2.json() if r2.content else {}
            if d2.get("success") and d2.get("data"):
                existing = d2["data"][0]
                log.info(f"  [OK] Agent existing: '{existing['name']}' (id={existing['id']})")
                existing["_existing"] = True
                return existing
            log.warning("  [WARN] Tidak bisa ambil agent existing")
            return None

        log.warning(f"  [FAIL] Create agent gagal [{r.status_code}]: {err}")
        return None
    except Exception as e:
        log.error(f"  [ERR] Create agent exception: {e}")
        return None


def agent_start(session: requests.Session, token: str, agent_id: str,
                ua: str, lang: str) -> bool:
    """POST /agents/{id}/start — hatch agent."""
    url = f"{HATCHER_BASE_API}/agents/{agent_id}/start"
    try:
        r = session.post(url, headers=_auth_headers_agent(token, ua, lang),
                         json={}, timeout=30)
        data = r.json() if r.content else {}
        if r.status_code == 200 and data.get("success"):
            status    = data["data"].get("status", "unknown")
            container = data["data"].get("containerId", "")[:20]
            log.info(f"  [OK] Agent started: status={status}, container={container}...")
            return True
        else:
            err = data.get("error", r.text)
            log.warning(f"  [FAIL] Start agent gagal [{r.status_code}]: {err}")
            return False
    except Exception as e:
        log.error(f"  [ERR] Start agent exception: {e}")
        return False


def agent_configure(session: requests.Session, token: str, agent_id: str,
                    username: str, ua: str, lang: str) -> bool:
    """PATCH /agents/{id} — konfigurasi agent."""
    url     = f"{HATCHER_BASE_API}/agents/{agent_id}"
    payload = {
        "description": AGENT_DESCRIPTION,
        "config": {
            "systemPrompt": AGENT_SYSTEM_PROMPT,
            "model":        AGENT_MODEL,
        },
        "isPublic": AGENT_IS_PUBLIC,
    }
    try:
        r = session.patch(url, headers=_auth_headers_agent(token, ua, lang),
                          json=payload, timeout=20)
        data = r.json() if r.content else {}
        if r.status_code == 200 and data.get("success"):
            log.info(f"  [OK] Agent dikonfigurasi: model={AGENT_MODEL}")
            return True
        else:
            err = data.get("error", r.text)
            log.warning(f"  [WARN] Config agent gagal [{r.status_code}]: {err}")
            return False
    except Exception as e:
        log.error(f"  [ERR] Configure agent exception: {e}")
        return False


def auto_create_agent_for_account(
    session: requests.Session,
    email: str,
    password: str,
    username: str,
    proxy_str: str,
    ua: str,
    lang: str,
    delay: HumanDelay
) -> dict:
    """
    Jalankan full flow create agent untuk 1 akun.
    Dipanggil tepat setelah register sukses.
    Menggunakan session & proxy yang SAMA dengan register.

    Return dict hasil agent:
      { agent_id, agent_name, agent_slug, agent_url, agent_status, agent_configured }
    """
    result = {
        "agent_status":     "pending",
        "agent_id":         None,
        "agent_name":       None,
        "agent_slug":       None,
        "agent_url":        None,
        "agent_configured": False,
        "agent_proxy":      proxy_str,
    }

    log.info(f"\n  ── AUTO CREATE AGENT ──────────────────────────────────")
    log.info(f"  Proxy    : {proxy_str}")
    log.info(f"  Email    : {email}")

    # Step 1: Login
    log.info("  [A-1/4] Login untuk create agent ...")
    delay.short()
    auth = agent_login(session, email, password, ua, lang)
    if not auth:
        result["agent_status"] = "login_failed"
        log.error("  [AGENT] Login gagal, skip create agent")
        return result

    token   = auth["token"]
    delay.short()

    # Step 2: Create Agent
    log.info("  [A-2/4] Membuat agent ...")
    agent = agent_create(session, token, username, ua, lang)
    if not agent:
        result["agent_status"] = "create_failed"
        log.error("  [AGENT] Create agent gagal")
        return result

    agent_id    = agent["id"]
    agent_name  = agent["name"]
    agent_slug  = agent["slug"]
    is_existing = agent.get("_existing", False)

    result["agent_id"]    = agent_id
    result["agent_name"]  = agent_name
    result["agent_slug"]  = agent_slug
    result["agent_url"]   = f"https://hatcher.host/agent/{agent_slug}"
    result["agent_reused"] = is_existing

    if is_existing:
        log.info(f"  [INFO] Pakai agent existing: '{agent_name}'")
    delay.short()

    # Step 3: Start/Hatch Agent
    current_status = agent.get("status", "")
    if current_status == "active":
        log.info("  [A-3/4] Agent sudah ACTIVE, skip start ...")
        started = True
    else:
        log.info("  [A-3/4] Menjalankan agent (hatch) ...")
        started = agent_start(session, token, agent_id, ua, lang)

    if not started:
        result["agent_status"] = "start_failed"
        log.error("  [AGENT] Start agent gagal")
        return result

    log.info("  [INFO] Menunggu container siap (5s) ...")
    time.sleep(5)

    # Step 4: Configure Agent
    log.info("  [A-4/4] Mengkonfigurasi agent ...")
    configured = agent_configure(session, token, agent_id, username, ua, lang)

    result["agent_status"]     = "active"
    result["agent_configured"] = configured

    log.info(f"  [SUCCESS] Agent aktif!")
    log.info(f"  URL: https://hatcher.host/agent/{agent_slug}")

    return result



# ══════════════════════════════════════════════════════════════════════
#  FILE UTILS
# ══════════════════════════════════════════════════════════════════════
def load_results() -> list:
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []


def save_results(data: list):
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, OUTPUT_FILE)
    log.info(f"[SAVE] Disimpan ke {OUTPUT_FILE}")


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
    log.info(f"[SAVE] Agent results disimpan ke {AGENT_OUTPUT_FILE}")


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    log.info("=" * 65)
    log.info("  Hatcher Auto Register + Auto Verify + Auto Create Agent")
    log.info(f"  Referral       : {REFERRAL_CODE}")
    log.info(f"  Target         : {ACCOUNTS_TO_CREATE} akun")
    log.info(f"  Proxy file     : {PROXY_FILE} (USE_PROXY={USE_PROXY})")
    log.info(f"  Delay range    : {DELAY_MIN}-{DELAY_MAX}s (+jitter {DELAY_JITTER}s)")
    log.info(f"  Session rotate : setiap akun (1 proxy = 1 akun)")
    log.info(f"  Max retries    : {MAX_RETRIES}x exponential backoff")
    log.info(f"  Agent model    : {AGENT_MODEL}")
    log.info("=" * 65)

    results        = load_results()
    agent_results  = load_agent_results()

    done      = sum(1 for r in results if r.get("status") in ("success", "verified", "unverified", "already_exists"))
    remaining = max(0, ACCOUNTS_TO_CREATE - done)

    log.info(f"[INFO] Sudah ada {done} akun, target {ACCOUNTS_TO_CREATE}")
    log.info(f"[INFO] Perlu buat {remaining} akun lagi")

    if remaining <= 0:
        log.info("  Target sudah tercapai!")
        return

    pm       = ProxyManager()

    if pm.count == 0:
        log.error("[FATAL] Tidak ada proxy tersedia. Buat file proxies_alive.txt dengan daftar proxy!")
        return

    try:
        sm = SessionManager(pm)
    except RuntimeError as e:
        log.error(f"[FATAL] {e}")
        return

    delay    = HumanDelay()
    tempmail = TempMailClient()
    verifier = HatcherVerifier(sm)

    ok_count    = 0
    ver_count   = 0
    agent_ok    = 0
    fail_count  = 0

    for idx in range(1, remaining + 1):
        log.info(f"\n{'─'*65}")
        log.info(f"[{idx}/{remaining}] Membuat akun baru ...")
        log.info(f"{'─'*65}")

        # Rotate session → proxy BARU per akun
        try:
            sm.rotate_for_new_account()
        except RuntimeError as e:
            log.error(f"[FATAL] {e}")
            break

        # Catat proxy & fingerprint yang dipakai akun ini
        account_proxy = sm.current_proxy
        account_ua    = sm.current_ua
        account_lang  = sm.current_lang

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
            results.append({
                "email":       temp_email,
                "username":    username,
                "password":    password,
                "status":      reg["status"],
                "verified":    False,
                "verify_link": "",
                "proxy":       account_proxy or "direct",
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

        # Simpan hasil register
        result_entry = {
            "email":       temp_email,
            "username":    username,
            "password":    password,
            "status":      "success" if verified else "registered_unverified",
            "verified":    verified,
            "verify_link": verify_link or "",
            "proxy":       account_proxy or "direct",
            "response":    reg.get("data", {}),
            "timestamp":   datetime.now().isoformat()
        }
        results.append(result_entry)
        save_results(results)

        log.info(f"\n  [SUMMARY Register #{idx}]")
        log.info(f"    Email     : {temp_email}")
        log.info(f"    Username  : {username}")
        log.info(f"    Password  : {password}")
        log.info(f"    Verified  : {'YES ✓' if verified else 'NO ✗'}")
        log.info(f"    Proxy     : {account_proxy}")

        # ── Step 7: AUTO CREATE AGENT ──────────────────────────────────
        # Langsung buat agent di akun yg baru sukses register
        # Gunakan session & proxy yang SAMA dengan register
        log.info(f"\n  [STEP 7] Auto Create Agent untuk akun baru ...")
        delay.short()

        agent_result = auto_create_agent_for_account(
            session   = sm.session,
            email     = temp_email,
            password  = password,
            username  = username,
            proxy_str = account_proxy or "direct",
            ua        = account_ua,
            lang      = account_lang,
            delay     = delay
        )

        # Simpan hasil agent
        agent_entry = {
            "email":            temp_email,
            "username":         username,
            "verified":         verified,
            "proxy":            account_proxy or "direct",
            "timestamp":        datetime.now().isoformat(),
            **agent_result
        }
        agent_results.append(agent_entry)
        save_agent_results(agent_results)

        if agent_result["agent_status"] == "active":
            agent_ok += 1
            log.info(f"  [SUCCESS] Agent aktif: {agent_result.get('agent_url', '-')}")
        else:
            log.warning(f"  [WARN] Agent gagal dibuat: {agent_result['agent_status']}")

        if idx < remaining:
            delay.between_accounts()

    # Final summary
    log.info("\n" + "=" * 65)
    log.info(f"  SELESAI")
    log.info(f"  Register sukses  : {ok_count}")
    log.info(f"  Akun terverif    : {ver_count}")
    log.info(f"  Agent berhasil   : {agent_ok}")
    log.info(f"  Gagal            : {fail_count}")
    log.info(f"  Proxy tersisa    : {pm.count}")
    log.info(f"  Proxy terpakai   : {len(pm.used)}")
    log.info(f"  Output register  : {OUTPUT_FILE}")
    log.info(f"  Output agent     : {AGENT_OUTPUT_FILE}")
    log.info("=" * 65)

    # Tabel akun verified
    verified_list = [r for r in results if r.get("verified")]
    if verified_list:
        log.info(f"\n  {len(verified_list)} Akun Terverifikasi:")
        log.info(f"  {'Email':<35} {'Username':<18} {'Password'}")
        log.info(f"  {'-'*35} {'-'*18} {'-'*12}")
        for acc in verified_list:
            log.info(f"  {acc['email']:<35} {acc['username']:<18} {acc['password']}")

    # Tabel agent aktif
    active_agents = [r for r in agent_results if r.get("agent_status") == "active"]
    if active_agents:
        log.info(f"\n  {len(active_agents)} Agent Aktif:")
        log.info(f"  {'Email':<35} {'Proxy':<22} {'Agent URL'}")
        log.info(f"  {'-'*35} {'-'*22} {'-'*40}")
        for r in active_agents:
            proxy = (r.get("proxy") or "direct")[:20]
            log.info(f"  {r['email']:<35} {proxy:<22} {r.get('agent_url', '-')}")

    sm.close()
    tempmail.close()


if __name__ == "__main__":
    main()
