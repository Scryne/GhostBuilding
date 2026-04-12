from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_maps():
    return {"status": "ok", "data": []}
