import logging
from typing import List
from app.database import get_db
from app.models import User, Geofence
from app.auth import verify_auth
from app.schemas import GeofenceCreate, GeofenceOut, LocationPoint
from sqlalchemy import insert, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Polygon, Point
from fastapi import APIRouter,Depends, HTTPException, Path
logger = logging.getLogger(__name__)

router = APIRouter()

def geom_to_wkt(geom):
    if geom is None:
        return None
    return to_shape(geom).wkt

@router.get("/api/geofences/list", response_model=List[GeofenceOut])
async def list_geofences(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_auth)
):
    result = await db.execute(select(Geofence))
    items = result.scalars().all()
    return [
        {
            "id": obj.id,
            "name": obj.name,
            "geom": geom_to_wkt(obj.geom),
            "created_at": obj.created_at
        }
        for obj in items
    ]

@router.post("/api/geofences", response_model=GeofenceOut)
async def create_geofence(
    payload: GeofenceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_auth)
):
    try:
        polygon = Polygon(payload.coordinates)
        geom = from_shape(polygon, srid=4326)

        stmt = insert(Geofence).values(
            name=payload.name,
            geom=geom
        ).returning(Geofence)

        result = await db.execute(stmt)
        await db.commit()
        obj = result.scalar_one()

        return {
            "id": obj.id,
            "name": obj.name,
            "geom": geom_to_wkt(obj.geom),
            "created_at": obj.created_at
        }
    except Exception as e:
        logger.exception("Failed to create geofence: %s", e)
        raise HTTPException(500, detail="Internal server error")

@router.get("/api/geofences/{geofence_id}", response_model=GeofenceOut)
async def get_geofence(
    geofence_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_auth)
):
    result = await db.execute(select(Geofence).where(Geofence.id == geofence_id))
    geofence = result.scalar_one_or_none()
    if not geofence:
        raise HTTPException(404, detail="Geofence not found")
    return {
        "id": geofence.id,
        "name": geofence.name,
        "geom": geom_to_wkt(geofence.geom),
        "created_at": geofence.created_at
    }

@router.put("/api/geofences/{geofence_id}", response_model=GeofenceOut)
async def update_geofence(
    payload: GeofenceCreate,
    geofence_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_auth)
):
    try:
        polygon = Polygon(payload.coordinates)
        geom = from_shape(polygon, srid=4326)

        stmt = (
            update(Geofence)
            .where(Geofence.id == geofence_id)
            .values(
                name=payload.name,
                geom=geom,
            )
            .returning(Geofence)
        )
        result = await db.execute(stmt)
        await db.commit()
        updated = result.scalar_one_or_none()
        if not updated:
            raise HTTPException(404, detail="Geofence not found")
        return {
            "id": updated.id,
            "name": updated.name,
            "geom": geom_to_wkt(updated.geom),
            "created_at": updated.created_at
        }
    except Exception as e:
        logger.exception("Failed to update geofence: %s", e)
        raise HTTPException(500, detail="Internal server error")

@router.delete("/api/geofences/{geofence_id}")
async def delete_geofence(
    geofence_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_auth)
):
    try:
        stmt = delete(Geofence).where(Geofence.id == geofence_id).returning(Geofence.id)
        result = await db.execute(stmt)
        await db.commit()
        deleted = result.scalar_one_or_none()
        if not deleted:
            raise HTTPException(404, detail="Geofence not found")
        return {"detail": "Geofence deleted", "id": deleted}
    except Exception as e:
        logger.exception("Failed to delete geofence: %s", e)
        raise HTTPException(500, detail="Internal server error")

@router.post("/api/geofences/status")
async def geofence_status(
    location: LocationPoint,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_auth)
):
    try:
        point = from_shape(Point(location.lon, location.lat), srid=4326)

        stmt = select(Geofence).where(
            Geofence.geom.ST_Contains(point)
        )
        result = await db.execute(stmt)
        inside = result.scalars().all()

        return {
            "status": True,
            "inside_geofences": [
                {"id": str(zone.id), "name": zone.name}
                for zone in inside
            ]
        }
    except Exception as e:
        logger.exception("Geofence status check failed: %s", e)
        raise HTTPException(500, detail="Internal server error")
