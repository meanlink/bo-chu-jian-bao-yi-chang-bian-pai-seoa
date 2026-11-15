from pydantic import BaseModel, Field

class ContractInput(BaseModel):
    source_version: str = Field(min_length=1, max_length=80)
    name: str = Field(default='', max_length=160)
    column_mapping: dict = Field(min_length=1)
    units: dict = Field(default_factory=dict)

class BatchInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    source: str = Field(default='manual.csv', max_length=200)
    source_version: str = Field(min_length=1, max_length=80)
    raw_text: str = Field(min_length=1, max_length=8_000_000)

class RawReplaceInput(BaseModel):
    source: str = Field(default='manual.csv', max_length=200)
    raw_text: str = Field(min_length=1, max_length=8_000_000)
