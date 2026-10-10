"""Who is signed in: the Cloudflare Access token, checked by the Worker.

PLAN-v2-phase1.md, decision 4. Access decides who gets as far as /edit and
/api; this decides who the request is from. Every such request carries
Access's token in the Cf-Access-Jwt-Assertion header, and `verify` checks
its signature against the team's published keys, its audience (this
Access application's tag), its issuer, and its expiry, and returns the
email in it. Anything that doesn't check out raises Refused. An email the
page sends is never trusted; only this one is.

The RS256 signature check is plain Python (RSASSA-PKCS1-v1_5 verify is
one modular power and a byte comparison), not Web Crypto, so v2/tests run
the same code the Worker does. Verifying uses only the public key, so
there's no timing concern; the whole expected encoding is built and
compared, never parsed out of the signature.

The keys are fetched through a function the caller passes (the Worker's
fetch; a fake in tests) and kept for an hour. A token signed with a key
not in hand fetches them again, at most once every five minutes, since
Access rotates its keys.
"""
import base64
import hashlib
import hmac
import json
import time

# DER prefix of a SHA-256 DigestInfo (RFC 8017, section 9.2, note 1).
SHA256_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
LEEWAY = 60  # seconds of clock difference allowed on exp and nbf


class Refused(Exception):
    """The request has no token, or one that doesn't check out."""


def b64url(s):
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except (ValueError, TypeError) as e:
        raise Refused("malformed token") from e


def rs256_ok(jwk, signed, signature):
    """Whether `signature` is `jwk`'s RS256 signature over `signed`."""
    if jwk.get("kty") != "RSA":
        return False
    n = int.from_bytes(b64url(jwk["n"]), "big")
    e = int.from_bytes(b64url(jwk["e"]), "big")
    k = (n.bit_length() + 7) // 8
    if n.bit_length() < 2048 or len(signature) != k:
        return False
    s = int.from_bytes(signature, "big")
    if s >= n:
        return False
    digest = SHA256_INFO + hashlib.sha256(signed).digest()
    expected = b"\x00\x01" + b"\xff" * (k - len(digest) - 3) + b"\x00" + digest
    return hmac.compare_digest(pow(s, e, n).to_bytes(k, "big"), expected)


class Keys:
    """The team's signing keys, by key ID. `fetch_text(url)` is an async
    function returning the response body as a str."""

    TTL = 3600
    REFETCH_GAP = 300

    def __init__(self, team_domain, fetch_text):
        self.url = f"{team_domain}/cdn-cgi/access/certs"
        self.fetch_text = fetch_text
        self.keys = {}
        self.fetched_at = None

    async def _fetch(self, now):
        certs = json.loads(await self.fetch_text(self.url))
        self.keys = {k["kid"]: k for k in certs.get("keys", []) if "kid" in k}
        self.fetched_at = now

    async def get(self, kid, now):
        if self.fetched_at is None or now - self.fetched_at > self.TTL:
            await self._fetch(now)
        elif kid not in self.keys and now - self.fetched_at > self.REFETCH_GAP:
            await self._fetch(now)
        return self.keys.get(kid)


async def verify(token, keys, team_domain, aud, now=None):
    """The signed-in email, lower case, from an Access token; raises
    Refused unless signature, audience, issuer, and expiry all check
    out."""
    if not token:
        raise Refused("no token")
    now = time.time() if now is None else now
    parts = token.split(".")
    if len(parts) != 3:
        raise Refused("malformed token")
    try:
        header = json.loads(b64url(parts[0]))
        claims = json.loads(b64url(parts[1]))
    except ValueError as e:
        raise Refused("malformed token") from e
    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise Refused("malformed token")
    if header.get("alg") != "RS256":
        raise Refused(f"unexpected alg {header.get('alg')!r}")
    jwk = await keys.get(header.get("kid"), now)
    if jwk is None:
        raise Refused("no matching signing key")
    if not rs256_ok(jwk, f"{parts[0]}.{parts[1]}".encode(), b64url(parts[2])):
        raise Refused("bad signature")
    auds = claims.get("aud") if isinstance(claims.get("aud"), list) else [claims.get("aud")]
    if aud not in auds:
        raise Refused("wrong audience")
    if claims.get("iss") != team_domain:
        raise Refused("wrong issuer")
    exp, nbf = claims.get("exp"), claims.get("nbf", 0)
    if not isinstance(exp, (int, float)) or exp + LEEWAY < now:
        raise Refused("expired")
    if not isinstance(nbf, (int, float)) or nbf - LEEWAY > now:
        raise Refused("not valid yet")
    email = claims.get("email")
    if not isinstance(email, str) or "@" not in email:
        raise Refused("no email in token")
    return email.strip().lower()
