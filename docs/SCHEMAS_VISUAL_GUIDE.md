# Pydantic Schemas - Visual Guide

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         ESP32 Device                              │
│                  (Neural Recording Hardware)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ TCP Connection
                             │ JSON Messages
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                 TCP Server (reciver.py)                           │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Parse JSON                                               │  │
│  │ {"cycles": [...]}                                        │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Validate with Pydantic (Optional)                        │  │
│  │ - Check voltage range                                    │  │
│  │ - Validate spike timestamps                              │  │
│  │ - Ensure data types                                      │  │
│  └────────────────┬──────────────────────────────────────────┘  │
│                   │                                              │
│         ┌─────────┴─────────┐                                    │
│         │                   │                                    │
│         ▼                   ▼                                    │
│    ┌─────────┐      ┌─────────────────┐                         │
│    │ Redis   │      │ JSON File       │                         │
│    │ Queue   │      │ (Session Data)  │                         │
│    └─────────┘      └─────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
         │                       │
         │ RedisMessageData      │ SessionData
         │ (JSON string)         │ (JSON file)
         │                       │
         ▼                       ▼
    ┌──────────┐         ┌──────────────┐
    │ Consumer │         │ Analysis     │
    │ Services │         │ Tools        │
    └──────────┘         └──────────────┘
```

## Schema Hierarchy

```
SessionData (Saved to File)
│
├─ SessionInfo
│  ├─ client_ip: str              "192.168.1.100"
│  ├─ client_port: int            54321
│  ├─ start_time: datetime        2025-11-21T12:34:00
│  ├─ end_time: datetime          2025-11-21T12:35:30
│  ├─ total_messages: int         100
│  ├─ total_cycles: int           500
│  └─ duration_seconds: float     90.0
│
└─ messages: List[RedisMessageData]  (Published to Redis & Saved)
   │
   ├─ message_id: int             1
   ├─ received_at: datetime       2025-11-21T12:34:05.123456
   │
   └─ data: Message
      │
      └─ cycles: List[CycleData]
         │
         ├─ v: float              1.2  (Voltage in volts)
         ├─ t: float              5000.5  (Time in microseconds)
         ├─ pred: List[float]     [1000.2, 2000.1]  (Predicted spikes)
         └─ gt: List[float]       [1000.0, 2000.0]  (Ground truth)
```

## Field Validation Constraints

```
┌───────────────────────────────────────────────────────────────┐
│                     CycleData Validation                       │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  v (Voltage)                 gt (Ground Truth)               │
│  ┌──────────────────┐        ┌──────────────────┐           │
│  │ 0.0 <  v < 3.0  │        │ List of floats   │           │
│  │ (0.1V to 2.9V)  │        │ (spike times)    │           │
│  └──────────────────┘        └──────────────────┘           │
│         ▲                            ▲                       │
│      VALID RANGE                  OPTIONAL                   │
│                                                               │
│  t (Time)                    pred (Predicted)                │
│  ┌──────────────────┐        ┌──────────────────┐           │
│  │  t ≥ 0.0        │        │ List of floats   │           │
│  │ (microseconds)  │        │ (spike times)    │           │
│  └──────────────────┘        └──────────────────┘           │
│         ▲                            ▲                       │
│      NON-NEGATIVE                 OPTIONAL                   │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

## Redis Queue Integration

```
                ┌─────────────────────┐
                │   Neural Receiver   │
                │   (reciver.py)      │
                └──────────┬──────────┘
                           │
                  Message Validation
                  (Optional: Pydantic)
                           │
           ┌───────────────┴──────────────┐
           │                              │
           ▼                              ▼
    ┌─────────────┐              ┌────────────────┐
    │  Serialize  │              │  Save to File  │
    │ to JSON     │              │  (SessionData) │
    └──────┬──────┘              └────────────────┘
           │
           ▼
    ┌─────────────┐
    │    Redis    │
    │    Queue    │
    │ (FIFO List) │
    └─────────────┘
           │
           ├──► Consumer 1 (Analysis)
           ├──► Consumer 2 (Visualization)
           └──► Consumer N (Custom Processing)
```

## Validation Workflow

```
Input Data (Raw JSON)
       │
       ▼
┌──────────────────────────────────────┐
│  Parse JSON String                   │
│  json.loads(data)                    │
└──────────────┬───────────────────────┘
               │
               ▼
        ┌──────────────────┐
        │ Create Dict      │
        │ with metadata    │
        │ + timestamp      │
        └────────┬─────────┘
                 │
                 ▼
┌──────────────────────────────────────┐
│  Validate with Pydantic Schema       │
│  RedisMessageData(**data_dict)       │
└──────────────┬───────────────────────┘
               │
         ┌─────┴─────┐
         │           │
        ✓ VALID    ✗ INVALID
         │           │
         ▼           ▼
    ┌────────┐  ┌──────────────┐
    │ Store  │  │ Log Error &  │
    │ in     │  │ Skip Message │
    │ Redis  │  └──────────────┘
    └────────┘
```

## Serialization Flow

```
Python Object                 JSON String
(Pydantic Model)              (for Redis/File)

RedisMessageData
  ├─ message_id: 1        ==serialize==>  {
  ├─ received_at: dt      (JSON dump)       "message_id": 1,
  └─ data:                                   "received_at": "2025-...",
      ├─ cycles: [                         "data": {
      │    CycleData                         "cycles": [
      │    ├─ v: 1.2     ==================   {"v": 1.2, "t": ...},
      │    ├─ t: 5000.5                       ...
      │    ├─ pred: []                      ]
      │    └─ gt: []                      }
      └─                                  }


                    Redis Queue
                  (as JSON string)
                        │
         ┌──────────────┼──────────────┐
         │              │              │
         ▼              ▼              ▼
     Consumer1      Consumer2      Consumer3
   (deserialize)   (deserialize)   (deserialize)
         │              │              │
         ▼              ▼              ▼
     Analysis      Visualization   Custom Logic
```

## Data Types Reference

```
BASIC TYPES:
│
├─ float
│  └─ Range: -∞ to +∞ (constrained by Field())
│     Example: 1.234, 5000.5
│
├─ int
│  └─ Range: -∞ to +∞ (constrained by Field())
│     Example: 1, 54321
│
├─ str
│  └─ Any string value
│     Example: "192.168.1.100"
│
└─ datetime
   └─ ISO format timestamp
      Example: "2025-11-21T12:34:56.789123"

CONTAINER TYPES:
│
├─ List[T]
│  └─ List of type T
│     Example: [1.0, 2.0, 3.0] (List[float])
│
└─ Optional[T]
   └─ Type T or None
      Example: Some value or null

PYDANTIC TYPES:
│
├─ BaseModel
│  └─ Base class for all schemas
│
└─ Field()
   └─ Field descriptor with constraints
      Example: Field(..., ge=0.0, le=1.0)
            -> greater than or equal, less than or equal
```

## Error Handling Pattern

```
try:
    data = json.loads(raw_json)
    
    # Create data dict with validation
    message_data = {
        "message_id": message_count,
        "received_at": datetime.now().isoformat(),
        "data": data
    }
    
    # Validate
    is_valid, validated_msg, error = DataValidator.validate_redis_message(
        message_data
    )
    
    if not is_valid:
        logger.error(f"Validation failed: {error}")  ← Log and skip
        continue
    
    # Process valid data
    redis_client.rpush(queue, RedisDataHandler.serialize_message(validated_msg))
    
except Exception as e:
    logger.error(f"Unexpected error: {e}")  ← Catch all
```

## File Structure

```
project/
├── real_time_visualizer_src/
│   ├── schema.py              ← Pydantic schemas
│   ├── validators.py          ← Validation utilities
│   ├── integration_examples.py ← Usage examples
│   └── reciver.py             ← TCP server (can integrate validation)
│
├── REDIS_SCHEMA_GUIDE.md      ← Complete documentation
├── PYDANTIC_SCHEMAS_SUMMARY.md ← Quick reference
└── (this file)                ← Visual guide
```

## Quick Validation Checklist

```
Before Storing in Redis:
  ☐ Message ID is positive integer (≥ 1)
  ☐ received_at is valid ISO datetime
  ☐ cycles list is not empty
  
For Each Cycle:
  ☐ voltage is 0.0 < v < 3.0
  ☐ time is ≥ 0.0
  ☐ pred list contains valid floats (optional)
  ☐ gt list contains valid floats (optional)
  
Before Saving Session:
  ☐ client_ip is valid IP format
  ☐ client_port is 0-65535
  ☐ start_time < end_time (if both present)
  ☐ total_messages matches message count
  ☐ total_cycles matches total cycle count
  ☐ duration_seconds ≥ 0
```
