import re
from dataclasses import dataclass
from typing import Optional

# Matches IDLE output:  Disp: 0.000 Load: 0.000 MotorState 1 Jog Speed 50mm/min
_IDLE_RE = re.compile(
    r"Disp:\s*([-\d.]+)\s+Load:\s*([-\d.]+)\s+MotorState\s+(\d)\s+Jog Speed\s+([\d.]+)mm/min",
    re.IGNORECASE,
)
# Matches RUNNING output:  Disp: 0.000 Load: 0.000
_RUN_RE = re.compile(r"Disp:\s*([-\d.]+)\s+Load:\s*([-\d.]+)", re.IGNORECASE)


@dataclass
class SensorReading:
    displacement: float
    load: float
    motor_enabled: Optional[bool] = None   # True = enabled (DriverEnableState==0)
    jog_speed: Optional[float] = None


@dataclass
class ParsedLine:
    reading: Optional[SensorReading] = None
    event: Optional[str] = None            # state-change / status string
    raw: str = ""


# Canonical event tags returned in ParsedLine.event
EVT_BOOT         = "BOOT_OK"
EVT_IDLE         = "STATE_IDLE"
EVT_RUN_3PT      = "STATE_RUN_3PT"
EVT_RUN_T        = "STATE_RUN_T"
EVT_FINISHED     = "STATE_FINISHED"
EVT_ESTOP        = "STATE_ESTOP"
EVT_TARED        = "INFO_TARED"
EVT_ZEROED       = "INFO_ZEROED"
EVT_ABORT_TRAVEL = "ABORT_TRAVEL"
EVT_ABORT_LOAD   = "ABORT_LOAD"
EVT_JOGSPEED     = "INFO_JOGSPEED"

_EVENT_MAP = {
    "BOOT OK":                                EVT_BOOT,
    "IDLE":                                   EVT_IDLE,
    "3 POINT BEND TEST STARTING":             EVT_RUN_3PT,
    "TENSILE TEST STARTING":                  EVT_RUN_T,
    "COMMANDED TO FINISH":                    EVT_FINISHED,
    "TESTING ABORTED - TRAVEL LIMIT REACHED": EVT_ABORT_TRAVEL,
    "TESTING ABORTED - LOAD LIMIT REACHED":   EVT_ABORT_LOAD,
    "ESTOP PRESSED - ALL MOTORS DISABLED":    EVT_ESTOP,
    "SCALE TARED":                            EVT_TARED,
    "DRO ZERO COMMAND SENT":                  EVT_ZEROED,
}


def parse_line(line: str) -> ParsedLine:
    line = line.strip()

    m = _IDLE_RE.search(line)
    if m:
        return ParsedLine(
            reading=SensorReading(
                displacement=float(m.group(1)),
                load=float(m.group(2)),
                motor_enabled=(int(m.group(3)) == 0),
                jog_speed=float(m.group(4)),
            ),
            raw=line,
        )

    m = _RUN_RE.search(line)
    if m:
        return ParsedLine(
            reading=SensorReading(
                displacement=float(m.group(1)),
                load=float(m.group(2)),
            ),
            raw=line,
        )

    upper = line.upper()
    for key, tag in _EVENT_MAP.items():
        if key in upper:
            return ParsedLine(event=tag, raw=line)

    if upper.startswith("JOGSPEED SET"):
        return ParsedLine(event=EVT_JOGSPEED, raw=line)

    return ParsedLine(raw=line)
