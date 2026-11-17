from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,Text,ForeignKey,DateTime,func
from datetime import datetime
from ..config.database import Base
class Batch(Base):
    __tablename__='batches'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(120),unique=True)
    sample_id:Mapped[int]=mapped_column(ForeignKey('samples.id'))
    candidate_sql:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(20),default='queued')
    # 复核受理时冻结的依据：账单快照表、两侧冻结语句与快照校验信息
    snapshot_table:Mapped[str|None]=mapped_column(String(120),nullable=True)
    frozen_original_sql:Mapped[str|None]=mapped_column(Text,nullable=True)
    frozen_candidate_sql:Mapped[str|None]=mapped_column(Text,nullable=True)
    snapshot_row_count:Mapped[int|None]=mapped_column(nullable=True)
    snapshot_checksum:Mapped[str|None]=mapped_column(String(64),nullable=True)
    frozen_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    # 执行者租约（并发领取控制）
    lease_owner:Mapped[str|None]=mapped_column(String(80),nullable=True)
    lease_token:Mapped[str|None]=mapped_column(String(64),nullable=True)
    lease_until:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    attempts:Mapped[int]=mapped_column(default=0,server_default='0')
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
