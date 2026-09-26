from .database import Field, utc_now


class Document:
    collection = ""
    fields = ()
    id = Field("id")
    def __init__(self, **values):
        for field in self.fields: setattr(self, field, values.get(field, getattr(type(self), field).default_value()))
    @classmethod
    def from_document(cls, document):
        instance = cls(); instance.load_document(document); return instance
    def load_document(self, document):
        for field in self.fields: setattr(self, field, document.get(field, getattr(type(self), field).default_value()))
    def to_document(self): return {field: getattr(self, field) for field in self.fields}


class Bus(Document):
    collection = "buses"
    fields = ("id", "bus_number", "route", "camera_id", "status", "latitude", "longitude", "last_seen")
    bus_number, route, camera_id = Field("bus_number"), Field("route"), Field("camera_id")
    status, latitude, longitude, last_seen = Field("status", "active"), Field("latitude"), Field("longitude"), Field("last_seen", utc_now)


class Incident(Document):
    collection = "incidents"
    fields = ("id", "incident_type", "description", "latitude", "longitude", "confidence", "severity", "priority_score", "image_url", "video_url", "bus_number", "status", "verified", "detected_at")
    incident_type, description, latitude, longitude = Field("incident_type"), Field("description"), Field("latitude"), Field("longitude")
    confidence, severity, priority_score = Field("confidence", 0.0), Field("severity", "medium"), Field("priority_score", 0.0)
    image_url, video_url, bus_number = Field("image_url"), Field("video_url"), Field("bus_number")
    status, verified, detected_at = Field("status", "pending"), Field("verified", False), Field("detected_at", utc_now)


class Detection(Document):
    collection = "detections"
    fields = ("id", "object_type", "confidence", "latitude", "longitude", "bus_number", "image_url", "detected_at")
    object_type, confidence, latitude, longitude = Field("object_type"), Field("confidence", 0.0), Field("latitude"), Field("longitude")
    bus_number, image_url, detected_at = Field("bus_number"), Field("image_url"), Field("detected_at", utc_now)
