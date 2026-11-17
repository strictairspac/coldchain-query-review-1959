from pydantic import BaseModel
class FreezeBasis(BaseModel):
    snapshot_table:str|None=None
    frozen_original_sql:str|None=None
    frozen_candidate_sql:str|None=None
    snapshot_row_count:int|None=None
    snapshot_checksum:str|None=None
    frozen_at:str|None=None
    attempts:int|None=None
class EvidenceOutput(BaseModel):
    id:int
    batch_id:int
    result:dict
    freeze_basis:FreezeBasis|None=None
