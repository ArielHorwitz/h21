from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field


CHALLENGE_TTL_SECONDS = 300  # 5 minutes


@dataclass
class _PendingChallenge:
    challenge: str
    created_at: float


@dataclass
class ProofOfWork:
    difficulty: int
    _challenges: dict[str, _PendingChallenge] = field(
        default_factory=dict, init=False
    )

    def generate_challenge(self) -> tuple[str, str]:
        """Return (challenge_id, challenge_string)."""
        challenge_id = secrets.token_hex(16)
        challenge = secrets.token_hex(32)
        self._challenges[challenge_id] = _PendingChallenge(
            challenge=challenge, created_at=time.monotonic()
        )
        self._prune_expired()
        return challenge_id, challenge

    def verify(self, challenge_id: str, nonce: str) -> bool:
        """Verify a PoW solution. Consumes the challenge on success."""
        self._prune_expired()

        pending = self._challenges.pop(challenge_id, None)
        if pending is None:
            return False

        digest = hashlib.sha256(
            (pending.challenge + nonce).encode()
        ).hexdigest()
        binary = bin(int(digest, 16))[2:].zfill(256)
        return binary[: self.difficulty] == "0" * self.difficulty

    def _prune_expired(self) -> None:
        now = time.monotonic()
        expired = [
            challenge_id
            for challenge_id, pending in self._challenges.items()
            if now - pending.created_at > CHALLENGE_TTL_SECONDS
        ]
        for challenge_id in expired:
            del self._challenges[challenge_id]
