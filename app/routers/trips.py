from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user
from app.models.trip import Trip
from app.models.user import User
from app.schemas.trip import TripCreate, TripCreateResponse, TripPublic, TripUpdate
from app.services.audit_log import record_trip_created

router = APIRouter(tags=["Trips"])


@router.post("", response_model=TripCreateResponse)
def create_trip(
    payload: TripCreate,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Trip:
    trip = Trip(
        user_id=current_user.id,
        destination=payload.destination,
        days=payload.days,
        budget=payload.budget,
        trip_style=payload.trip_style,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    background_tasks.add_task(
        record_trip_created,
        trip_id=trip.id,
        user_id=current_user.id,
        destination=trip.destination,
    )
    return trip


@router.get("", response_model=list[TripPublic])
def list_trips(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[Trip]:
    query = select(Trip).where(Trip.user_id == current_user.id).order_by(Trip.id)
    return list(db.scalars(query))


@router.get("/{trip_id}", response_model=TripPublic)
def get_trip(
    trip_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


@router.put("/{trip_id}", response_model=TripPublic)
def update_trip(
    trip_id: int,
    payload: TripUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(trip, key, value)

    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(
    trip_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    trip = db.get(Trip, trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    db.delete(trip)
    db.commit()
    return None
