from pydantic import BaseModel


class VaultNote(BaseModel):
    folder: str
    filename: str
    content: str


class VaultFile(BaseModel):
    filename: str
    content: str


class VaultPayload(BaseModel):
    notes: list[VaultNote]
    canvas: VaultFile
    index: VaultFile
    log_entry: str
