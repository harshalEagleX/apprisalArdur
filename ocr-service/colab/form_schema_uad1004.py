# Form Schema and ROI Map for UAD 1004 Form - Page 4
# This defines the structure for intelligent field extraction

FORM_SCHEMA = {
    "form_type": "UAD_1004",
    "page": 4,
    "sections": {
        "subject": {
            "property_address": {"type": "address", "required": True},
            "city": {"type": "text", "required": True},
            "state": {"type": "state_code", "required": True},
            "zip_code": {"type": "zip", "required": True},
            "borrower": {"type": "text", "required": True},
            "owner_of_record": {"type": "text", "required": True},
            "county": {"type": "text", "required": True},
            "legal_description": {"type": "text", "required": True},
            "assessor_parcel": {"type": "text", "required": True},
            "tax_year": {"type": "year", "required": True},
            "re_taxes": {"type": "currency", "required": True},
            "neighborhood_name": {"type": "text", "required": False},
            "map_reference": {"type": "text", "required": False},
            "census_tract": {"type": "text", "required": True},
            "special_assessments": {"type": "currency", "required": False},
        },
        "contract": {
            "contract_price": {"type": "currency", "required": True},
            "date_of_contract": {"type": "date", "required": True},
            "property_seller_owner": {"type": "boolean", "required": True},
            "financial_assistance": {"type": "currency", "required": False},
        },
        "neighborhood": {
            "location": {"type": "enum", "values": ["Urban", "Suburban", "Rural"]},
            "built_up": {"type": "enum", "values": ["Over 75%", "25-75%", "Under 25%"]},
            "growth": {"type": "enum", "values": ["Rapid", "Stable", "Slow"]},
            "property_values": {"type": "enum", "values": ["Increasing", "Stable", "Declining"]},
            "demand_supply": {"type": "enum", "values": ["Shortage", "In Balance", "Over Supply"]},
            "marketing_time": {"type": "enum", "values": ["Under 3 mths", "3-6 mths", "Over 6 mths"]},
        },
        "site": {
            "dimensions": {"type": "text", "required": False},
            "area": {"type": "area", "required": True},
            "shape": {"type": "text", "required": False},
            "view": {"type": "text", "required": False},
            "zoning": {"type": "text", "required": True},
            "zoning_description": {"type": "text", "required": True},
            "fema_flood_zone": {"type": "text", "required": True},
            "fema_map_number": {"type": "text", "required": True},
            "fema_map_date": {"type": "date", "required": True},
        },
        "improvements": {
            "units": {"type": "enum", "values": ["One", "One with Accessory Unit"]},
            "stories": {"type": "number", "required": True},
            "type": {"type": "enum", "values": ["Det.", "Att.", "S-Det./End Unit"]},
            "design_style": {"type": "text", "required": True},
            "year_built": {"type": "year", "required": True},
            "effective_age": {"type": "number", "required": True},
            "foundation": {"type": "text", "required": True},
            "exterior_walls": {"type": "text", "required": True},
            "roof_surface": {"type": "text", "required": True},
            "heating": {"type": "text", "required": True},
            "cooling": {"type": "text", "required": True},
            "rooms": {"type": "number", "required": True},
            "bedrooms": {"type": "number", "required": True},
            "bathrooms": {"type": "number", "required": True},
            "gla_sqft": {"type": "number", "required": True},
            "condition": {"type": "condition_rating", "required": True},
        },
        "property_rights": {
            "appraised": {"type": "enum", "values": ["Fee Simple", "Leasehold", "Other"]},
        },
        "assignment_type": {
            "type": {"type": "enum", "values": ["Purchase Transaction", "Refinance Transaction", "Other"]},
        },
        "occupant": {
            "status": {"type": "enum", "values": ["Owner", "Tenant", "Vacant"]},
        },
    }
}

# Checkbox Group Definitions - Mutually Exclusive Sets
CHECKBOX_GROUPS = {
    "property_rights": {
        "options": ["Fee Simple", "Leasehold", "Other"],
        "mutually_exclusive": True,
        "required": True
    },
    "assignment_type": {
        "options": ["Purchase Transaction", "Refinance Transaction", "Other"],
        "mutually_exclusive": True,
        "required": True
    },
    "occupant": {
        "options": ["Owner", "Tenant", "Vacant"],
        "mutually_exclusive": True,
        "required": True
    },
    "location": {
        "options": ["Urban", "Suburban", "Rural"],
        "mutually_exclusive": True,
        "required": True
    },
    "built_up": {
        "options": ["Over 75%", "25-75%", "Under 25%"],
        "mutually_exclusive": True,
        "required": True
    },
    "property_values": {
        "options": ["Increasing", "Stable", "Declining"],
        "mutually_exclusive": True,
        "required": True
    },
    "foundation_type": {
        "options": ["Concrete Slab", "Crawl Space", "Full Basement", "Partial Basement"],
        "mutually_exclusive": False,
        "required": True
    },
    "units": {
        "options": ["One", "One with Accessory Unit"],
        "mutually_exclusive": True,
        "required": True
    },
    "dwelling_type": {
        "options": ["Det.", "Att.", "S-Det./End Unit"],
        "mutually_exclusive": True,
        "required": True
    },
    "status": {
        "options": ["Existing", "Proposed", "Under Const."],
        "mutually_exclusive": True,
        "required": True
    },
    "fema_flood": {
        "options": ["Yes", "No"],
        "mutually_exclusive": True,
        "required": True
    },
}

# Normalization Dictionary
NORMALIZATION_MAP = {
    # Materials
    "CBS/AVERAGE": "CBS / Average",
    "CBS/AVG": "CBS / Average",
    "TILE/AVE": "Tile / Average",
    "TILE/AVG": "Tile / Average",
    "DRYWALL/AVG": "Drywall / Average",
    "WOOD/AVG": "Wood / Average",
    "CONCRETE/AVG": "Concrete / Average",
    # Conditions
    "C1": "C1 - New",
    "C2": "C2 - Excellent",
    "C3": "C3 - Good",
    "C4": "C4 - Average",
    "C5": "C5 - Fair",
    "C6": "C6 - Poor",
    # Yes/No
    "Y": "Yes",
    "N": "No",
    "YES": "Yes",
    "NO": "No",
}

# Validation Rules
VALIDATION_RULES = {
    "contract_price": {
        "type": "currency",
        "min": 10000,
        "max": 100000000,
        "cross_validate": ["sales_comparison_price"]
    },
    "gla_sqft": {
        "type": "number",
        "min": 100,
        "max": 50000,
        "tolerance_pct": 2.0
    },
    "year_built": {
        "type": "year",
        "min": 1800,
        "max": 2025
    },
    "effective_age": {
        "type": "number",
        "min": 0,
        "max": 100
    },
    "re_taxes": {
        "type": "currency",
        "min": 0,
        "max": 500000
    },
    "bedrooms": {
        "type": "number",
        "min": 0,
        "max": 20
    },
    "bathrooms": {
        "type": "number",
        "min": 0.5,
        "max": 15
    },
    "rooms": {
        "type": "number",
        "min": 1,
        "max": 50
    },
    "state": {
        "type": "enum",
        "values": ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"]
    },
    "fema_zone": {
        "type": "enum",
        "values": ["A","AE","AH","AO","AR","A99","V","VE","X","B","C","D"]
    }
}

print("✅ Form schema loaded: UAD 1004")
print(f"   Sections: {len(FORM_SCHEMA['sections'])}")
print(f"   Checkbox groups: {len(CHECKBOX_GROUPS)}")
print(f"   Normalization rules: {len(NORMALIZATION_MAP)}")
print(f"   Validation rules: {len(VALIDATION_RULES)}")
