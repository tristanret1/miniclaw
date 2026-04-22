"""Typed dataclass schema for config.yaml.

All fields have defaults matching config.yaml so AppConfig.from_dict({}) works.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Helpers ──────────────────────────────────────────────────────────────────

def _bool(v: Any, default: bool) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    if v is None:
        return default
    return bool(v)


def _int(v: Any, default: int) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _float(v: Any, default: float) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _str(v: Any, default: str) -> str:
    return str(v) if v is not None else default


def _list(v: Any, default: list) -> list:
    if isinstance(v, list):
        return v
    return default if v is None else list(v)


# ── Sub-configs ───────────────────────────────────────────────────────────────

@dataclass
class AnthropicConfig:
    model: str = "claude-sonnet-4-20250514"
    api_url: str = "https://api.anthropic.com/v1/messages"

    @classmethod
    def from_dict(cls, d: dict) -> AnthropicConfig:
        return cls(
            model=_str(d.get("model"), "claude-sonnet-4-20250514"),
            api_url=_str(d.get("api_url"), "https://api.anthropic.com/v1/messages"),
        )


@dataclass
class CodexConfig:
    model: str = "gpt-5.3-codex"
    api_url: str = "https://chatgpt.com/backend-api/codex/responses"

    @classmethod
    def from_dict(cls, d: dict) -> CodexConfig:
        return cls(
            model=_str(d.get("model"), "gpt-5.3-codex"),
            api_url=_str(d.get("api_url"), "https://chatgpt.com/backend-api/codex/responses"),
        )


@dataclass
class GLMConfig:
    model: str = "glm-4.7-flash"
    api_url: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    @classmethod
    def from_dict(cls, d: dict) -> GLMConfig:
        return cls(
            model=_str(d.get("model"), "glm-4.7-flash"),
            api_url=_str(d.get("api_url"), "https://api.z.ai/api/paas/v4/chat/completions"),
        )


@dataclass
class MinimaxConfig:
    model: str = "MiniMax-M2.7"
    api_url: str = "https://api.minimaxi.com/v1/text/chatcompletion_v2"

    @classmethod
    def from_dict(cls, d: dict) -> MinimaxConfig:
        return cls(
            model=_str(d.get("model"), "MiniMax-M2.7"),
            api_url=_str(d.get("api_url"), "https://api.minimaxi.com/v1/text/chatcompletion_v2"),
        )


@dataclass
class KimiConfig:
    model: str = "kimi-latest"
    api_url: str = "https://api.moonshot.cn/v1/chat/completions"

    @classmethod
    def from_dict(cls, d: dict) -> KimiConfig:
        return cls(
            model=_str(d.get("model"), "kimi-latest"),
            api_url=_str(d.get("api_url"), "https://api.moonshot.cn/v1/chat/completions"),
        )


@dataclass
class LLMConfig:
    provider: str = "anthropic"
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    codex: CodexConfig = field(default_factory=CodexConfig)
    glm: GLMConfig = field(default_factory=GLMConfig)
    minimax: MinimaxConfig = field(default_factory=MinimaxConfig)
    kimi: KimiConfig = field(default_factory=KimiConfig)
    max_history: int = 25
    max_tokens: int = 4096
    tools_enabled: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> LLMConfig:
        return cls(
            provider=_str(d.get("provider"), "anthropic"),
            anthropic=AnthropicConfig.from_dict(d.get("anthropic") or {}),
            codex=CodexConfig.from_dict(d.get("codex") or {}),
            glm=GLMConfig.from_dict(d.get("glm") or {}),
            minimax=MinimaxConfig.from_dict(d.get("minimax") or {}),
            kimi=KimiConfig.from_dict(d.get("kimi") or {}),
            max_history=_int(d.get("max_history"), 25),
            max_tokens=_int(d.get("max_tokens"), 4096),
            tools_enabled=_bool(d.get("tools_enabled"), False),
        )


@dataclass
class AutoReplyConfig:
    enabled: bool = False
    channels: list = field(default_factory=list)
    chance: float = 0.1
    keywords: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> AutoReplyConfig:
        return cls(
            enabled=_bool(d.get("enabled"), False),
            channels=_list(d.get("channels"), []),
            chance=_float(d.get("chance"), 0.1),
            keywords=_list(d.get("keywords"), []),
        )


@dataclass
class StreamConfig:
    flush_interval: float = 0.1
    flush_chars: int = 50

    @classmethod
    def from_dict(cls, d: dict) -> StreamConfig:
        return cls(
            flush_interval=_float(d.get("flush_interval"), 0.1),
            flush_chars=_int(d.get("flush_chars"), 50),
        )


@dataclass
class DiscordConfig:
    greeting_channel_id: str = ""
    allowed_dm_users: list = field(default_factory=list)
    auto_reply: AutoReplyConfig = field(default_factory=AutoReplyConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)

    @classmethod
    def from_dict(cls, d: dict) -> DiscordConfig:
        return cls(
            greeting_channel_id=_str(d.get("greeting_channel_id"), ""),
            allowed_dm_users=_list(d.get("allowed_dm_users"), []),
            auto_reply=AutoReplyConfig.from_dict(d.get("auto_reply") or {}),
            stream=StreamConfig.from_dict(d.get("stream") or {}),
        )


@dataclass
class VoiceConfig:
    enabled: bool = False
    sample_rate: int = 16000
    silence_threshold: int = 500
    silence_duration: float = 1.5
    conversation_timeout: float = 30.0
    playback_cooldown: float = 0.5
    wake_words: list = field(default_factory=lambda: ["小圆", "小方"])
    tts_provider: str = "volcengine"
    tts_voice: str = "cedar"
    tts_model: str = "gpt-4o-mini-tts"
    tts_speed: float = 1.2
    stt_model: str = "gpt-4o-transcribe"
    stt_language: str = "zh"
    stt_prompt: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> VoiceConfig:
        return cls(
            enabled=_bool(d.get("enabled"), False),
            sample_rate=_int(d.get("sample_rate"), 16000),
            silence_threshold=_int(d.get("silence_threshold"), 500),
            silence_duration=_float(d.get("silence_duration"), 1.5),
            conversation_timeout=_float(d.get("conversation_timeout"), 30.0),
            playback_cooldown=_float(d.get("playback_cooldown"), 0.5),
            wake_words=_list(d.get("wake_words"), ["小圆", "小方"]),
            tts_provider=_str(d.get("tts_provider"), "volcengine"),
            tts_voice=_str(d.get("tts_voice"), "cedar"),
            tts_model=_str(d.get("tts_model"), "gpt-4o-mini-tts"),
            tts_speed=_float(d.get("tts_speed"), 1.2),
            stt_model=_str(d.get("stt_model"), "gpt-4o-transcribe"),
            stt_language=_str(d.get("stt_language"), "zh"),
            stt_prompt=_str(d.get("stt_prompt"), ""),
        )


@dataclass
class VolcengineConfig:
    tts_resource_id: str = "volc.service_type.10029"
    tts_speaker: str = "zh_male_beijingxiaoye_emo_v2_mars_bigtts"

    @classmethod
    def from_dict(cls, d: dict) -> VolcengineConfig:
        return cls(
            tts_resource_id=_str(d.get("tts_resource_id"), "volc.service_type.10029"),
            tts_speaker=_str(d.get("tts_speaker"), "zh_male_beijingxiaoye_emo_v2_mars_bigtts"),
        )


@dataclass
class SMSConfig:
    enabled: bool = False
    webhook_port: int = 8080
    webhook_url: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> SMSConfig:
        return cls(
            enabled=_bool(d.get("enabled"), False),
            webhook_port=_int(d.get("webhook_port"), 8080),
            webhook_url=_str(d.get("webhook_url"), ""),
        )



@dataclass
class HeartbeatConfig:
    enabled: bool = False
    interval: str = "30m"
    channel_id: str = ""
    active_start: str = ""
    active_end: str = ""
    active_tz: str = ""
    ack_max_chars: int = 300
    isolated: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> HeartbeatConfig:
        return cls(
            enabled=_bool(d.get("enabled"), False),
            interval=_str(d.get("interval"), "30m"),
            channel_id=_str(d.get("channel_id"), ""),
            active_start=_str(d.get("active_start"), ""),
            active_end=_str(d.get("active_end"), ""),
            active_tz=_str(d.get("active_tz"), ""),
            ack_max_chars=_int(d.get("ack_max_chars"), 300),
            isolated=_bool(d.get("isolated"), True),
        )


@dataclass
class ApiConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8766
    api_key: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> ApiConfig:
        return cls(
            enabled=_bool(d.get("enabled"), False),
            host=_str(d.get("host"), "127.0.0.1"),
            port=_int(d.get("port"), 8766),
            api_key=_str(d.get("api_key"), ""),
        )



@dataclass
class GatewayConfig:
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    volcengine: VolcengineConfig = field(default_factory=VolcengineConfig)
    sms: SMSConfig = field(default_factory=SMSConfig)
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
    api: ApiConfig = field(default_factory=ApiConfig)

    @classmethod
    def from_dict(cls, d: dict) -> GatewayConfig:
        return cls(
            voice=VoiceConfig.from_dict(d.get("voice") or {}),
            volcengine=VolcengineConfig.from_dict(d.get("volcengine") or {}),
            sms=SMSConfig.from_dict(d.get("sms") or {}),
            heartbeat=HeartbeatConfig.from_dict(d.get("heartbeat") or {}),
            api=ApiConfig.from_dict(d.get("api") or {}),
        )


@dataclass
class SQLiteStorageConfig:
    sessions_path: str = "workspace/sessions.db"
    memory_path: str = "workspace/memory/memory.db"

    @classmethod
    def from_dict(cls, d: dict) -> SQLiteStorageConfig:
        return cls(
            sessions_path=_str(d.get("sessions_path"), "workspace/sessions.db"),
            memory_path=_str(d.get("memory_path"), "workspace/memory/memory.db"),
        )


@dataclass
class StorageConfig:
    backend: str = "sqlite"
    sqlite: SQLiteStorageConfig = field(default_factory=SQLiteStorageConfig)

    @classmethod
    def from_dict(cls, d: dict) -> StorageConfig:
        return cls(
            backend=_str(d.get("backend"), "sqlite"),
            sqlite=SQLiteStorageConfig.from_dict(d.get("sqlite") or {}),
        )


@dataclass
class GoogleCalendarConfig:
    enabled: bool = False
    life_calendar_id: str = ""
    work_calendar_id: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> GoogleCalendarConfig:
        return cls(
            enabled=_bool(d.get("enabled"), False),
            life_calendar_id=_str(d.get("life_calendar_id"), ""),
            work_calendar_id=_str(d.get("work_calendar_id"), ""),
        )


@dataclass
class CronConfig:
    enabled: bool = True
    timezone: str = "America/Vancouver"
    max_concurrent: int = 5
    tick_interval_min: float = 2.0
    tick_interval_max: float = 60.0
    backoff: list = field(default_factory=lambda: [30, 60, 300, 900, 3600])

    @classmethod
    def from_dict(cls, d: dict) -> CronConfig:
        return cls(
            enabled=_bool(d.get("enabled"), True),
            timezone=_str(d.get("timezone"), "America/Vancouver"),
            max_concurrent=_int(d.get("max_concurrent"), 5),
            tick_interval_min=_float(d.get("tick_interval_min"), 2.0),
            tick_interval_max=_float(d.get("tick_interval_max"), 60.0),
            backoff=_list(d.get("backoff"), [30, 60, 300, 900, 3600]),
        )


@dataclass
class HealthConfig:
    enabled: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> HealthConfig:
        return cls(enabled=_bool(d.get("enabled"), True))


@dataclass
class KbConfig:
    enabled: bool = True
    root: str = "~/kb"
    auto_compile: bool = True
    compile_timeout: int = 600
    query_timeout: int = 300

    @classmethod
    def from_dict(cls, d: dict) -> KbConfig:
        return cls(
            enabled=_bool(d.get("enabled"), True),
            root=_str(d.get("root"), "~/kb"),
            auto_compile=_bool(d.get("auto_compile"), True),
            compile_timeout=_int(d.get("compile_timeout"), 600),
            query_timeout=_int(d.get("query_timeout"), 300),
        )


@dataclass
class TimeoutsConfig:
    http_read: int = 120
    http_connect: int = 10
    exec_default: int = 30
    exec_max: int = 120
    acp_max: int = 600

    @classmethod
    def from_dict(cls, d: dict) -> TimeoutsConfig:
        return cls(
            http_read=_int(d.get("http_read"), 120),
            http_connect=_int(d.get("http_connect"), 10),
            exec_default=_int(d.get("exec_default"), 30),
            exec_max=_int(d.get("exec_max"), 120),
            acp_max=_int(d.get("acp_max"), 600),
        )


@dataclass
class ServicesConfig:
    google_calendar: GoogleCalendarConfig = field(default_factory=GoogleCalendarConfig)
    cron: CronConfig = field(default_factory=CronConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    kb: KbConfig = field(default_factory=KbConfig)
    timeouts: TimeoutsConfig = field(default_factory=TimeoutsConfig)

    @classmethod
    def from_dict(cls, d: dict) -> ServicesConfig:
        return cls(
            google_calendar=GoogleCalendarConfig.from_dict(d.get("google_calendar") or {}),
            cron=CronConfig.from_dict(d.get("cron") or {}),
            health=HealthConfig.from_dict(d.get("health") or {}),
            kb=KbConfig.from_dict(d.get("kb") or {}),
            timeouts=TimeoutsConfig.from_dict(d.get("timeouts") or {}),
        )


# ── Root config ───────────────────────────────────────────────────────────────

@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    services: ServicesConfig = field(default_factory=ServicesConfig)

    @classmethod
    def from_dict(cls, d: dict) -> AppConfig:
        return cls(
            llm=LLMConfig.from_dict(d.get("llm") or {}),
            discord=DiscordConfig.from_dict(d.get("discord") or {}),
            gateway=GatewayConfig.from_dict(d.get("gateway") or {}),
            storage=StorageConfig.from_dict(d.get("storage") or {}),
            services=ServicesConfig.from_dict(d.get("services") or {}),
        )
