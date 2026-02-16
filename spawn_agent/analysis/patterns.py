"""
Pattern matching for on-chain transaction analysis.

Identifies known patterns in transaction sequences such as
sandwich attacks, front-running, wallet drains, and token
deployment patterns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Known transaction pattern types."""

    SANDWICH_ATTACK = "sandwich_attack"
    FRONT_RUN = "front_run"
    WALLET_DRAIN = "wallet_drain"
    TOKEN_SNIPE = "token_snipe"
    LP_PULL = "lp_pull"
    AIRDROP_FARM = "airdrop_farm"
    CONTRACT_DEPLOY_AND_INTERACT = "contract_deploy_and_interact"


@dataclass
class PatternMatch:
    """A detected pattern with supporting evidence."""

    pattern_type: PatternType
    confidence: float  # 0.0 to 1.0
    addresses: list[str]
    description: str
    transactions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern_type.value,
            "confidence": self.confidence,
            "addresses": self.addresses,
            "description": self.description,
            "transactions": self.transactions,
            "metadata": self.metadata,
        }


class PatternMatcher:
    """
    Identifies known on-chain patterns from transaction sequences.

    The matcher maintains a sliding window of recent transactions
    and applies pattern-specific rules to detect suspicious sequences.

    Args:
        window_size: Number of recent transactions to keep in the buffer.
        min_confidence: Minimum confidence threshold for reporting matches.
    """

    def __init__(
        self,
        window_size: int = 5000,
        min_confidence: float = 0.5,
    ) -> None:
        self.window_size = window_size
        self.min_confidence = min_confidence
        self._buffer: list[dict[str, Any]] = []

    def ingest(self, transaction: dict[str, Any]) -> list[PatternMatch]:
        """
        Add a transaction to the buffer and check for patterns.

        Returns any newly detected patterns.
        """
        self._buffer.append(transaction)
        if len(self._buffer) > self.window_size:
            self._buffer = self._buffer[-self.window_size:]

        matches: list[PatternMatch] = []

        # Run pattern detectors
        for detector in [
            self._detect_sandwich,
            self._detect_wallet_drain,
            self._detect_lp_pull,
            self._detect_deploy_and_interact,
        ]:
            match = detector(transaction)
            if match and match.confidence >= self.min_confidence:
                matches.append(match)

        return matches

    def scan_buffer(self) -> list[PatternMatch]:
        """Scan the entire buffer for patterns (batch mode)."""
        all_matches: list[PatternMatch] = []

        for detector in [
            self._scan_sandwich_attacks,
            self._scan_airdrop_farming,
        ]:
            matches = detector()
            all_matches.extend(
                m for m in matches if m.confidence >= self.min_confidence
            )

        return all_matches

    def _detect_sandwich(self, tx: dict[str, Any]) -> Optional[PatternMatch]:
        """
        Detect sandwich attacks in real-time.

        A sandwich attack consists of:
        1. Attacker buys token (front-run)
        2. Victim's swap executes at worse price
        3. Attacker sells token (back-run)

        All three transactions occur in the same block.
        """
        if len(self._buffer) < 3:
            return None

        block = tx.get("blockNumber")
        if block is None:
            return None

        # Get all transactions in the same block
        same_block = [
            t for t in self._buffer[-50:]
            if t.get("blockNumber") == block
        ]

        if len(same_block) < 3:
            return None

        # Look for buy-swap-sell pattern with same attacker
        for i in range(len(same_block) - 2):
            tx1, tx2, tx3 = same_block[i], same_block[i + 1], same_block[i + 2]

            from1 = tx1.get("from", "").lower()
            from3 = tx3.get("from", "").lower()
            from2 = tx2.get("from", "").lower()

            # Same sender on outside, different in middle
            if from1 == from3 and from1 != from2:
                to = tx1.get("to", "").lower()
                # All going to the same contract (DEX router)
                if to == tx2.get("to", "").lower() == tx3.get("to", "").lower():
                    return PatternMatch(
                        pattern_type=PatternType.SANDWICH_ATTACK,
                        confidence=0.75,
                        addresses=[from1, from2],
                        description=(
                            f"Potential sandwich attack: {from1[:10]}... "
                            f"sandwiched {from2[:10]}... in block {block}"
                        ),
                        transactions=[
                            tx1.get("hash", ""),
                            tx2.get("hash", ""),
                            tx3.get("hash", ""),
                        ],
                        metadata={
                            "block": block,
                            "attacker": from1,
                            "victim": from2,
                            "contract": to,
                        },
                    )
        return None

    def _detect_wallet_drain(self, tx: dict[str, Any]) -> Optional[PatternMatch]:
        """Detect a wallet being drained (many outgoing txs, no incoming)."""
        from_addr = tx.get("from", "").lower()
        if not from_addr:
            return None

        # Check recent history for this address
        recent = [
            t for t in self._buffer[-200:]
            if t.get("from", "").lower() == from_addr
            or t.get("to", "").lower() == from_addr
        ]

        outgoing = [
            t for t in recent if t.get("from", "").lower() == from_addr
        ]
        incoming = [
            t for t in recent if t.get("to", "").lower() == from_addr
        ]

        # Many outgoing, few incoming in a short window
        if len(outgoing) >= 5 and len(incoming) == 0:
            total_out = sum(int(t.get("value", 0)) for t in outgoing)
            return PatternMatch(
                pattern_type=PatternType.WALLET_DRAIN,
                confidence=min(0.9, len(outgoing) * 0.12),
                addresses=[from_addr],
                description=(
                    f"Possible wallet drain: {len(outgoing)} outgoing "
                    f"transactions, 0 incoming"
                ),
                transactions=[t.get("hash", "") for t in outgoing[:5]],
                metadata={
                    "outgoing_count": len(outgoing),
                    "total_value_wei": total_out,
                },
            )
        return None

    def _detect_lp_pull(self, tx: dict[str, Any]) -> Optional[PatternMatch]:
        """Detect liquidity removal patterns."""
        input_data = tx.get("input", "0x")
        method = input_data[:10] if len(input_data) >= 10 else ""

        # removeLiquidity / removeLiquidityETH selectors
        lp_remove_selectors = {"0xbaa2abde", "0x02751cec", "0xaf2979eb", "0xded9382a"}

        if method in lp_remove_selectors:
            from_addr = tx.get("from", "").lower()
            value = int(tx.get("value", 0))

            return PatternMatch(
                pattern_type=PatternType.LP_PULL,
                confidence=0.6,
                addresses=[from_addr],
                description=(
                    f"Liquidity removal detected from {from_addr[:10]}..."
                ),
                transactions=[tx.get("hash", "")],
                metadata={
                    "method_selector": method,
                    "contract": tx.get("to", "").lower(),
                },
            )
        return None

    def _detect_deploy_and_interact(
        self, tx: dict[str, Any]
    ) -> Optional[PatternMatch]:
        """Detect contract deployment followed by immediate interaction."""
        # Contract creation = to is None/empty
        if tx.get("to"):
            return None

        from_addr = tx.get("from", "").lower()
        block = tx.get("blockNumber", 0)

        # Check if deployer immediately interacted with another contract
        # within the last few blocks
        deployer_recent = [
            t for t in self._buffer[-20:]
            if t.get("from", "").lower() == from_addr
            and t.get("to")
            and t.get("blockNumber", 0) >= block - 2
        ]

        if len(deployer_recent) >= 2:
            return PatternMatch(
                pattern_type=PatternType.CONTRACT_DEPLOY_AND_INTERACT,
                confidence=0.55,
                addresses=[from_addr],
                description=(
                    f"Contract deployed by {from_addr[:10]}... with "
                    f"immediate interactions"
                ),
                transactions=[t.get("hash", "") for t in deployer_recent],
                metadata={
                    "deployer": from_addr,
                    "interaction_count": len(deployer_recent),
                },
            )
        return None

    def _scan_sandwich_attacks(self) -> list[PatternMatch]:
        """Batch scan the buffer for sandwich attack patterns."""
        matches: list[PatternMatch] = []
        seen_blocks: set[int] = set()

        for tx in self._buffer:
            block = tx.get("blockNumber")
            if block and block not in seen_blocks:
                seen_blocks.add(block)
                match = self._detect_sandwich(tx)
                if match:
                    matches.append(match)

        return matches

    def _scan_airdrop_farming(self) -> list[PatternMatch]:
        """Scan for airdrop farming patterns (many wallets, similar behavior)."""
        from collections import Counter

        # Group by target contract
        targets: dict[str, list[str]] = {}
        for tx in self._buffer:
            to = tx.get("to", "").lower()
            from_addr = tx.get("from", "").lower()
            if to and from_addr:
                if to not in targets:
                    targets[to] = []
                targets[to].append(from_addr)

        matches: list[PatternMatch] = []

        for target, senders in targets.items():
            unique = set(senders)
            if len(unique) >= 10:
                # Check if senders have similar value patterns
                values = Counter()
                for tx in self._buffer:
                    if tx.get("to", "").lower() == target:
                        v = int(tx.get("value", 0))
                        values[v] += 1

                # If most transactions use the same value, likely farming
                if values and values.most_common(1)[0][1] >= len(unique) * 0.5:
                    matches.append(
                        PatternMatch(
                            pattern_type=PatternType.AIRDROP_FARM,
                            confidence=0.65,
                            addresses=list(unique)[:20],
                            description=(
                                f"Potential airdrop farming: {len(unique)} "
                                f"wallets targeting {target[:10]}..."
                            ),
                            metadata={
                                "target_contract": target,
                                "unique_senders": len(unique),
                                "most_common_value": values.most_common(1)[0][0],
                            },
                        )
                    )

        return matches

    def clear(self) -> None:
        """Clear the transaction buffer."""
        self._buffer.clear()
