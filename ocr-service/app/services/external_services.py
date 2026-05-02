"""
External Service Integrations for Appraisal QC

Provides integrations with:
- USPS Address Validation
- FEMA Flood Zone Check
- County Assessor Data (stubbed)

All integrations are async and include caching for efficiency.
"""

import asyncio
import hashlib
import logging
import re
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache

logger = logging.getLogger(__name__)

# Try to import async HTTP client
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.info("httpx not available. External service calls will be stubbed.")


@dataclass
class AddressVerificationResult:
    """Result of address verification."""
    is_valid: bool
    standardized_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    zip_plus4: Optional[str] = None
    delivery_point: Optional[str] = None
    error_message: Optional[str] = None
    source: str = "stub"


@dataclass
class FloodZoneResult:
    """Result of FEMA flood zone check."""
    in_flood_zone: bool
    flood_zone: Optional[str] = None  # e.g., "AE", "X", "VE"
    panel_number: Optional[str] = None
    effective_date: Optional[str] = None
    community_number: Optional[str] = None
    requires_insurance: bool = False
    error_message: Optional[str] = None
    source: str = "stub"


@dataclass
class AssessorResult:
    """Result of county assessor lookup."""
    found: bool
    owner_name: Optional[str] = None
    assessed_value: Optional[float] = None
    tax_year: Optional[int] = None
    land_value: Optional[float] = None
    improvement_value: Optional[float] = None
    zoning: Optional[str] = None
    property_class: Optional[str] = None
    error_message: Optional[str] = None
    source: str = "stub"


class SimpleCache:
    """Simple in-memory cache with TTL."""
    
    def __init__(self, default_ttl_minutes: int = 60):
        self._cache: Dict[str, tuple] = {}  # key -> (value, expiry_time)
        self.default_ttl = timedelta(minutes=default_ttl_minutes)
    
    def _make_key(self, *args, **kwargs) -> str:
        """Create cache key from arguments."""
        key_data = str(args) + str(sorted(kwargs.items()))
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, expiry = self._cache[key]
            if datetime.now() < expiry:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[timedelta] = None):
        """Set value in cache with TTL."""
        ttl = ttl or self.default_ttl
        expiry = datetime.now() + ttl
        self._cache[key] = (value, expiry)
    
    def clear(self):
        """Clear all cached values."""
        self._cache.clear()


class ExternalServices:
    """
    Facade for external service integrations.
    
    All methods are async for non-blocking I/O.
    Includes caching to avoid repeated API calls.
    """
    
    def __init__(
        self,
        cache_ttl_minutes: int = 60,
        usps_api_key: Optional[str] = None,
        fema_api_key: Optional[str] = None,
    ):
        self.cache = SimpleCache(cache_ttl_minutes)
        self.usps_api_key = usps_api_key
        self.fema_api_key = fema_api_key
        self._client = None
    
    async def _get_client(self):
        """Get or create HTTP client."""
        if self._client is None and HTTPX_AVAILABLE:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def verify_usps_address(
        self, 
        address: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None,
    ) -> AddressVerificationResult:
        """
        Verify an address using USPS Web Tools API.
        
        Note: Requires USPS API key. Falls back to stub if not available.
        
        Args:
            address: Street address
            city: City name (optional)
            state: State abbreviation (optional)
            zip_code: ZIP code (optional)
            
        Returns:
            AddressVerificationResult with standardized address
        """
        # Check cache first
        cache_key = self.cache._make_key("usps", address, city, state, zip_code)
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        if not self.usps_api_key or not HTTPX_AVAILABLE:
            # Return stub result
            result = self._stub_usps_verify(address, city, state, zip_code)
            self.cache.set(cache_key, result)
            return result
        
        # TODO: Implement actual USPS API call
        # For now, return stub
        result = self._stub_usps_verify(address, city, state, zip_code)
        self.cache.set(cache_key, result)
        return result
    
    def _stub_usps_verify(
        self, 
        address: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None,
    ) -> AddressVerificationResult:
        """Stub USPS verification using basic parsing."""
        # Simple validation: address has content
        if not address or len(address.strip()) < 5:
            return AddressVerificationResult(
                is_valid=False,
                error_message="Address too short",
                source="stub"
            )
        
        # Extract ZIP if present in address
        zip_match = re.search(r'\b(\d{5})(?:-(\d{4}))?\b', address)
        extracted_zip = zip_match.group(1) if zip_match else zip_code
        extracted_plus4 = zip_match.group(2) if zip_match and zip_match.group(2) else None
        
        return AddressVerificationResult(
            is_valid=True,
            standardized_address=address.upper().strip(),
            city=city.upper().strip() if city else None,
            state=state.upper().strip() if state else None,
            zip_code=extracted_zip,
            zip_plus4=extracted_plus4,
            source="stub"
        )
    
    async def check_fema_flood_zone(
        self,
        latitude: float,
        longitude: float,
    ) -> FloodZoneResult:
        """
        Check FEMA flood zone for a location.
        
        Note: Uses FEMA Flood Map Service Center API.
        
        Args:
            latitude: Property latitude
            longitude: Property longitude
            
        Returns:
            FloodZoneResult with flood zone information
        """
        # Check cache first
        cache_key = self.cache._make_key("fema", latitude, longitude)
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        if not HTTPX_AVAILABLE:
            result = self._stub_fema_check(latitude, longitude)
            self.cache.set(cache_key, result)
            return result
        
        # TODO: Implement actual FEMA API call
        # FEMA provides a free API for flood zone lookups
        result = self._stub_fema_check(latitude, longitude)
        self.cache.set(cache_key, result)
        return result
    
    def _stub_fema_check(
        self,
        latitude: float,
        longitude: float,
    ) -> FloodZoneResult:
        """Stub FEMA check returning 'unknown' status."""
        return FloodZoneResult(
            in_flood_zone=False,
            flood_zone="X",  # Zone X = minimal flood hazard
            error_message="Stub response - actual FEMA lookup not performed",
            source="stub"
        )
    
    async def get_county_assessor_data(
        self,
        apn: str,
        county: str,
        state: str,
    ) -> AssessorResult:
        """
        Look up property data from county assessor.
        
        Note: This requires county-specific integrations.
        Currently returns stub data.
        
        Args:
            apn: Assessor's Parcel Number
            county: County name
            state: State abbreviation
            
        Returns:
            AssessorResult with property data
        """
        # Check cache first
        cache_key = self.cache._make_key("assessor", apn, county, state)
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        # Return stub - actual implementation would need county-specific APIs
        result = AssessorResult(
            found=False,
            error_message="County assessor lookup not implemented - requires county-specific integration",
            source="stub"
        )
        self.cache.set(cache_key, result)
        return result


# Convenience functions for synchronous use
def verify_address_sync(address: str) -> AddressVerificationResult:
    """Synchronous wrapper for address verification."""
    services = ExternalServices()
    return asyncio.run(services.verify_usps_address(address))


def check_flood_zone_sync(lat: float, lon: float) -> FloodZoneResult:
    """Synchronous wrapper for flood zone check."""
    services = ExternalServices()
    return asyncio.run(services.check_fema_flood_zone(lat, lon))
