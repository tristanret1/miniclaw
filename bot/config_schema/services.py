from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoogleCalendarConfig:
    enabled: bool = False


@dataclass(frozen=True)
class CronConfig:
    enabled: bool = True
    timezone: str = "America/Vancouver"
    max_concurrent: int = 5
    tick_interval_min: float = 2.0
    tick_interval_max: float = 60.0
    backoff: tuple = field(default_factory=lambda: (30, 60, 300, 900, 3600))


@dataclass(frozen=True)
class HealthConfig:
    enabled: bool = True


@dataclass(frozen=True)
class TimeoutConfig:
    http_read: int = 120
    http_connect: int = 10
    exec_default: int = 30
    exec_max: int = 120
    acp_max: int = 600


@dataclass(frozen=True)
class ServicesConfig:
    google_calendar: GoogleCalendarConfig = field(default_factory=GoogleCalendarConfig)
    cron: CronConfig = field(default_factory=CronConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
