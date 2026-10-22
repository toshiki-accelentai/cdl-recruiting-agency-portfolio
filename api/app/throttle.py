"""A speed limit for wrong passwords.

Two counters, both over a sliding window (default 15 minutes):
  per (client address, username)  5 wrong passwords, then wait: stops guessing one account
  per client address             20 wrong passwords across any usernames, then wait: stops trying many names

Keyed by client address on purpose: a stranger can only block their own address, never lock the owner out.
State is in memory (one API process), so a restart clears it. That is acceptable for a demo login.
"""
import math
import time
from collections import deque

MAX_PER_USER_AND_ADDRESS = 5
MAX_PER_ADDRESS = 20
WINDOW_SECONDS = 15 * 60
PRUNE_ABOVE_KEYS = 5000  # only then is it worth walking every entry to drop the expired ones
MAX_USERNAME_LENGTH = 100
MAX_ADDRESS_LENGTH = 64


def client_ip(request) -> str:
    """The real client address. Behind Caddy it is the first X-Forwarded-For entry (Caddy sets it).

    The API is reachable only through Caddy, which replaces what a visitor sends, so it cannot be faked.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first[:MAX_ADDRESS_LENGTH]
    return (request.client.host if request.client else "unknown")[:MAX_ADDRESS_LENGTH]


class LoginThrottle:
    def __init__(self, clock=time.monotonic, max_per_user_ip=MAX_PER_USER_AND_ADDRESS,
                 max_per_ip=MAX_PER_ADDRESS, window_seconds=WINDOW_SECONDS):
        self._clock = clock
        self._max_per_user_ip = max_per_user_ip
        self._max_per_ip = max_per_ip
        self._window = window_seconds
        self._by_user_ip: dict[tuple[str, str], deque] = {}
        self._by_ip: dict[str, deque] = {}
        self._next_prune_at = 0.0

    @staticmethod
    def _name(username: str) -> str:
        return (username or "").strip().lower()[:MAX_USERNAME_LENGTH]

    def _recent(self, bucket: dict, key) -> deque | None:
        """The failures still inside the window (older ones are dropped)."""
        times = bucket.get(key)
        if times is None:
            return None
        cutoff = self._clock() - self._window
        while times and times[0] <= cutoff:
            times.popleft()
        if not times:
            del bucket[key]
            return None
        return times

    def blocked_for(self, ip: str, username: str) -> int:
        """Seconds to wait before another try, 0 if allowed."""
        waits = []
        for bucket, key, limit in ((self._by_user_ip, (ip, self._name(username)), self._max_per_user_ip),
                                   (self._by_ip, ip, self._max_per_ip)):
            times = self._recent(bucket, key)
            if times is not None and len(times) >= limit:
                # the count drops below the limit when the limit-th most recent failure leaves the window
                waits.append(times[-limit] + self._window - self._clock())
        return max(1, math.ceil(max(waits))) if waits else 0

    def record_failure(self, ip: str, username: str) -> None:
        now = self._clock()
        if len(self._by_user_ip) + len(self._by_ip) > PRUNE_ABOVE_KEYS and now >= self._next_prune_at:
            self._prune()
            self._next_prune_at = now + self._window / 10
        self._by_user_ip.setdefault((ip, self._name(username)), deque(maxlen=self._max_per_user_ip)).append(now)
        self._by_ip.setdefault(ip, deque(maxlen=self._max_per_ip)).append(now)

    def record_success(self, ip: str, username: str) -> None:
        self._by_user_ip.pop((ip, self._name(username)), None)

    def _prune(self) -> None:
        for bucket in (self._by_user_ip, self._by_ip):
            for key in list(bucket):
                self._recent(bucket, key)

    def tracked_keys(self) -> int:
        return len(self._by_user_ip) + len(self._by_ip)

    def reset(self) -> None:
        self._by_user_ip.clear()
        self._by_ip.clear()
        self._next_prune_at = 0.0


login_throttle = LoginThrottle()


MAX_WRITES = 30  # a person clicking "Called" or fixing a field does not come near this
WRITE_WINDOW_SECONDS = 60


class WriteThrottle:
    """A speed limit for a logged-in user's writes: at most `max_writes` in any `window_seconds`, per user.

    Reads are never limited. State is in memory (one API process), like the login throttle.
    """

    def __init__(self, clock=time.monotonic, max_writes=MAX_WRITES, window_seconds=WRITE_WINDOW_SECONDS):
        self._clock = clock
        self._max = max_writes
        self._window = window_seconds
        self._by_user: dict[int, deque] = {}

    def hit(self, user_id: int) -> int:
        """Count one write attempt. Returns 0 if allowed, else the seconds to wait (a refused attempt is not counted)."""
        now = self._clock()
        times = self._by_user.setdefault(user_id, deque(maxlen=self._max))
        while times and times[0] <= now - self._window:
            times.popleft()
        if len(times) >= self._max:
            return max(1, math.ceil(times[0] + self._window - now))
        times.append(now)
        return 0

    def reset(self) -> None:
        self._by_user.clear()


write_throttle = WriteThrottle()
