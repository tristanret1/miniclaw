from dataclasses import dataclass, field


@dataclass(frozen=True)
class VolcengineConfig:
    tts_resource_id: str = "volc.service_type.10029"
    tts_speaker: str = "zh_male_beijingxiaoye_emo_v2_mars_bigtts"


@dataclass(frozen=True)
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
    volcengine: VolcengineConfig = field(default_factory=VolcengineConfig)


@dataclass(frozen=True)
class SMSConfig:
    enabled: bool = False
    webhook_port: int = 8080
    max_message_length: int = 1600


@dataclass(frozen=True)
class IMessageConfig:
    enabled: bool = False
    cli_path: str = "imsg"
    service: str = "auto"


@dataclass(frozen=True)
class HeartbeatConfig:
    enabled: bool = False
    interval: str = "30m"
    ack_max_chars: int = 300
    isolated: bool = True


@dataclass(frozen=True)
class GatewayConfig:
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    sms: SMSConfig = field(default_factory=SMSConfig)
    imessage: IMessageConfig = field(default_factory=IMessageConfig)
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
