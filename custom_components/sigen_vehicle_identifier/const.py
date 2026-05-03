DOMAIN = "sigen_vehicle_identifier"

CONF_SLAVE_ID = "slave_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_READ_ONLY = "read_only"

DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 1
DEFAULT_SCAN_INTERVAL = 30

# DC charger running state enum values
RUNNING_STATE_IDLE = 0x00
RUNNING_STATE_OCCUPIED = 0x01
RUNNING_STATE_PREPARING_COMM = 0x02
RUNNING_STATE_CHARGING = 0x03
RUNNING_STATE_FAULT = 0x04
RUNNING_STATE_SCHEDULED = 0x05
RUNNING_STATE_ENDED = 0x06
RUNNING_STATE_UNAVAILABLE = 0x07
RUNNING_STATE_DISCHARGING = 0x08
RUNNING_STATE_ALARM = 0x09
RUNNING_STATE_PREPARING_INSULATION = 0x0A

RUNNING_STATE_NAMES = {
    RUNNING_STATE_IDLE: "Idle",
    RUNNING_STATE_OCCUPIED: "Occupied",
    RUNNING_STATE_PREPARING_COMM: "Preparing",
    RUNNING_STATE_CHARGING: "Charging",
    RUNNING_STATE_FAULT: "Fault",
    RUNNING_STATE_SCHEDULED: "Scheduled",
    RUNNING_STATE_ENDED: "Ended",
    RUNNING_STATE_UNAVAILABLE: "Unavailable",
    RUNNING_STATE_DISCHARGING: "Discharging",
    RUNNING_STATE_ALARM: "Alarm",
    RUNNING_STATE_PREPARING_INSULATION: "Preparing Insulation",
}

ACTIVE_STATES = {
    RUNNING_STATE_OCCUPIED,
    RUNNING_STATE_PREPARING_COMM,
    RUNNING_STATE_CHARGING,
    RUNNING_STATE_DISCHARGING,
    RUNNING_STATE_ALARM,
    RUNNING_STATE_PREPARING_INSULATION,
    RUNNING_STATE_SCHEDULED,
}

END_STATES = {
    RUNNING_STATE_IDLE,
    RUNNING_STATE_ENDED,
    RUNNING_STATE_FAULT,
    RUNNING_STATE_UNAVAILABLE,
}

# DC charger Modbus register addresses (FC04 input registers)
# Addresses as documented by Sigenergy — adjust base offset if needed
REG_DC_VOLTAGE = 31500
REG_DC_CURRENT = 31501
REG_DC_POWER_HI = 31502    # S32 high word
REG_DC_POWER_LO = 31503    # S32 low word
REG_DC_SOC = 31504
REG_DC_CHARGING_CAP_HI = 31505   # U32 high word
REG_DC_CHARGING_CAP_LO = 31506   # U32 low word
REG_DC_DURATION_HI = 31507       # U32 high word
REG_DC_DURATION_LO = 31508       # U32 low word
REG_DC_RUNNING_STATE = 31513

# DC charger Modbus register addresses (FC03 holding registers)
REG_DC_START_STOP = 41000

# Storage keys
STORAGE_KEY = "sigen_vehicle_identifier_sessions"
STORAGE_VERSION = 1
MAX_SESSIONS = 200

MIN_TAGGED_SESSIONS_FOR_CENTROID = 2
LOW_CONFIDENCE_THRESHOLD = 0.85

# Pre-seeded car IDs
CAR_ID_ZOE = "renault_zoe_2022"
CAR_ID_MG = "mg_zs_ev_2022"
CAR_ID_GEELY = "geely_ex5_2026"

DEFAULT_CARS = {
    CAR_ID_ZOE: {
        "name": "Renault Zoe",
        "color": "#FFD700",
        "created": None,
        "session_count": 0,
        "correct_predictions": 0,
    },
    CAR_ID_MG: {
        "name": "MG ZS EV",
        "color": "#C0C0C0",
        "created": None,
        "session_count": 0,
        "correct_predictions": 0,
    },
    CAR_ID_GEELY: {
        "name": "Geely EX5",
        "color": "#4169E1",
        "created": None,
        "session_count": 0,
        "correct_predictions": 0,
    },
}

# Identification algorithm thresholds
LFP_VSOC_THRESHOLD = 7.6       # v_soc_ratio above this → LFP (Geely)
CAPACITY_THRESHOLD_KWH = 63.0   # below → Zoe, above → MG
MIN_SOC_DELTA_FOR_CAPACITY = 2.0   # % SOC change needed for capacity estimate
MIN_ENERGY_FOR_CAPACITY = 0.5      # kWh delivered before capacity estimate
MIN_V2H_ENERGY_FOR_DV_DE = 1.0    # kWh discharged before dV/dE method
DV_DE_THRESHOLD = 2.8              # V/kWh — above → Zoe (faster drop)

FEATURE_WEIGHTS = {
    "v_soc_ratio": 4.0,
    "estimated_capacity_kwh": 4.0,
    "initial_voltage": 2.0,
    "dv_de": 1.5,
    "peak_power_kw": 1.0,
}

NOTIFICATION_ID = "sigen_dc_charger_session"
