from typing import List

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect
)

from fastapi.middleware.cors import CORSMiddleware
from .database import MongoSession, func, get_db, init_db

from .models import (
    Bus,
    Incident as IncidentModel,
    Detection
)

from .schemas import (
    BusCreate,
    BusResponse,
    IncidentCreate,
    IncidentUpdate,
    IncidentResponse,
    DetectionCreate,
    DetectionResponse,
    DashboardStats
)

import cv2
import numpy as np

from fastapi import UploadFile, File
from ai.ai_detector import AIDetector
# ============================================================
# M6 - REALTIME IMPORTS
# ============================================================

from .realtime.connection_manager import manager
from .realtime.event_manager import create_incident_event
from .realtime.incident_adapter import m4_to_m3_incident


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="AI-Powered Mobile Urban Sensing API",
    description="Backend API for AI-powered public bus urban intelligence platform",
    version="1.0.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)



mobile_detector = AIDetector()


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup():
    init_db()


@app.post("/api/mobile/test")
async def mobile_test(data: dict):
    print("[MOBILE] Received:", data)

    return {
        "message": "Mobile connected successfully",
        "received": data
    }

@app.post("/api/mobile/gps")
async def receive_mobile_gps(data: dict):

    global latest_mobile_gps

    latest_mobile_gps = {
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "accuracy": data.get("accuracy"),
        "speed": data.get("speed"),
        "heading": data.get("heading")
    }

    print(
        f"[MOBILE GPS] "
        f"Lat: {latest_mobile_gps['latitude']} | "
        f"Lon: {latest_mobile_gps['longitude']} | "
        f"Accuracy: {latest_mobile_gps['accuracy']}m | "
        f"Speed: {latest_mobile_gps['speed']} | "
        f"Heading: {latest_mobile_gps['heading']}"
    )

    return {
        "message": "GPS stored successfully",
        "received": latest_mobile_gps
    }


def calculate_mobile_severity(confidence: float):

    if confidence >= 0.85:
        return "critical"

    elif confidence >= 0.70:
        return "high"

    elif confidence >= 0.50:
        return "medium"

    return "low"

@app.post("/api/mobile/detect")
async def detect_mobile_frame(
    file: UploadFile = File(...),
    db: MongoSession = Depends(get_db)
):

    global latest_mobile_gps

    try:

        # ========================================================
        # 1. CHECK GPS
        # ========================================================

        if latest_mobile_gps is None:

            return {
                "success": False,
                "message": "GPS data not available yet"
            }

        latitude = latest_mobile_gps.get("latitude")
        longitude = latest_mobile_gps.get("longitude")

        if latitude is None or longitude is None:

            return {
                "success": False,
                "message": "Invalid GPS coordinates"
            }

        # ========================================================
        # 2. READ IMAGE
        # ========================================================

        image_bytes = await file.read()

        image_array = np.frombuffer(
            image_bytes,
            np.uint8
        )

        frame = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        if frame is None:

            return {
                "success": False,
                "message": "Invalid image"
            }

        # ========================================================
        # 3. RUN AI
        # ========================================================

        detections = mobile_detector.detect(frame)

        print(
            f"[MOBILE AI] "
            f"Detections: {len(detections)}"
        )

        # ========================================================
        # 4. STORE DETECTIONS + CREATE INCIDENTS
        # ========================================================

        created_incidents = []

        for detection in detections:

            # ----------------------------------------------------
            # Get class/type
            # ----------------------------------------------------

            object_type = (
                detection.get("class")
                or detection.get("type")
                or "unknown"
            )

            confidence = float(
                detection.get("confidence", 0)
            )

            print(
                f"[AI DETECTION] "
                f"{object_type} | "
                f"Confidence: {confidence:.2f}"
            )

            # ----------------------------------------------------
            # Only create incident for potholes
            # ----------------------------------------------------

            if object_type.lower() != "pothole":

                continue

            # ----------------------------------------------------
            # Severity
            # ----------------------------------------------------

            severity = calculate_mobile_severity(
                confidence
            )

            # ----------------------------------------------------
            # Priority score
            # ----------------------------------------------------

            priority_score = round(
                confidence * 100,
                2
            )

            # ====================================================
            # SAVE DETECTION
            # ====================================================

            new_detection = Detection(
                object_type=object_type,
                confidence=confidence,
                latitude=latitude,
                longitude=longitude,
                bus_number="MOBILE-01"
            )

            db.add(new_detection)

            # ====================================================
            # SAVE INCIDENT
            # ====================================================

            new_incident = IncidentModel(
                incident_type="pothole",

                description=(
                    "Pothole detected by mobile "
                    "urban sensing camera"
                ),

                latitude=latitude,
                longitude=longitude,

                confidence=confidence,

                severity=severity,

                priority_score=priority_score,

                bus_number="MOBILE-01",

                status="pending",

                verified=False
            )

            db.add(new_incident)

            # ----------------------------------------------------
            # Keep object for response
            # ----------------------------------------------------

            created_incidents.append(
                new_incident
            )

        # ========================================================
        # 5. COMMIT DATABASE
        # ========================================================

        db.commit()

        # Refresh database objects
        for incident in created_incidents:

            db.refresh(incident)

        # ========================================================
        # 6. WEBSOCKET BROADCAST
        # ========================================================

        for incident in created_incidents:

            event = create_incident_event(
                incident
            )

            await manager.broadcast(
                event
            )

            print(
                f"[M6] Incident broadcast | "
                f"ID: {incident.id}"
            )

        # ========================================================
        # 7. RESPONSE
        # ========================================================

        return {

            "success": True,

            "detections": detections,

            "incidents_created": len(
                created_incidents
            ),

            "incidents": [
                {
                    "id": incident.id,
                    "type": incident.incident_type,
                    "latitude": incident.latitude,
                    "longitude": incident.longitude,
                    "confidence": incident.confidence,
                    "severity": incident.severity,
                    "priority_score": incident.priority_score
                }

                for incident in created_incidents
            ]
        }

    except Exception as e:

        db.rollback()

        print(
            f"[MOBILE AI ERROR] {e}"
        )

        return {
            "success": False,
            "message": str(e)
        }
# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():
    return {
        "status": "online",
        "project": "AI-Powered Mobile Urban Sensing Using Public Buses",
        "version": "1.0.0"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "database": "connected"
    }


# ============================================================
# M6 - WEBSOCKET
# ============================================================

@app.websocket("/ws/incidents")
async def incident_websocket(websocket: WebSocket):

    await manager.connect(websocket)

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

    except Exception as e:
        print(f"[M6] WebSocket closed: {e}")

    finally:
        manager.disconnect(websocket)
# ============================================================
# M4 → M3 → M6
# RECEIVE INCIDENT FROM M4
# ============================================================

@app.post("/api/incidents/from-m4")
async def receive_m4_incident(
    incident_data: dict,
    db: MongoSession = Depends(get_db)
):
    """
    Receive a complete incident generated by M4.

    Flow:

    M4
      ↓
    FastAPI
      ↓
    Convert M4 format → M3 database format
      ↓
    Save to database
      ↓
    Create M6 realtime event
      ↓
    Broadcast through WebSocket
      ↓
    React Dashboard
    """

    try:

        # ----------------------------------------------------
        # Import M4 Incident model
        # ----------------------------------------------------

        from intelligence.incident import Incident

        # ----------------------------------------------------
        # Reconstruct M4 Incident object
        # ----------------------------------------------------

        incident = Incident(**incident_data)

        # ----------------------------------------------------
        # Convert M4 format → M3 format
        # ----------------------------------------------------

        m3_data = m4_to_m3_incident(incident)

        # ----------------------------------------------------
        # Create database record
        # ----------------------------------------------------

        new_incident = IncidentModel(**m3_data)

        db.add(new_incident)

        db.commit()

        db.refresh(new_incident)

        # ----------------------------------------------------
        # Create M6 realtime event
        # ----------------------------------------------------

        event = create_incident_event(new_incident)

        # ----------------------------------------------------
        # Broadcast to all connected dashboards
        # ----------------------------------------------------

        await manager.broadcast(event)

        # ----------------------------------------------------
        # Response
        # ----------------------------------------------------

        return {
            "message": "M4 incident received successfully",
            "incident_id": incident.incident_id,
            "database_id": new_incident.id,
            "realtime": True
        }

    except Exception as e:

        # Rollback database if something fails
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to process M4 incident: {str(e)}"
        )


# ============================================================
# BUS APIs
# ============================================================

@app.post(
    "/api/buses",
    response_model=BusResponse
)
def create_bus(
    bus: BusCreate,
    db: MongoSession = Depends(get_db)
):

    existing_bus = (
        db.query(Bus)
        .filter(Bus.bus_number == bus.bus_number)
        .first()
    )

    if existing_bus:

        raise HTTPException(
            status_code=400,
            detail="Bus number already exists"
        )

    new_bus = Bus(
        **bus.model_dump()
    )

    db.add(new_bus)

    db.commit()

    db.refresh(new_bus)

    return new_bus


# ============================================================

@app.get(
    "/api/buses",
    response_model=List[BusResponse]
)
def get_buses(
    db: MongoSession = Depends(get_db)
):

    return (
        db.query(Bus)
        .order_by(Bus.id.desc())
        .all()
    )


# ============================================================

@app.get(
    "/api/buses/{bus_id}",
    response_model=BusResponse
)
def get_bus(
    bus_id: int,
    db: MongoSession = Depends(get_db)
):

    bus = (
        db.query(Bus)
        .filter(Bus.id == bus_id)
        .first()
    )

    if not bus:

        raise HTTPException(
            status_code=404,
            detail="Bus not found"
        )

    return bus


# ============================================================

@app.put(
    "/api/buses/{bus_id}",
    response_model=BusResponse
)
def update_bus(
    bus_id: int,
    bus_data: BusCreate,
    db: MongoSession = Depends(get_db)
):

    bus = (
        db.query(Bus)
        .filter(Bus.id == bus_id)
        .first()
    )

    if not bus:

        raise HTTPException(
            status_code=404,
            detail="Bus not found"
        )

    for key, value in bus_data.model_dump().items():

        setattr(
            bus,
            key,
            value
        )

    db.commit()

    db.refresh(bus)

    return bus


# ============================================================

@app.delete("/api/buses/{bus_id}")
def delete_bus(
    bus_id: int,
    db: MongoSession = Depends(get_db)
):

    bus = (
        db.query(Bus)
        .filter(Bus.id == bus_id)
        .first()
    )

    if not bus:

        raise HTTPException(
            status_code=404,
            detail="Bus not found"
        )

    db.delete(bus)

    db.commit()

    return {
        "message": "Bus deleted successfully",
        "bus_id": bus_id
    }


# ============================================================
# INCIDENT APIs
# ============================================================

@app.post(
    "/api/incidents",
    response_model=IncidentResponse
)
async def create_incident(
    incident: IncidentCreate,
    db: MongoSession = Depends(get_db)
):

    print("\n[M3] Creating incident...")

    new_incident = IncidentModel(
        **incident.model_dump()
    )

    db.add(new_incident)

    db.commit()

    db.refresh(new_incident)

    print(
        f"[M3] Incident saved | "
        f"Database ID: {new_incident.id}"
    )

    # Create realtime event
    event = create_incident_event(
        new_incident
    )

    print("[M6] Incident event created")

    # Broadcast event
    await manager.broadcast(
        event
    )

    print("[M6] Broadcast completed")

    return new_incident

# ============================================================

@app.get(
    "/api/incidents",
    response_model=List[IncidentResponse]
)
def get_incidents(
    status: str | None = None,
    severity: str | None = None,
    incident_type: str | None = None,
    db: MongoSession = Depends(get_db)
):

    query = db.query(
        IncidentModel
    )

    # Filters are case-insensitive on purpose: the detection pipeline stores
    # severities in mixed case (HIGH / MEDIUM / low) and the dashboard sends
    # canonical lowercase values, so an exact match would silently drop rows.

    if status:

        query = query.filter(
            func.lower(IncidentModel.status) == func.lower(status)
        )

    if severity:

        query = query.filter(
            func.lower(IncidentModel.severity) == func.lower(severity)
        )

    if incident_type:

        query = query.filter(
            func.lower(IncidentModel.incident_type) == func.lower(incident_type)
        )

    return (
        query
        .order_by(
            IncidentModel.id.desc()
        )
        .all()
    )


# ============================================================

@app.get(
    "/api/incidents/{incident_id}",
    response_model=IncidentResponse
)
def get_incident(
    incident_id: int,
    db: MongoSession = Depends(get_db)
):

    incident = (
        db.query(IncidentModel)
        .filter(
            IncidentModel.id == incident_id
        )
        .first()
    )

    if not incident:

        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    return incident


# ============================================================

@app.put(
    "/api/incidents/{incident_id}",
    response_model=IncidentResponse
)
def update_incident(
    incident_id: int,
    update_data: IncidentUpdate,
    db: MongoSession = Depends(get_db)
):

    incident = (
        db.query(IncidentModel)
        .filter(
            IncidentModel.id == incident_id
        )
        .first()
    )

    if not incident:

        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    update_values = update_data.model_dump(
        exclude_unset=True
    )

    for key, value in update_values.items():

        setattr(
            incident,
            key,
            value
        )

    db.commit()

    db.refresh(incident)

    return incident


# ============================================================

@app.delete(
    "/api/incidents/{incident_id}"
)
def delete_incident(
    incident_id: int,
    db: MongoSession = Depends(get_db)
):

    incident = (
        db.query(IncidentModel)
        .filter(
            IncidentModel.id == incident_id
        )
        .first()
    )

    if not incident:

        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    db.delete(incident)

    db.commit()

    return {
        "message": "Incident deleted successfully",
        "incident_id": incident_id
    }


# ============================================================
# DETECTION APIs
# ============================================================

@app.post(
    "/api/detections",
    response_model=DetectionResponse
)
def create_detection(
    detection: DetectionCreate,
    db: MongoSession = Depends(get_db)
):

    new_detection = Detection(
        **detection.model_dump()
    )

    db.add(new_detection)

    db.commit()

    db.refresh(new_detection)

    return new_detection


# ============================================================

@app.get(
    "/api/detections",
    response_model=List[DetectionResponse]
)
def get_detections(
    object_type: str | None = None,
    bus_number: str | None = None,
    db: MongoSession = Depends(get_db)
):

    query = db.query(
        Detection
    )

    if object_type:

        query = query.filter(
            Detection.object_type == object_type
        )

    if bus_number:

        query = query.filter(
            Detection.bus_number == bus_number
        )

    return (
        query
        .order_by(
            Detection.id.desc()
        )
        .all()
    )


# ============================================================

@app.get(
    "/api/detections/{detection_id}",
    response_model=DetectionResponse
)
def get_detection(
    detection_id: int,
    db: MongoSession = Depends(get_db)
):

    detection = (
        db.query(Detection)
        .filter(
            Detection.id == detection_id
        )
        .first()
    )

    if not detection:

        raise HTTPException(
            status_code=404,
            detail="Detection not found"
        )

    return detection


# ============================================================

@app.delete(
    "/api/detections/{detection_id}"
)
def delete_detection(
    detection_id: int,
    db: MongoSession = Depends(get_db)
):

    detection = (
        db.query(Detection)
        .filter(
            Detection.id == detection_id
        )
        .first()
    )

    if not detection:

        raise HTTPException(
            status_code=404,
            detail="Detection not found"
        )

    db.delete(detection)

    db.commit()

    return {
        "message": "Detection deleted successfully",
        "detection_id": detection_id
    }


# ============================================================
# DASHBOARD STATISTICS
# ============================================================

@app.get(
    "/api/dashboard/stats",
    response_model=DashboardStats
)
def dashboard_stats(
    db: MongoSession = Depends(get_db)
):

    # --------------------------------------------------------
    # BUS COUNTS
    # --------------------------------------------------------

    total_buses = (
        db.query(Bus)
        .count()
    )

    active_buses = (
        db.query(Bus)
        .filter(
            Bus.status == "active"
        )
        .count()
    )

    # --------------------------------------------------------
    # INCIDENT COUNTS
    # --------------------------------------------------------

    total_incidents = (
        db.query(IncidentModel)
        .count()
    )

    pending_incidents = (
        db.query(IncidentModel)
        .filter(
            IncidentModel.status == "pending"
        )
        .count()
    )

    critical_incidents = (
        db.query(IncidentModel)
        .filter(
            IncidentModel.severity == "critical"
        )
        .count()
    )

    # --------------------------------------------------------
    # DETECTION COUNTS
    # --------------------------------------------------------

    total_detections = (
        db.query(Detection)
        .count()
    )

    # --------------------------------------------------------
    # RETURN
    # --------------------------------------------------------

    return DashboardStats(
        total_buses=total_buses,
        active_buses=active_buses,
        total_incidents=total_incidents,
        pending_incidents=pending_incidents,
        critical_incidents=critical_incidents,
        total_detections=total_detections
    )