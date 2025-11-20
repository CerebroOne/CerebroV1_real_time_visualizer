# Redis Data Schema Guide

This document describes the Pydantic schemas used for neural data stored in Redis and saved to JSON files.

## Overview

The neural recording system uses a hierarchical data structure:

```
SessionData (Complete session - saved to file)
├── SessionInfo (metadata)
└── Messages[] (array of messages)
    ├── RedisMessageData
    │   ├── message_id
    │   ├── received_at
    │   └── data (Message)
    │       └── cycles[] (array of CycleData)
    │           ├── v (voltage)
    │           ├── t (time)
    │           ├── pred (predicted spikes)
    │           └── gt (ground truth spikes)
```

## Schema Details

### 1. CycleData
**Represents a single measurement cycle from the ESP32**

```python
class CycleData(BaseModel):
    v: float          # Voltage in volts (0.0 - 3.0)
    t: float          # Time in microseconds (≥ 0.0)
    pred: List[float] # Predicted spike times (microseconds)
    gt: List[float]   # Ground truth spike times (microseconds)
```

**Validation Rules:**
- `v`: Must be between 0.0 and 3.0 volts
- `t`: Must be non-negative
- `pred` & `gt`: Empty lists by default, can contain spike timestamps

**Example:**
```json
{
  "v": 1.2,
  "t": 5000.5,
  "pred": [1000.2, 2000.1],
  "gt": [1000.0, 2000.0]
}
```

---

### 2. Message
**Represents a complete message containing multiple cycles**

```python
class Message(BaseModel):
    cycles: List[CycleData]  # List of cycle measurements
```

**Example:**
```json
{
  "cycles": [
    {
      "v": 1.2,
      "t": 5000.5,
      "pred": [1000.2],
      "gt": [1000.0]
    },
    {
      "v": 1.3,
      "t": 5100.2,
      "pred": [1050.1],
      "gt": [1050.0]
    }
  ]
}
```

---

### 3. RedisMessageData
**Represents data as stored in Redis queue**

```python
class RedisMessageData(BaseModel):
    message_id: int      # Sequential ID (≥ 1)
    received_at: datetime # ISO format timestamp
    data: Message        # The actual message
```

**Purpose:** This is the format used for:
- Storing in Redis queue (`REDIS_QUEUE_NAME`)
- Serializing to JSON for file storage
- Publishing to Redis subscribers

**Example:**
```json
{
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
```

---

### 4. SessionInfo
**Metadata about a recording session**

```python
class SessionInfo(BaseModel):
    client_ip: str                  # ESP32 IP address
    client_port: int                # ESP32 port (0-65535)
    start_time: datetime            # Session start (ISO format)
    end_time: Optional[datetime]    # Session end (optional)
    total_messages: Optional[int]   # Messages received (≥ 0)
    total_cycles: Optional[int]     # Cycles processed (≥ 0)
    duration_seconds: Optional[float] # Duration in seconds (≥ 0)
```

**Example:**
```json
{
  "client_ip": "192.168.1.100",
  "client_port": 54321,
  "start_time": "2025-11-21T12:34:00",
  "end_time": "2025-11-21T12:35:30",
  "total_messages": 100,
  "total_cycles": 500,
  "duration_seconds": 90.0
}
```

---

### 5. SessionData
**Complete session data saved to JSON file**

```python
class SessionData(BaseModel):
    session_info: SessionInfo           # Session metadata
    messages: List[RedisMessageData]    # All messages from session
```

**Example:**
```json
{
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
```

---

## Usage Examples

### Validating Data from Redis

```python
from schema import RedisMessageData
import json

# Get message from Redis
redis_json = redis_client.lpop('neural_data_queue')
data_dict = json.loads(redis_json)

# Validate with Pydantic
try:
    validated_message = RedisMessageData(**data_dict)
    print(f"Message {validated_message.message_id} is valid")
    print(f"Contains {len(validated_message.data.cycles)} cycles")
except ValidationError as e:
    print(f"Invalid data: {e}")
```

### Validating Session Data from File

```python
from schema import SessionData
import json

# Load from file
with open('neural_data_20251121.json', 'r') as f:
    data_dict = json.load(f)

# Validate
try:
    session = SessionData(**data_dict)
    print(f"Session: {session.session_info.client_ip}")
    print(f"Messages: {len(session.messages)}")
    print(f"Duration: {session.session_info.duration_seconds}s")
except ValidationError as e:
    print(f"Invalid session data: {e}")
```

### Creating Data Manually

```python
from schema import CycleData, Message, RedisMessageData
from datetime import datetime

# Create cycle data
cycle = CycleData(
    v=1.5,
    t=5000.0,
    pred=[1000.0, 2000.0],
    gt=[1001.0, 2001.0]
)

# Create message
message = Message(cycles=[cycle])

# Create Redis message
redis_msg = RedisMessageData(
    message_id=1,
    received_at=datetime.now(),
    data=message
)

# Serialize to JSON
import json
json_str = redis_msg.model_dump_json()
redis_client.rpush('neural_data_queue', json_str)
```

---

## Integration with reciver.py

The receiver uses these schemas implicitly:

1. **Receiving**: ESP32 sends raw JSON messages with cycles
2. **Parsing**: Messages are parsed into `RedisMessageData`
3. **Redis Publishing**: Serialized to JSON and pushed to queue
4. **File Saving**: Session data is collected as `SessionData`
5. **Validation**: Can be validated using Pydantic schemas

### Current Flow (without explicit validation)

```
ESP32 → JSON → dict → RedisMessageData (implicit) → Redis
                  ↓
              SessionData (implicit) → JSON File
```

### Recommended Enhancement

Add explicit validation in `reciver.py`:

```python
from schema import RedisMessageData, ValidationError

try:
    data = json.loads(line.decode("utf-8"))
    message_data = {
        "message_id": message_count,
        "received_at": datetime.now().isoformat(),
        "data": data,
    }
    # Validate
    validated = RedisMessageData(**message_data)
    # Publish to Redis
    redis_client.rpush(redis_queue, validated.model_dump_json())
except ValidationError as e:
    logger.error(f"Validation error: {e}")
```

---

## Redis Configuration

**Queue Name:** `REDIS_QUEUE_NAME` (default: `neural_data_queue`)

**Data Format in Queue:** JSON string of `RedisMessageData`

**Queue Operations:**
- **Add message:** `redis_client.rpush(queue_name, json_string)`
- **Get message:** `redis_client.lpop(queue_name)`
- **Get length:** `redis_client.llen(queue_name)`
- **Get all:** `redis_client.lrange(queue_name, 0, -1)`

---

## Field Constraints Summary

| Field | Type | Constraints | Example |
|-------|------|-------------|---------|
| `CycleData.v` | float | 0.0 < v < 3.0 | 1.2 |
| `CycleData.t` | float | t ≥ 0.0 | 5000.5 |
| `CycleData.pred` | List[float] | Optional | [1000.2] |
| `CycleData.gt` | List[float] | Optional | [1000.0] |
| `Message.cycles` | List[CycleData] | Required | [...] |
| `RedisMessageData.message_id` | int | id ≥ 1 | 1 |
| `RedisMessageData.received_at` | datetime | ISO format | 2025-11-21T12:34:56.789123 |
| `SessionInfo.client_port` | int | 0 ≤ port ≤ 65535 | 54321 |
| `SessionInfo.total_messages` | int | ≥ 0 | 100 |
| `SessionInfo.total_cycles` | int | ≥ 0 | 500 |
| `SessionInfo.duration_seconds` | float | ≥ 0 | 90.0 |

---

## Best Practices

1. **Always validate incoming data** from ESP32 or Redis
2. **Use schema for serialization** to ensure consistency
3. **Include error handling** for validation failures
4. **Log validation errors** for debugging
5. **Use type hints** when working with schema objects
6. **Document custom extensions** to schemas

---

## Related Files

- **Schema definitions:** `real_time_visualizer_src/schema.py`
- **TCP Server:** `real_time_visualizer_src/reciver.py`
- **Report Generator:** `scripts/dataset_report_generator.py`
- **Consumer Example:** `real_time_visualizer_src/consumer_example.py`
