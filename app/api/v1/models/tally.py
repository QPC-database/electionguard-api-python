from typing import Any, Dict, List
import electionguard.election
from electionguard.serializable import read_json_object
import electionguard.tally
from electionguard.manifest import InternalManifest

from .ballot import SubmittedBallot
from .base import BaseRequest
from .election import ElectionManifest, CiphertextElectionContext
from .guardian import Guardian

__all__ = [
    "PublishedCiphertextTally",
    "TallyDecryptionShare",
    "StartTallyRequest",
    "AppendTallyRequest",
    "DecryptTallyRequest",
    "DecryptTallyShareRequest",
    "convert_tally",
]

PublishedCiphertextTally = Any
TallyDecryptionShare = Any


class StartTallyRequest(BaseRequest):
    ballots: List[SubmittedBallot]
    description: ElectionManifest
    context: CiphertextElectionContext


class AppendTallyRequest(StartTallyRequest):
    encrypted_tally: PublishedCiphertextTally


class DecryptTallyRequest(BaseRequest):
    encrypted_tally: PublishedCiphertextTally
    shares: Dict[str, TallyDecryptionShare]
    description: ElectionManifest
    context: CiphertextElectionContext


class DecryptTallyShareRequest(BaseRequest):
    encrypted_tally: PublishedCiphertextTally
    guardian: Guardian
    description: ElectionManifest
    context: CiphertextElectionContext


def convert_tally(
    encrypted_tally: PublishedCiphertextTally,
    description: InternalManifest,
    context: electionguard.election.CiphertextElectionContext,
) -> electionguard.tally.CiphertextTally:
    """
    Convert to an SDK CiphertextTally model
    """

    published_tally = read_json_object(
        encrypted_tally, electionguard.tally.PublishedCiphertextTally
    )
    tally = electionguard.tally.CiphertextTally(
        published_tally.object_id, description, context
    )

    return tally
