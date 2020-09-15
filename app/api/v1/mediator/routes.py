from fastapi import APIRouter
from . import ballot
from . import election
from . import key
from . import tally

router = APIRouter()

router.include_router(election.router, prefix="/election")
router.include_router(key.router, prefix="/key")
router.include_router(ballot.router, prefix="/ballot")
router.include_router(tally.router, prefix="/tally")