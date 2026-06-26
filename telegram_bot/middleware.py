"""
Rate limiting middleware for FastAPI.

Simple in-memory rate limiting based on IP address and endpoint.
"""

import time
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware that limits requests per IP per endpoint.
    
    Configuration:
    - Default: 100 requests per minute per IP
    - Webhook endpoints: 1000 requests per minute per IP (higher limit)
    """
    
    def __init__(self, app, requests_per_minute: int = 100):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_counts: Dict[Tuple[str, str], list] = defaultdict(list)
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, considering proxies."""
        if request.headers.get("x-forwarded-for"):
            return request.headers.get("x-forwarded-for").split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    def _get_limit_for_path(self, path: str) -> int:
        """Get rate limit for specific path."""
        # Higher limits for webhook endpoints
        if "/telegram/webhook" in path or "/telegram/tenant-webhook" in path:
            return self.requests_per_minute * 10  # 1000 req/min
        
        # Health check has no limit
        if path == "/health":
            return 10000
        
        return self.requests_per_minute  # 100 req/min default
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        client_ip = self._get_client_ip(request)
        path = request.url.path
        limit = self._get_limit_for_path(path)
        
        key = (client_ip, path)
        now = time.time()
        
        # Remove old requests (older than 60 seconds)
        self.request_counts[key] = [
            timestamp for timestamp in self.request_counts[key]
            if now - timestamp < 60
        ]
        
        # Check rate limit
        if len(self.request_counts[key]) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded"
            )
        
        # Add current request
        self.request_counts[key].append(now)
        
        # Clean up old entries periodically
        if len(self.request_counts) > 10000:
            # Remove IP+path combinations with no recent activity
            cutoff = now - 120
            self.request_counts = {
                k: v for k, v in self.request_counts.items()
                if any(ts > cutoff for ts in v)
            }
        
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(
            limit - len(self.request_counts[key])
        )
        
        return response
