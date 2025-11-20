"""
Pydantic schemas for neural data structures.

This module defines schemas for:
1. Individual cycle data from ESP32
2. Complete messages with multiple cycles
3. Redis queue message format
4. Session information and summary
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional


class CycleData(BaseModel):
    """Schema for a single cycle of neural data.
    
    Attributes:
        v: Voltage reading in volts (float, can be negative)
        t: Time measurement in microseconds (float, optional)
        pred: List of predicted spike times in microseconds (List[float])
        gt: List of ground truth spike times in microseconds (List[float])
    """
    v: float = Field(..., description="Voltage reading in volts (can be negative)", le=3.0)
    t: Optional[float] = Field(None, description="Time measurement in microseconds", ge=0.0)
    pred: List[float] = Field(default_factory=list, description="Predicted spike times (μs)")
    gt: List[float] = Field(default_factory=list, description="Ground truth spike times (μs)")

    class Config:
        json_schema_extra = {
            "example": {
                "v": 1.2,
                "t": 5000.5,
                "pred": [1000.2, 2000.1],
                "gt": [1000.0, 2000.0]
            }
        }


class Message(BaseModel):
    """Schema for a complete message from ESP32.
    
    Attributes:
        cycles: List of cycle data points
    """
    cycles: List[CycleData] = Field(..., description="List of cycles in this message")

    class Config:
        json_schema_extra = {
            "example": {
                "cycles": [
                    {
                        "v": 1.2,
                        "t": 5000.5,
                        "pred": [1000.2],
                        "gt": [1000.0]
                    }
                ]
            }
        }


class RedisMessageData(BaseModel):
    """Schema for data stored in Redis queue.
    
    This represents the complete message including timing information
    as it is published to the Redis queue.
    
    Attributes:
        message_id: Sequential message identifier from ESP32
        received_at: ISO format timestamp when message was received
        data: The actual message containing cycle data
    """
    message_id: int = Field(..., description="Sequential message ID", ge=1)
    received_at: datetime = Field(..., description="When message was received (ISO format)")
    data: Message = Field(..., description="The message data containing cycles")

    class Config:
        json_schema_extra = {
            "example": {
                "message_id": 1,
                "received_at": "2025-11-21T12:34:56.789123",
                "data": {
                    "cycles": [
                        {
                            "v": 1.2,
                            "t": 5000.5,
                            "pred": [1000.2],
                            "gt": [1000.0]
                        }
                    ]
                }
            }
        }


class SessionInfo(BaseModel):
    """Schema for session metadata.
    
    Attributes:
        client_ip: IP address of ESP32 client
        client_port: Port number of ESP32 connection
        start_time: ISO format timestamp of session start
        end_time: ISO format timestamp of session end (optional)
        total_messages: Total messages received in session (optional)
        total_cycles: Total cycles processed in session (optional)
        duration_seconds: Session duration in seconds (optional)
    """
    client_ip: str = Field(..., description="ESP32 client IP address")
    client_port: int = Field(..., description="ESP32 client port number", ge=0, le=65535)
    start_time: datetime = Field(..., description="Session start time (ISO format)")
    end_time: Optional[datetime] = Field(None, description="Session end time (ISO format)")
    total_messages: Optional[int] = Field(None, description="Total messages received", ge=0)
    total_cycles: Optional[int] = Field(None, description="Total cycles processed", ge=0)
    duration_seconds: Optional[float] = Field(None, description="Session duration in seconds", ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "client_ip": "192.168.1.100",
                "client_port": 54321,
                "start_time": "2025-11-21T12:34:00",
                "end_time": "2025-11-21T12:35:30",
                "total_messages": 100,
                "total_cycles": 500,
                "duration_seconds": 90.0
            }
        }


class SessionData(BaseModel):
    """Schema for complete session data saved to file.
    
    This is the top-level structure saved to the JSON file when
    a session is complete.
    
    Attributes:
        session_info: Metadata about the session
        messages: List of all messages received during session
    """
    session_info: SessionInfo = Field(..., description="Session metadata")
    messages: List[RedisMessageData] = Field(..., description="All messages from session")

    class Config:
        json_schema_extra = {
            "example": {
                "session_info": {
                    "client_ip": "192.168.1.100",
                    "client_port": 54321,
                    "start_time": "2025-11-21T12:34:00",
                    "end_time": "2025-11-21T12:35:30",
                    "total_messages": 1,
                    "total_cycles": 1,
                    "duration_seconds": 90.0
                },
                "messages": [
                    {
                        "message_id": 1,
                        "received_at": "2025-11-21T12:34:05.123456",
                        "data": {
                            "cycles": [
                                {
                                    "v": 1.2,
                                    "t": 5000.5,
                                    "pred": [1000.2],
                                    "gt": [1000.0]
                                }
                            ]
                        }
                    }
                ]
            }
        }

