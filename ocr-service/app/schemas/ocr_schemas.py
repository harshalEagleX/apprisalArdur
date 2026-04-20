from typing import Optional
from pydantic import BaseModel

class ExtractedFields(BaseModel):
    borrowerName: Optional[str] = None
    coBorrowerName: Optional[str] = None
    propertyAddress: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipCode: Optional[str] = None
    appraisedValue: Optional[float] = None
    effectiveDate: Optional[str] = None
    salePrice: Optional[float] = None
    lenderName: Optional[str] = None
    appraiserName: Optional[str] = None
    appraiserLicenseNumber: Optional[str] = None


class CheckboxFields(BaseModel):
    isInFloodZone: bool = False
    isForSale: bool = False
    hasPoolOrSpa: bool = False
    isCondoOrPUD: bool = False
    isPud: bool = False
    isManufacturedHome: bool = False
    didAnalyzeContract: bool = False


class OcrResponse(BaseModel):
    success: bool
    processingTimeMs: int
    confidenceScore: float
    formType: Optional[str] = None
    extractedFields: ExtractedFields
    checkboxes: CheckboxFields
    rawText: Optional[str] = None
    warnings: list[str] = []
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    message: str
