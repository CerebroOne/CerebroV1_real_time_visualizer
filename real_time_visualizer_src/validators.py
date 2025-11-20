"""
Validation utilities for neural data schemas.

This module provides helper functions for validating and working with
neural data structures using Pydantic schemas.
"""

import json
import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime

from schema import (
    CycleData,
    Message,
    RedisMessageData,
    SessionInfo,
    SessionData,
)
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class DataValidator:
    """Utility class for validating neural data structures."""

    @staticmethod
    def validate_cycle_data(data: Dict) -> Tuple[bool, Optional[CycleData], Optional[str]]:
        """
        Validate cycle data.
        
        Args:
            data: Dictionary containing cycle data
            
        Returns:
            Tuple of (is_valid, CycleData object, error message)
        """
        try:
            cycle = CycleData(**data)
            return True, cycle, None
        except ValidationError as e:
            error_msg = f"Cycle validation failed: {e}"
            logger.error(error_msg)
            return False, None, error_msg

    @staticmethod
    def validate_message(data: Dict) -> Tuple[bool, Optional[Message], Optional[str]]:
        """
        Validate message data.
        
        Args:
            data: Dictionary containing message with cycles
            
        Returns:
            Tuple of (is_valid, Message object, error message)
        """
        try:
            message = Message(**data)
            return True, message, None
        except ValidationError as e:
            error_msg = f"Message validation failed: {e}"
            logger.error(error_msg)
            return False, None, error_msg

    @staticmethod
    def validate_redis_message(data: Dict) -> Tuple[bool, Optional[RedisMessageData], Optional[str]]:
        """
        Validate Redis message data.
        
        Args:
            data: Dictionary containing redis message
            
        Returns:
            Tuple of (is_valid, RedisMessageData object, error message)
        """
        try:
            # Handle string timestamps
            if isinstance(data.get('received_at'), str):
                data['received_at'] = datetime.fromisoformat(data['received_at'])
            
            redis_msg = RedisMessageData(**data)
            return True, redis_msg, None
        except ValidationError as e:
            error_msg = f"Redis message validation failed: {e}"
            logger.error(error_msg)
            return False, None, error_msg

    @staticmethod
    def validate_session_info(data: Dict) -> Tuple[bool, Optional[SessionInfo], Optional[str]]:
        """
        Validate session info data.
        
        Args:
            data: Dictionary containing session info
            
        Returns:
            Tuple of (is_valid, SessionInfo object, error message)
        """
        try:
            # Handle string timestamps
            if isinstance(data.get('start_time'), str):
                data['start_time'] = datetime.fromisoformat(data['start_time'])
            if isinstance(data.get('end_time'), str):
                data['end_time'] = datetime.fromisoformat(data['end_time'])
            
            session_info = SessionInfo(**data)
            return True, session_info, None
        except ValidationError as e:
            error_msg = f"Session info validation failed: {e}"
            logger.error(error_msg)
            return False, None, error_msg

    @staticmethod
    def validate_session_data(data: Dict) -> Tuple[bool, Optional[SessionData], Optional[str]]:
        """
        Validate complete session data.
        
        Args:
            data: Dictionary containing complete session data
            
        Returns:
            Tuple of (is_valid, SessionData object, error message)
        """
        try:
            session_data = SessionData(**data)
            return True, session_data, None
        except ValidationError as e:
            error_msg = f"Session data validation failed: {e}"
            logger.error(error_msg)
            return False, None, error_msg

    @staticmethod
    def validate_json_string(json_str: str, data_type: str = "redis_message") -> Tuple[bool, Optional[object], Optional[str]]:
        """
        Validate JSON string and return parsed data.
        
        Args:
            json_str: JSON string to validate
            data_type: Type of data ("cycle", "message", "redis_message", "session")
            
        Returns:
            Tuple of (is_valid, parsed object, error message)
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            error_msg = f"JSON decode error: {e}"
            logger.error(error_msg)
            return False, None, error_msg

        validators = {
            "cycle": DataValidator.validate_cycle_data,
            "message": DataValidator.validate_message,
            "redis_message": DataValidator.validate_redis_message,
            "session": DataValidator.validate_session_data,
        }

        if data_type not in validators:
            return False, None, f"Unknown data type: {data_type}"

        return validators[data_type](data)


class RedisDataHandler:
    """Helper class for working with Redis data."""

    @staticmethod
    def serialize_message(message: RedisMessageData) -> str:
        """
        Serialize RedisMessageData to JSON string.
        
        Args:
            message: RedisMessageData object
            
        Returns:
            JSON string representation
        """
        return message.model_dump_json()

    @staticmethod
    def deserialize_message(json_str: str) -> Optional[RedisMessageData]:
        """
        Deserialize JSON string to RedisMessageData.
        
        Args:
            json_str: JSON string to deserialize
            
        Returns:
            RedisMessageData object or None if invalid
        """
        is_valid, message, error = DataValidator.validate_json_string(
            json_str, data_type="redis_message"
        )
        return message if is_valid else None

    @staticmethod
    def serialize_session(session: SessionData) -> str:
        """
        Serialize SessionData to JSON string.
        
        Args:
            session: SessionData object
            
        Returns:
            JSON string representation
        """
        return session.model_dump_json(indent=2)

    @staticmethod
    def create_redis_message(
        message_id: int,
        cycles: List[Dict],
        received_at: Optional[datetime] = None
    ) -> Optional[RedisMessageData]:
        """
        Create a RedisMessageData object from components.
        
        Args:
            message_id: Sequential message ID
            cycles: List of cycle dictionaries
            received_at: Reception timestamp (defaults to now)
            
        Returns:
            RedisMessageData object or None if invalid
        """
        if received_at is None:
            received_at = datetime.now()

        data = {
            "message_id": message_id,
            "received_at": received_at,
            "data": {"cycles": cycles}
        }

        is_valid, message, error = DataValidator.validate_redis_message(data)
        if not is_valid:
            logger.error(f"Failed to create Redis message: {error}")
        return message

    @staticmethod
    def create_session_data(
        client_ip: str,
        client_port: int,
        messages: List[RedisMessageData],
        start_time: datetime,
        end_time: Optional[datetime] = None
    ) -> Optional[SessionData]:
        """
        Create a SessionData object from components.
        
        Args:
            client_ip: ESP32 client IP
            client_port: ESP32 client port
            messages: List of RedisMessageData objects
            start_time: Session start time
            end_time: Session end time
            
        Returns:
            SessionData object or None if invalid
        """
        total_messages = len(messages)
        total_cycles = sum(len(msg.data.cycles) for msg in messages)
        duration_seconds = (end_time - start_time).total_seconds() if end_time else None

        session_info_data = {
            "client_ip": client_ip,
            "client_port": client_port,
            "start_time": start_time,
            "end_time": end_time,
            "total_messages": total_messages,
            "total_cycles": total_cycles,
            "duration_seconds": duration_seconds,
        }

        data = {
            "session_info": session_info_data,
            "messages": [msg.model_dump() for msg in messages]
        }

        is_valid, session, error = DataValidator.validate_session_data(data)
        if not is_valid:
            logger.error(f"Failed to create session data: {error}")
        return session


class DataStats:
    """Utility class for computing statistics on neural data."""

    @staticmethod
    def get_message_stats(message: RedisMessageData) -> Dict:
        """
        Get statistics for a message.
        
        Args:
            message: RedisMessageData object
            
        Returns:
            Dictionary with statistics
        """
        cycles = message.data.cycles
        voltages = [c.v for c in cycles]
        times = [c.t for c in cycles]

        return {
            "message_id": message.message_id,
            "cycle_count": len(cycles),
            "voltage_min": min(voltages),
            "voltage_max": max(voltages),
            "voltage_mean": sum(voltages) / len(voltages),
            "time_min": min(times),
            "time_max": max(times),
            "spike_count": sum(len(c.gt) for c in cycles),
        }

    @staticmethod
    def get_session_stats(session: SessionData) -> Dict:
        """
        Get statistics for a complete session.
        
        Args:
            session: SessionData object
            
        Returns:
            Dictionary with session statistics
        """
        info = session.session_info
        all_cycles = [c for msg in session.messages for c in msg.data.cycles]
        voltages = [c.v for c in all_cycles]

        return {
            "client_ip": info.client_ip,
            "message_count": len(session.messages),
            "cycle_count": len(all_cycles),
            "duration_seconds": info.duration_seconds,
            "voltage_min": min(voltages) if voltages else None,
            "voltage_max": max(voltages) if voltages else None,
            "voltage_mean": sum(voltages) / len(voltages) if voltages else None,
            "total_spikes": sum(len(c.gt) for c in all_cycles),
        }
