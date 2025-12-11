import logging
import httpx
import asyncio
from app.models import User
from app.auth import verify_auth
from app.config import NOMINATIM_URL, PHOTON_URL, NOMINATIM_REVERSE_URL
from fastapi import APIRouter,Depends, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/api/search")
async def nominatim_search(
    q: str = Query(..., min_length=2),
    user: User = Depends(verify_auth),
    limit: int = Query(10, ge=1, le=50),
    ):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                NOMINATIM_URL,
                params={
                    "q": q,
                    "format": "json",
                    "limit": limit,
                    "addressdetails": 1
                },
                headers={"User-Agent": "medocr-search"}
            )

            response.raise_for_status()
            data = response.json()
            return {
                "status": True,
                "msg": "Search successful",
                "count": len(data),
                "results": data
            }

    except httpx.HTTPStatusError as e:
        logger.error(f"Nominatim HTTP error: {e.response.text}")
        raise HTTPException(status_code=502, detail="Nominatim responded with an error")

    except httpx.RequestError as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not connect to Nominatim")

    except Exception as e:
        logger.exception("Unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/api/photon-search")
async def photon_search(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    user = Depends(verify_auth)
):
    params = {"q": q, "limit": limit}
    headers = {"User-Agent": "medocr-photon"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(PHOTON_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            return {
                "status": True,
                "count": len(data.get("features", [])),
                "results": data.get("features", [])
            }
        except httpx.HTTPStatusError:
            raise HTTPException(502, "Photon search failed")
        except httpx.RequestError:
            raise HTTPException(500, "Could not connect to Photon")

@router.get("/api/unified-search")
async def unified_search(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user = Depends(verify_auth),
):
    ua_photon = {"User-Agent": "medocr-photon"}
    ua_nominatim = {"User-Agent": "medocr-search"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        fetch_count = limit + offset
        try:
            response = await client.get(
                PHOTON_URL,
                params={"q": q, "limit": fetch_count},
                headers=ua_photon
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Photon [{e.response.status_code}]: {e.response.text}")
            raise HTTPException(502, "Photon search failed")
        except httpx.RequestError as e:
            logger.error(f"Photon request error: {e}")
            raise HTTPException(502, "Could not connect to Photon")

        all_features = response.json().get("features", [])
        logger.info(f"Photon returned {len(all_features)} raw features")

        page = all_features[offset : offset + limit]
        logger.info(f"Sliced to {len(page)} features (offset={offset}, limit={limit})")

        async def fetch_address(feat):
            lon, lat = feat["geometry"]["coordinates"]
            try:
                r = await client.get(
                    NOMINATIM_REVERSE_URL,
                    params={"lon": lon, "lat": lat, "format": "json", "addressdetails": 1},
                    headers=ua_nominatim
                )
                r.raise_for_status()
                return r.json().get("address", {})
            except httpx.HTTPStatusError:
                logger.warning(f"Nominatim HTTP error for {lat},{lon}")
            except httpx.RequestError:
                logger.warning(f"Nominatim request error for {lat},{lon}")
            return {}

        addresses = await asyncio.gather(
            *[fetch_address(f) for f in page],
            return_exceptions=False
        )

        combined = []
        for feat, addr in zip(page, addresses):
            combined.append({
                "type": feat.get("type"),
                "geometry": feat.get("geometry"),
                "properties": feat.get("properties"),
                "address": addr
            })

        logger.info(f"Returning {len(combined)} combined results")

        return {
            "status": True,
            "count": len(combined),
            "results": combined
        }

@router.get("/api/geoencode")
async def geo_encode(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(verify_auth)
):
    params = {
        "q": q,
        "format": "json",
        "limit": limit,
        "addressdetails": 1
    }
    headers = {"User-Agent": "medocr-geoencode"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(NOMINATIM_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            return {
                "status": True,
                "count": len(data),
                "results": data
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"Geoencode HTTP error: {e.response.text}")
            raise HTTPException(status_code=502, detail="Geoencode failed")
        except httpx.RequestError as e:
            logger.error(f"Geoencode request error: {e}")
            raise HTTPException(status_code=500, detail="Could not connect to Nominatim")
        except Exception as e:
            logger.exception("Unexpected error in geoencode")
            raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/api/reverse-geoencode")
async def reverse_geoencode(
    lat: float = Query(...),
    lon: float = Query(...),
    user: User = Depends(verify_auth)
):
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "addressdetails": 1
    }
    headers = {"User-Agent": "medocr-reverse-geoencode"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(NOMINATIM_REVERSE_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            return {
                "status": True,
                "result": data
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"Reverse geoencode HTTP error: {e.response.text}")
            raise HTTPException(status_code=502, detail="Reverse geoencode failed")
        except httpx.RequestError as e:
            logger.error(f"Reverse geoencode request error: {e}")
            raise HTTPException(status_code=500, detail="Could not connect to Nominatim")
        except Exception as e:
            logger.exception("Unexpected error in reverse geoencode")
            raise HTTPException(status_code=500, detail="Internal server error")
