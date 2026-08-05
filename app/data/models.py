from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    payload: Mapped[dict] = mapped_column(JSON)
    family: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    status: Mapped[str] = mapped_column(String(32))
    family: Mapped[str] = mapped_column(String(64))
    renderer: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    freq_per_day: Mapped[float | None] = mapped_column(Float)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    source_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SensorReading(Base):
    """Historico rotulado de sensores (seed do banner.xlsx).

    Fonte de verdade de leitura do kNN e das estatisticas. Nao confundir com
    Event: eventos novos do /eventos carregam rotulo PREDITO e ficam fora
    deste corpus (sem feedback loop do classificador).
    """
    __tablename__ = "sensor_readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fault: Mapped[str] = mapped_column(String(64))
    family: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    z_rms_velocity_in_s: Mapped[float | None] = mapped_column(Float)
    z_rms_velocity_mm_s: Mapped[float | None] = mapped_column(Float)
    temperature_f: Mapped[float | None] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    x_rms_velocity_in_s: Mapped[float | None] = mapped_column(Float)
    x_rms_velocity_mm_s: Mapped[float | None] = mapped_column(Float)
    z_peak_acceleration_g: Mapped[float | None] = mapped_column(Float)
    x_peak_acceleration_g: Mapped[float | None] = mapped_column(Float)
    z_peak_vel_comp_freq_hz: Mapped[float | None] = mapped_column(Float)
    x_peak_vel_comp_freq_hz: Mapped[float | None] = mapped_column(Float)
    z_rms_acceleration_g: Mapped[float | None] = mapped_column(Float)
    x_rms_acceleration_g: Mapped[float | None] = mapped_column(Float)
    z_kurtosis: Mapped[float | None] = mapped_column(Float)
    x_kurtosis: Mapped[float | None] = mapped_column(Float)
    z_crest_factor: Mapped[float | None] = mapped_column(Float)
    x_crest_factor: Mapped[float | None] = mapped_column(Float)
    z_peak_velocity_in_s: Mapped[float | None] = mapped_column(Float)
    z_peak_velocity_mm_s: Mapped[float | None] = mapped_column(Float)
    x_peak_velocity_in_s: Mapped[float | None] = mapped_column(Float)
    x_peak_velocity_mm_s: Mapped[float | None] = mapped_column(Float)
    z_high_freq_rms_accel_g: Mapped[float | None] = mapped_column(Float)
    x_high_freq_rms_accel_g: Mapped[float | None] = mapped_column(Float)
    rpm: Mapped[float | None] = mapped_column(Float)
