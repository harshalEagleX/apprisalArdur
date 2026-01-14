from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# --- External Documents Models ---

class EngagementLetter(BaseModel):
    borrower_name: Optional[str] = None
    property_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    lender_name: Optional[str] = None
    lender_address: Optional[str] = None
    assignment_type: Optional[str] = None  # Refinance, Purchase, etc.
    loan_type: Optional[str] = None

class PurchaseAgreement(BaseModel):
    contract_price: Optional[float] = None
    contract_date: Optional[str] = None  # Date of last signature
    seller_name: Optional[str] = None
    concessions_amount: Optional[float] = None
    personal_property_items: List[str] = []

class PublicRecord(BaseModel):
    owner_name: Optional[str] = None
    tax_year: Optional[str] = None
    assessed_value: Optional[float] = None
    zoning: Optional[str] = None

# --- Appraisal Report Sections ---

class SubjectSection(BaseModel):
    # S-1: Property Address fields
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    
    # S-2: Borrower fields
    borrower: Optional[str] = None
    co_borrower: Optional[str] = None  # Added for S-2
    
    # S-3: Owner of Public Record
    owner_of_public_record: Optional[str] = None
    
    # S-4: Legal Description and Taxes
    legal_description: Optional[str] = None
    apn: Optional[str] = None  # Assessor's Parcel #
    tax_year: Optional[str] = None
    re_taxes: Optional[float] = None
    
    # S-5: Neighborhood Name
    neighborhood_name: Optional[str] = None
    
    # S-6: Map Reference and Census Tract
    map_reference: Optional[str] = None
    census_tract: Optional[str] = None
    
    # S-7: Occupant Status
    occupant: Optional[str] = None  # Owner, Tenant, Vacant
    lease_dates: Optional[str] = None  # For Tenant occupancy
    rental_amount: Optional[float] = None  # For Tenant occupancy
    utilities_on: Optional[bool] = None  # For Vacant occupancy
    
    # S-8: Special Assessments
    special_assessments: Optional[float] = 0.0
    special_assessments_comment: Optional[str] = None
    
    # S-9: PUD and HOA
    hoa_dues: Optional[float] = 0.0
    hoa_period: Optional[str] = None  # Per Year, Per Month
    is_pud: bool = False
    
    # S-10: Lender/Client Information
    lender_name: Optional[str] = None
    lender_address: Optional[str] = None
    
    # S-11: Property Rights Appraised
    property_rights: Optional[str] = None  # Fee Simple, Leasehold, De Minimis PUD
    
    # S-12: Prior Listing/Sale History
    prior_sale_offered_12mo: Optional[bool] = None
    data_sources: Optional[str] = None
    mls_number: Optional[str] = None
    days_on_market: Optional[int] = None
    list_price: Optional[float] = None
    list_date: Optional[str] = None

class ContractSection(BaseModel):
    assignment_type: Optional[str] = None  # Refinance, Purchase, etc.
    # C-1: Contract Analysis Requirement
    did_analyze_contract: Optional[bool] = None
    contract_analysis_comment: Optional[str] = None  # Analysis commentary
    sale_type: Optional[str] = None  # Arms-Length, Non Arms-Length, REO, Short Sale, Court Ordered
    
    # C-2: Contract Price and Date
    contract_price: Optional[float] = None
    date_of_contract: Optional[str] = None  # Date of LAST signature (fully executed)
    
    # C-3: Owner of Record Data Source
    is_seller_owner: Optional[bool] = None
    owner_record_data_source: Optional[str] = None
    owner_record_commentary: Optional[str] = None  # Required when seller != owner
    
    # C-4: Financial Assistance/Concessions
    financial_assistance: Optional[bool] = None
    financial_assistance_amount: Optional[float] = None
    financial_assistance_description: Optional[str] = None
    
    # C-5: Personal Property Analysis
    sales_concessions_comment: Optional[str] = None
    personal_property_items: List[str] = []  # Items from contract
    personal_property_contributes_to_value: Optional[bool] = None

class NeighborhoodSection(BaseModel):
    # N-1: Neighborhood Characteristics
    location: Optional[str] = None  # Urban, Suburban, Rural
    built_up: Optional[str] = None  # Over 75%, 25-75%, Under 25%
    growth_rate: Optional[str] = None  # Rapid, Stable, Slow
    
    # N-2: Housing Trends
    property_values: Optional[str] = None  # Increasing, Stable, Declining
    demand_supply: Optional[str] = None  # Shortage, In Balance, Over Supply
    marketing_time: Optional[str] = None  # Under 3 mths, 3-6 mths, Over 6 mths
    
    # N-3: One-Unit Housing Price and Age
    price_low: Optional[float] = None
    price_high: Optional[float] = None
    predominant_price: Optional[float] = None
    age_low: Optional[int] = None
    age_high: Optional[int] = None
    predominant_age: Optional[int] = None
    
    # N-4: Present Land Use (all percentages should sum to 100%)
    land_use_one_unit: Optional[float] = None
    land_use_2_4_family: Optional[float] = None
    land_use_multi_family: Optional[float] = None
    land_use_commercial: Optional[float] = None
    land_use_industrial: Optional[float] = None
    land_use_other: Optional[float] = None
    land_use_other_description: Optional[str] = None
    land_use_total: Optional[float] = None  # Deprecated: for backwards compatibility
    
    # N-5: Neighborhood Boundaries
    boundaries_description: Optional[str] = None  # Must include North, South, East, West
    
    # N-6: Neighborhood Description
    description_commentary: Optional[str] = None
    
    # N-7: Market Conditions
    market_conditions_comment: Optional[str] = None

class SiteSection(BaseModel):
    # ST-1: Dimensions
    dimensions: Optional[str] = None
    
    # ST-2: Site Area
    area: Optional[float] = None
    area_unit: Optional[str] = None  # sf, ac
    
    # ST-3: Shape
    shape: Optional[str] = None
    
    # ST-4: View
    view: Optional[str] = None
    
    # ST-5: Zoning
    zoning_classification: Optional[str] = None
    zoning_description: Optional[str] = None
    zoning_compliance: Optional[str] = None  # Legal, Legal Nonconforming, No Zoning, Illegal
    
    # ST-6: Highest and Best Use
    highest_and_best_use: Optional[bool] = None
    highest_and_best_use_comment: Optional[str] = None
    
    # ST-7 & ST-9: Utilities & Off-Site Improvements
    utilities_electricity: bool = False
    utilities_electricity_other: Optional[str] = None
    utilities_gas: bool = False
    utilities_gas_other: Optional[str] = None
    utilities_water: bool = False
    utilities_water_other: Optional[str] = None
    utilities_sewer: bool = False
    utilities_sewer_other: Optional[str] = None
    
    offsite_street: Optional[str] = None # Asphalt, etc.
    offsite_street_type: Optional[str] = None # Public, Private
    offsite_alley: Optional[str] = None # None, etc.
    offsite_alley_type: Optional[str] = None # Public, Private
    
    utilities_typical: Optional[bool] = None
    utilities_typical_description: Optional[str] = None
    
    # ST-8: FEMA Flood Hazard
    fema_flood_hazard: Optional[bool] = None
    fema_flood_zone: Optional[str] = None
    fema_map_number: Optional[str] = None
    fema_map_date: Optional[str] = None
    
    # ST-10: Adverse Site Conditions
    adverse_site_conditions: Optional[bool] = None
    adverse_site_conditions_description: Optional[str] = None

class ImprovementSection(BaseModel):
    units_count: Optional[int] = 1
    stories: Optional[str] = None
    improvement_type: Optional[str] = None
    construction_status: Optional[str] = None  # Existing/Proposed/Under Construction
    design_style: Optional[str] = None
    year_built: Optional[int] = None
    effective_age: Optional[int] = None

    foundation: Optional[str] = None
    foundation_area_sf: Optional[float] = None
    basement_area_sf: Optional[float] = None
    sump_pump: Optional[bool] = None
    evidence_dampness: Optional[bool] = None
    evidence_settlement: Optional[bool] = None
    evidence_infestation: Optional[bool] = None

    foundation_walls: Optional[str] = None
    exterior_walls: Optional[str] = None
    roof_surface: Optional[str] = None
    gutters_downspouts: Optional[str] = None
    window_type: Optional[str] = None
    storm_sash_screens: Optional[str] = None

    floors: Optional[str] = None
    walls: Optional[str] = None
    trim_finish: Optional[str] = None
    bath_floor: Optional[str] = None
    bath_wainscot: Optional[str] = None

    car_storage: Optional[str] = None  # None/Driveway/Garage/Carport
    driveway_surface: Optional[str] = None
    driveway_cars: Optional[int] = None
    garage_cars: Optional[int] = None
    carport_cars: Optional[int] = None

    utilities_status: Optional[str] = None

    built_in_appliances: List[str] = []
    built_in_appliances_operational_statement: Optional[str] = None

    total_rooms: Optional[int] = None
    bedrooms: Optional[int] = None
    baths: Optional[float] = None
    gla: Optional[float] = None

    additional_features: Optional[str] = None
    condition_rating: Optional[str] = None  # C1-C6
    condition_commentary: Optional[str] = None

    adverse_conditions_affecting_livability: Optional[bool] = None
    adverse_conditions_commentary: Optional[str] = None

    conforms_to_neighborhood: Optional[bool] = None
    neighborhood_conformity_commentary: Optional[str] = None

    additions_present: Optional[bool] = None
    additions_commentary: Optional[str] = None

    security_bars_present: Optional[bool] = None
    security_bars_commentary: Optional[str] = None

class Comparable(BaseModel):
    address: Optional[str] = None
    proximity: Optional[str] = None
    sale_price: Optional[float] = None
    sale_financing_concessions: Optional[str] = None
    data_source: Optional[str] = None
    verification_source: Optional[str] = None
    sale_date: Optional[str] = None
    location_rating: Optional[str] = None
    leasehold_fee_simple: Optional[str] = None
    site_size: Optional[str] = None
    view: Optional[str] = None
    design_style: Optional[str] = None
    quality_rating: Optional[str] = None  # Q1-Q6
    actual_age: Optional[int] = None
    condition_rating: Optional[str] = None # C1-C6
    functional_utility: Optional[str] = None
    room_count_total: Optional[int] = None
    room_count_bed: Optional[int] = None
    room_count_bath: Optional[float] = None
    gla: Optional[float] = None
    basement_gla: Optional[float] = None
    heating_cooling: Optional[str] = None
    garage_carport: Optional[str] = None
    porch_patio_deck: Optional[str] = None
    net_adjustment: Optional[float] = None
    adjusted_sale_price: Optional[float] = None
    is_listing: bool = False

class SalesComparisonSection(BaseModel):
    comparables_count_sales: Optional[int] = None
    comparables_count_listings: Optional[int] = None
    comparables: List[Comparable] = []
    summary_commentary: Optional[str] = None

class AppraisalReport(BaseModel):
    form_type: str = "1004"
    subject: SubjectSection = Field(default_factory=SubjectSection)
    contract: ContractSection = Field(default_factory=ContractSection)
    neighborhood: NeighborhoodSection = Field(default_factory=NeighborhoodSection)
    site: SiteSection = Field(default_factory=SiteSection)
    improvements: ImprovementSection = Field(default_factory=ImprovementSection)
    sales_comparison: SalesComparisonSection = Field(default_factory=SalesComparisonSection)
    # Add other sections as needed

class ValidationContext(BaseModel):
    """
    The context passed to the Rule Engine. 
    Contains the parsed report and any available supporting docs.
    """
    report: AppraisalReport
    engagement_letter: Optional[EngagementLetter] = None
    purchase_agreement: Optional[PurchaseAgreement] = None
    public_record: Optional[PublicRecord] = None
    addenda_text: Optional[str] = None
