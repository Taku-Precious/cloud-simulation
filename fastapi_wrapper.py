"""
FastAPI HTTP wrapper for Cloud Storage gRPC backend.
Provides REST API endpoints for authentication and file operations.
"""

import os
import io
import grpc
import logging
import uuid
import sys
from typing import Optional
from datetime import datetime
from pathlib import Path

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

# Import gRPC client and local services
from integration.auth_token_validator import AuthTokenValidator
from integration.unified_server import UnifiedCloudService
import cloudsecurity_pb2
import cloudsecurity_pb2_grpc

# ============================================================================
# CONFIGURATION
# ============================================================================

GRPC_HOST = "localhost"
GRPC_PORT = 51234
API_HOST = "localhost"
API_PORT = 8000
REACT_ORIGIN = "http://localhost:3000"

# ============================================================================
# PYDANTIC MODELS - Request/Response Validation
# ============================================================================

class RegisterRequest(BaseModel):
    """User registration request"""
    username: str = Field(..., min_length=3, max_length=20)
    email: str = Field(...)
    password: str = Field(..., min_length=8)
    
    @validator('email')
    def validate_email(cls, v):
        if '@' not in v or '.' not in v:
            raise ValueError('Invalid email format')
        return v.lower()
    
    @validator('username')
    def validate_username(cls, v):
        if not v.replace('_', '').isalnum():
            raise ValueError('Username must be alphanumeric or contain underscores')
        return v


class LoginRequest(BaseModel):
    """User login request"""
    username: str
    password: str


class OTPVerifyRequest(BaseModel):
    """OTP verification request"""
    session_id: str
    username: str
    otp: str = Field(..., min_length=6, max_length=6)


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class AuthResponse(BaseModel):
    """Authentication response"""
    success: bool
    message: str
    auth_token: Optional[str] = None
    session_id: Optional[str] = None
    email_masked: Optional[str] = None
    expires_in: Optional[int] = None


class FileMetadata(BaseModel):
    """File metadata"""
    file_id: str
    filename: str
    file_size: int
    checksum: str
    uploaded_at: str
    modified_at: Optional[str] = None


class FileListResponse(BaseModel):
    """File list response"""
    success: bool
    message: str
    files: list[FileMetadata]
    total_count: int
    limit: int
    offset: int


class QuotaResponse(BaseModel):
    """User quota response"""
    success: bool
    message: str
    total_quota_bytes: int
    total_quota_gb: float
    used_bytes: int
    used_gb: float
    available_bytes: int
    available_gb: float
    usage_percentage: float
    file_count: int


class AccountInfoResponse(BaseModel):
    """User account info response"""
    success: bool
    message: str
    username: str
    email: str
    account_created: str
    last_login: str
    total_files: int
    storage_used_gb: float


class ErrorDetail(BaseModel):
    """Error detail"""
    code: str
    message: str
    details: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response"""
    success: bool
    error: ErrorDetail
    timestamp: str


# ============================================================================
# FASTAPI APPLICATION SETUP
# ============================================================================

app = FastAPI(
    title="Cloud Storage API",
    description="REST API for cloud file storage system",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[REACT_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# GLOBALS - gRPC Connection
# ============================================================================

grpc_channel = None
grpc_stub = None
unified_service = None
token_validator = None

@app.on_event("startup")
async def startup_event():
    """Initialize gRPC connection on startup"""
    global grpc_channel, grpc_stub, unified_service, token_validator
    
    try:
        logger.info("Initializing FastAPI wrapper")
        logger.info(f"Connecting to gRPC server at {GRPC_HOST}:{GRPC_PORT}")
        
        # Initialize unified service for local operations
        try:
            unified_service = UnifiedCloudService()
            logger.info("UnifiedCloudService initialized locally")
        except Exception as e:
            logger.error(f"Could not initialize UnifiedCloudService: {e}")
            raise
        
        # Initialize token validator
        try:
            token_validator = AuthTokenValidator()
            logger.info("AuthTokenValidator initialized")
        except Exception as e:
            logger.warning(f"Could not initialize AuthTokenValidator: {e}")
        
        logger.info("FastAPI wrapper initialized successfully")
    
    except Exception as e:
        logger.error(f"Failed to initialize FastAPI wrapper: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Close gRPC connection on shutdown"""
    global grpc_channel
    if grpc_channel:
        await grpc_channel.close()
        logger.info("gRPC connection closed")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def mask_email(email: str) -> str:
    """Mask email for privacy - u***@example.com"""
    parts = email.split('@')
    if len(parts[0]) <= 2:
        masked = parts[0][0] + '*' * 3
    else:
        masked = parts[0][0] + '*' * (len(parts[0]) - 2) + parts[0][-1]
    return f"{masked}@{parts[1]}"


def create_error_response(code: str, message: str, details: str = None) -> ErrorResponse:
    """Create standardized error response"""
    return ErrorResponse(
        success=False,
        error=ErrorDetail(code=code, message=message, details=details),
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


async def validate_auth_token(authorization: Optional[str]) -> tuple[bool, str, Optional[str]]:
    """
    Validate auth token from Authorization header.
    Returns: (is_valid, username, error_message)
    """
    if not authorization:
        return False, None, "Missing Authorization header"
    
    if not authorization.startswith("Bearer "):
        return False, None, "Invalid Authorization format. Use: Bearer <token>"
    
    token = authorization[7:]  # Remove "Bearer " prefix
    
    try:
        if token_validator:
            username = token_validator.validate_token(token)
            if username:
                return True, username, None
            else:
                return False, None, "Invalid or expired auth token"
        else:
            # Fallback: try to validate using gRPC
            return False, None, "Token validator not initialized"
    
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return False, None, f"Token validation failed: {str(e)}"


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.post("/auth/register", response_model=AuthResponse, status_code=201)
async def register(request: RegisterRequest):
    """
    Register new user account.
    
    Args:
        request: Registration details (username, email, password)
    
    Returns:
        201: User created successfully
        400: Invalid input
        409: Username or email already exists
        422: Password doesn't meet strength requirements
    """
    try:
        logger.info(f"Registration request for user: {request.username}")
        
        # Validate password strength
        if len(request.password) < 8:
            raise HTTPException(
                status_code=422,
                detail="Password must be at least 8 characters"
            )
        
        if not any(c.isupper() for c in request.password):
            raise HTTPException(
                status_code=422,
                detail="Password must contain at least one uppercase letter"
            )
        
        if not any(c.isdigit() for c in request.password):
            raise HTTPException(
                status_code=422,
                detail="Password must contain at least one digit"
            )
        
        # Call gRPC to register
        if unified_service:
            success, message = unified_service._register_user(
                request.username,
                request.email,
                request.password
            )
            
            if success:
                logger.info(f"User registered successfully: {request.username}")
                return AuthResponse(
                    success=True,
                    message="User registered successfully",
                    auth_token=None,
                    session_id=None
                )
            else:
                # Check if it's a conflict (username/email exists)
                if "already exists" in message or "duplicate" in message.lower():
                    raise HTTPException(status_code=409, detail=message)
                else:
                    raise HTTPException(status_code=400, detail=message)
        else:
            raise HTTPException(status_code=500, detail="Service not initialized")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/login", response_model=AuthResponse, status_code=200)
async def login(request: LoginRequest):
    """
    Initiate login - send OTP to email.
    
    Args:
        request: Login credentials (username, password)
    
    Returns:
        200: OTP sent successfully (session_id returned)
        401: Invalid credentials
        429: Too many failed attempts (rate limited)
    """
    try:
        logger.info(f"Login request for user: {request.username}")
        
        if not request.username or not request.password:
            raise HTTPException(
                status_code=400,
                detail="Username and password required"
            )
        
        # Call gRPC login via unified service
        if unified_service:
            # Create gRPC request
            grpc_request = cloudsecurity_pb2.Request(
                login=request.username,
                password=request.password
            )
            
            # Call login method on the gRPC service
            grpc_response = unified_service.login(grpc_request, None)
            result = grpc_response.result
            
            if "SUCCESS" in result:
                parts = result.split("|")
                session_id = parts[1] if len(parts) > 1 else ""
                message = parts[2] if len(parts) > 2 else "OTP sent"
                
                # Get email from database for masking
                user = unified_service.auth_db.get_user(request.username)
                email_masked = mask_email(user['email']) if user else "***@***.***"
                
                logger.info(f"OTP sent to user: {request.username}")
                return AuthResponse(
                    success=True,
                    message="OTP sent successfully",
                    session_id=session_id,
                    email_masked=email_masked
                )
            else:
                # Check for rate limiting
                if "Too many" in result or "rate" in result.lower():
                    raise HTTPException(status_code=429, detail=result)
                else:
                    raise HTTPException(status_code=401, detail=result)
        else:
            raise HTTPException(status_code=500, detail="Service not initialized")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/verify-otp", response_model=AuthResponse, status_code=200)
async def verify_otp(request: OTPVerifyRequest):
    """
    Verify OTP and complete authentication.
    
    Args:
        request: OTP verification details (session_id, username, otp)
    
    Returns:
        200: Authentication successful (auth_token returned)
        401: Invalid or expired OTP/session
        400: Invalid OTP format
    """
    try:
        logger.info(f"OTP verification for user: {request.username}")
        
        # Verify request format
        if not all([request.session_id, request.username, request.otp]):
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: session_id, username, otp"
            )
        
        # Call gRPC OTP verification via unified service
        if unified_service:
            verify_string = f"OTP_VERIFY|{request.username}|{request.session_id}|{request.otp}"
            
            grpc_request = cloudsecurity_pb2.Request(
                login="__OTP_VERIFY__",
                password=verify_string
            )
            
            grpc_response = unified_service.login(grpc_request, None)
            result = grpc_response.result
            
            if "AUTH_SUCCESS" in result:
                parts = result.split("|")
                auth_token = parts[1] if len(parts) > 1 else ""
                
                logger.info(f"User authenticated successfully: {request.username}")
                return AuthResponse(
                    success=True,
                    message="Authentication successful",
                    auth_token=auth_token,
                    expires_in=3600  # 1 hour
                )
            else:
                raise HTTPException(status_code=401, detail=result)
        else:
            raise HTTPException(status_code=500, detail="Service not initialized")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FILE STORAGE ENDPOINTS
# ============================================================================

@app.post("/storage/upload", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """
    Upload file to user's cloud storage.
    
    Args:
        file: File to upload
        authorization: Bearer token
    
    Returns:
        201: File uploaded successfully
        401: Invalid auth token
        413: File too large
        507: User quota exceeded
    """
    try:
        # Validate auth
        is_valid, username, error_msg = await validate_auth_token(authorization)
        if not is_valid:
            raise HTTPException(status_code=401, detail=error_msg)
        
        logger.info(f"Upload request from user: {username}, file: {file.filename}")
        
        # Read file content
        content = await file.read()
        
        if not content:
            raise HTTPException(status_code=400, detail="File is empty")
        
        # Limit file size (example: 5GB)
        MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024  # 5GB
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: 5GB"
            )
        
        # Call gRPC upload
        if unified_service:
            success, message, file_id = unified_service.storage_manager.upload_file(
                authorization.replace("Bearer ", ""),
                file.filename,
                content
            )
            
            if success:
                logger.info(f"File uploaded successfully: {file_id}")
                return {
                    "success": True,
                    "message": message,
                    "file_id": file_id,
                    "filename": file.filename,
                    "file_size": len(content),
                    "checksum": "calculated_by_storage_manager",
                    "uploaded_at": datetime.utcnow().isoformat() + "Z"
                }
            else:
                # Check if quota exceeded
                if "quota" in message.lower():
                    raise HTTPException(status_code=507, detail=message)
                else:
                    raise HTTPException(status_code=400, detail=message)
        else:
            raise HTTPException(status_code=500, detail="Service not initialized")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/storage/download/{file_id}")
async def download_file(
    file_id: str,
    authorization: Optional[str] = Header(None)
):
    """
    Download file from user's cloud storage.
    
    Args:
        file_id: File identifier
        authorization: Bearer token
    
    Returns:
        200: File content (binary)
        401: Invalid auth token
        403: Access denied
        404: File not found
        410: File deleted
    """
    try:
        # Validate auth
        is_valid, username, error_msg = await validate_auth_token(authorization)
        if not is_valid:
            raise HTTPException(status_code=401, detail=error_msg)
        
        logger.info(f"Download request from user: {username}, file_id: {file_id}")
        
        # Call gRPC download
        if unified_service:
            success, message, file_data = unified_service.storage_manager.download_file(
                authorization.replace("Bearer ", ""),
                file_id
            )
            
            if success:
                logger.info(f"File downloaded successfully: {file_id}")
                return Response(
                    content=file_data,
                    media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename=\"{file_id}\""}
                )
            else:
                # Determine error type
                if "deleted" in message.lower():
                    raise HTTPException(status_code=410, detail=message)
                elif "not found" in message.lower():
                    raise HTTPException(status_code=404, detail=message)
                elif "denied" in message.lower():
                    raise HTTPException(status_code=403, detail=message)
                else:
                    raise HTTPException(status_code=400, detail=message)
        else:
            raise HTTPException(status_code=500, detail="Service not initialized")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/storage/{file_id}", status_code=200)
async def delete_file(
    file_id: str,
    authorization: Optional[str] = Header(None)
):
    """
    Delete file from user's cloud storage.
    
    Args:
        file_id: File identifier
        authorization: Bearer token
    
    Returns:
        200: File deleted successfully
        401: Invalid auth token
        403: Access denied
        404: File not found
    """
    try:
        # Validate auth
        is_valid, username, error_msg = await validate_auth_token(authorization)
        if not is_valid:
            raise HTTPException(status_code=401, detail=error_msg)
        
        logger.info(f"Delete request from user: {username}, file_id: {file_id}")
        
        # Call gRPC delete
        if unified_service:
            success, message = unified_service.storage_manager.delete_file(
                authorization.replace("Bearer ", ""),
                file_id
            )
            
            if success:
                logger.info(f"File deleted successfully: {file_id}")
                return {
                    "success": True,
                    "message": message,
                    "file_id": file_id
                }
            else:
                # Determine error type
                if "not found" in message.lower():
                    raise HTTPException(status_code=404, detail=message)
                elif "denied" in message.lower():
                    raise HTTPException(status_code=403, detail=message)
                else:
                    raise HTTPException(status_code=400, detail=message)
        else:
            raise HTTPException(status_code=500, detail="Service not initialized")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/storage/list", status_code=200)
async def list_files(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
    authorization: Optional[str] = Header(None)
):
    """
    List files in user's cloud storage.
    
    Args:
        limit: Max files to return (default 50, max 100)
        offset: Pagination offset (default 0)
        sort_by: Sort by field (created_at, name, size)
        order: Sort order (asc, desc)
        authorization: Bearer token
    
    Returns:
        200: File list with metadata
        401: Invalid auth token
    """
    try:
        # Validate sort parameters
        if sort_by not in ['created_at', 'name', 'size']:
            raise HTTPException(status_code=400, detail="Invalid sort_by parameter")
        if order not in ['asc', 'desc']:
            raise HTTPException(status_code=400, detail="Invalid order parameter")
        
        # Validate auth
        is_valid, username, error_msg = await validate_auth_token(authorization)
        if not is_valid:
            raise HTTPException(status_code=401, detail=error_msg)
        
        logger.info(f"List request from user: {username}, limit: {limit}, offset: {offset}")
        
        # Call gRPC list
        if unified_service:
            success, message, files = unified_service.storage_manager.list_user_files(
                authorization.replace("Bearer ", "")
            )
            
            if success:
                # Apply sorting and pagination
                sorted_files = files  # Would apply sort_by/order here
                paginated_files = sorted_files[offset:offset+limit]
                
                file_list = [
                    FileMetadata(
                        file_id=f.get('file_id', ''),
                        filename=f.get('filename', ''),
                        file_size=f.get('file_size', 0),
                        checksum=f.get('checksum', ''),
                        uploaded_at=f.get('uploaded_at', ''),
                        modified_at=f.get('modified_at', '')
                    )
                    for f in paginated_files
                ]
                
                logger.info(f"Listed {len(file_list)} files for user: {username}")
                return FileListResponse(
                    success=True,
                    message="Files retrieved successfully",
                    files=file_list,
                    total_count=len(files),
                    limit=limit,
                    offset=offset
                )
            else:
                raise HTTPException(status_code=400, detail=message)
        else:
            raise HTTPException(status_code=500, detail="Service not initialized")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/storage/quota", response_model=QuotaResponse, status_code=200)
async def get_quota(authorization: Optional[str] = Header(None)):
    """
    Get user's storage quota information.
    
    Args:
        authorization: Bearer token
    
    Returns:
        200: Quota information
        401: Invalid auth token
    """
    try:
        # Validate auth
        is_valid, username, error_msg = await validate_auth_token(authorization)
        if not is_valid:
            raise HTTPException(status_code=401, detail=error_msg)
        
        logger.info(f"Quota request from user: {username}")
        
        # Call gRPC quota
        if unified_service:
            success, message, quota_data = unified_service.storage_manager.get_user_quota(
                authorization.replace("Bearer ", "")
            )
            
            if success:
                total_bytes = quota_data.get('total_bytes', 1024*1024*1024*1024)
                used_bytes = quota_data.get('used_bytes', 0)
                
                logger.info(f"Quota retrieved for user: {username}")
                return QuotaResponse(
                    success=True,
                    message="Quota information retrieved",
                    total_quota_bytes=total_bytes,
                    total_quota_gb=total_bytes / (1024**3),
                    used_bytes=used_bytes,
                    used_gb=used_bytes / (1024**3),
                    available_bytes=total_bytes - used_bytes,
                    available_gb=(total_bytes - used_bytes) / (1024**3),
                    usage_percentage=(used_bytes / total_bytes * 100) if total_bytes > 0 else 0,
                    file_count=quota_data.get('file_count', 0)
                )
            else:
                raise HTTPException(status_code=400, detail=message)
        else:
            raise HTTPException(status_code=500, detail="Service not initialized")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quota error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@app.get("/health", status_code=200)
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        200: Service is healthy
    """
    return {
        "success": True,
        "message": "Cloud Storage API is healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@app.get("/api/version", status_code=200)
async def get_version():
    """
    Get API version.
    
    Returns:
        200: Version information
    """
    return {
        "success": True,
        "version": "1.0.0",
        "api_name": "Cloud Storage REST API",
        "grpc_backend": f"{GRPC_HOST}:{GRPC_PORT}"
    }


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting FastAPI server on {API_HOST}:{API_PORT}")
    logger.info(f"gRPC backend: {GRPC_HOST}:{GRPC_PORT}")
    logger.info(f"CORS origin: {REACT_ORIGIN}")
    logger.info("OpenAPI docs at http://localhost:8000/docs")
    
    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        log_level="info"
    )
