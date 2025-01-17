from typing import Any, List, Optional
from uuid import uuid4
import sys


from fastapi import APIRouter, Body, HTTPException, status

from electionguard.election import (
    ElectionConstants,
    make_ciphertext_election_context,
)
from electionguard.group import ElementModP, ElementModQ
from electionguard.election import CiphertextElectionContext
from electionguard.manifest import Manifest
from electionguard.serializable import read_json_object, write_json_object

from .manifest import get_manifest
from ....core.client import get_client_id
from ....core.repository import get_repository, DataCollection
from ..models import (
    BaseResponse,
    Election,
    ElectionState,
    ElectionQueryRequest,
    ElectionQueryResponse,
    MakeElectionContextRequest,
    MakeElectionContextResponse,
    SubmitElectionRequest,
    SubmitElectionResponse,
)
from ..tags import ELECTION

router = APIRouter()


@router.get("/constants", tags=[ELECTION])
def get_election_constants() -> Any:
    """
    Return the constants defined for an election
    """
    constants = ElectionConstants()
    return constants.to_json_object()


@router.get("", response_model=ElectionQueryResponse, tags=[ELECTION])
def get_election(election_id: str) -> ElectionQueryResponse:
    """Get an election by election id"""
    try:
        with get_repository(get_client_id(), DataCollection.ELECTION) as repository:
            query_result = repository.get({"election_id": election_id})
            if not query_result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Could not find election {election_id}",
                )
            election = Election(
                election_id=query_result["election_id"],
                state=query_result["state"],
                context=query_result["context"],
                manifest=query_result["manifest"],
            )

            return ElectionQueryResponse(
                elections=[election],
            )
    except Exception as error:
        print(sys.exc_info())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="get election failed",
        ) from error


@router.put("", response_model=SubmitElectionResponse, tags=[ELECTION])
def create_election(
    election_id: Optional[str], request: SubmitElectionRequest = Body(...)
) -> SubmitElectionResponse:
    """
    Submit an election.

    Method expects a manifest to already be submitted or to optionally be provided
    as part of the request body.  If a manifest is provided as part of the body
    then it will override any cached value, however the hash must match the hash
    contained in the CiphertextelectionContext
    """
    if not election_id:
        election_id = request.election_id

    if not election_id:
        election_id = str(uuid4())

    context = CiphertextElectionContext.from_json_object(request.context)

    if request.manifest:
        manifest = Manifest.from_json_object(request.manifest)
    else:
        manifest_query = get_manifest(context.manifest_hash)
        manifest = Manifest.from_json_object(manifest_query.manifests[0])

    # validate that the context was built against the correct manifest
    if context.manifest_hash != manifest.crypto_hash():
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="manifest hash does not match provided context hash",
        )

    election = Election(
        election_id=election_id,
        state=ElectionState.CREATED,
        context=context.to_json_object(),
        manifest=manifest.to_json_object(),
    )

    try:
        with get_repository(get_client_id(), DataCollection.ELECTION) as repository:
            _ = repository.set(write_json_object(election.dict()))
            return SubmitElectionResponse(election_id=election_id)
    except Exception as error:
        print(sys.exc_info())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Submit election failed",
        ) from error


@router.get("/find", response_model=ElectionQueryResponse, tags=[ELECTION])
def find_elections(
    skip: int = 0, limit: int = 100, request: ElectionQueryRequest = Body(...)
) -> ElectionQueryResponse:
    """
    Find elections.

    Search the repository for elections that match the filter criteria specified in the request body.
    If no filter criteria is specified the API will iterate all available data.
    """
    try:

        filter = write_json_object(request.filter) if request.filter else {}
        with get_repository(get_client_id(), DataCollection.ELECTION) as repository:
            cursor = repository.find(filter, skip, limit)
            elections: List[Election] = []
            for item in cursor:
                elections.append(
                    Election(
                        election_id=item["election_id"],
                        state=item["state"],
                        context=item["context"],
                        manifest=item["manifest"],
                    )
                )
            return ElectionQueryResponse(elections=elections)
    except Exception as error:
        print(sys.exc_info())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="find elections failed",
        ) from error


@router.post("/open", response_model=BaseResponse, tags=[ELECTION])
def open_election(election_id: str) -> BaseResponse:
    """
    Open an election.
    """
    return _update_election_state(election_id, ElectionState.OPEN)


@router.post("/close", response_model=BaseResponse, tags=[ELECTION])
def close_election(election_id: str) -> BaseResponse:
    """
    Close an election.
    """
    return _update_election_state(election_id, ElectionState.CLOSED)


@router.post("/publish", response_model=BaseResponse, tags=[ELECTION])
def publish_election(election_id: str) -> BaseResponse:
    """
    Publish an election
    """
    return _update_election_state(election_id, ElectionState.PUBLISHED)


@router.post("/context", response_model=MakeElectionContextResponse, tags=[ELECTION])
def build_election_context(
    manifest_hash: Optional[str] = None, request: MakeElectionContextRequest = Body(...)
) -> MakeElectionContextResponse:
    """
    Build a CiphertextElectionContext for a given election and returns it.

    Caller must specify the manifest to build against
    by either providing the manifest hash in the query parameter or request body;
    or by providing the manifest directly in the request body
    """
    if not manifest_hash:
        manifest_hash = request.manifest_hash

    if manifest_hash:
        print(manifest_hash)
        manifest_query = get_manifest(manifest_hash)
        manifest = Manifest.from_json_object(manifest_query.manifests[0])
    else:
        manifest = Manifest.from_json_object(request.manifest)

    elgamal_public_key: ElementModP = read_json_object(
        request.elgamal_public_key, ElementModP
    )
    commitment_hash = read_json_object(request.commitment_hash, ElementModQ)
    number_of_guardians = request.number_of_guardians
    quorum = request.quorum

    context = make_ciphertext_election_context(
        number_of_guardians,
        quorum,
        elgamal_public_key,
        commitment_hash,
        manifest.crypto_hash(),
    )

    return MakeElectionContextResponse(context=context.to_json_object())


def _update_election_state(election_id: str, new_state: ElectionState) -> BaseResponse:
    try:
        with get_repository(get_client_id(), DataCollection.ELECTION) as repository:
            query_result = repository.get({"election_id": election_id})
            if not query_result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Could not find election {election_id}",
                )
            election = Election(
                election_id=query_result["election_id"],
                state=new_state,
                context=query_result["context"],
                manifest=query_result["manifest"],
            )

            repository.update({"election_id": election_id}, election.dict())
            return BaseResponse()
    except Exception as error:
        print(sys.exc_info())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="update election failed",
        ) from error
