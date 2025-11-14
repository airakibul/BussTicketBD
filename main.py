# from fastapi import FastAPI, HTTPException, Depends, status
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from pydantic import BaseModel, EmailStr
# from motor.motor_asyncio import AsyncIOMotorClient
# from passlib.context import CryptContext
# from datetime import datetime, timedelta
# from typing import Optional
# import os
# from jose import JWTError, jwt
# from jose.exceptions import ExpiredSignatureError

# # Configuration
# SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
# ALGORITHM = "HS256"
# ACCESS_TOKEN_EXPIRE_MINUTES = 30
# MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
# DATABASE_NAME = "BussTicketBD"

# app = FastAPI(title="Authentication API")
# security = HTTPBearer()
# #pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")

# # MongoDB connection
# client = AsyncIOMotorClient(MONGODB_URL)
# db = client[DATABASE_NAME]
# users_collection = db["users"]

# # Pydantic models
# class UserRegister(BaseModel):
#     email: EmailStr
#     username: str
#     password: str
#     full_name: Optional[str] = None

# class UserLogin(BaseModel):
#     username: str
#     password: str

# class Token(BaseModel):
#     access_token: str
#     token_type: str

# class UserResponse(BaseModel):
#     id: str
#     email: str
#     username: str
#     full_name: Optional[str] = None

# # Helper functions
# def hash_password(password: str) -> str:
#     return pwd_context.hash(password)


# def verify_password(plain_password: str, hashed_password: str) -> bool:
#     return pwd_context.verify(plain_password, hashed_password)


# def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
#     to_encode = data.copy()
#     expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=15))
#     to_encode.update({"exp": expire})
#     encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
#     return encoded_jwt

# async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
#     token = credentials.credentials
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         username: str = payload.get("sub")
#         if username is None:
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="Invalid authentication credentials"
#             )
#     except ExpiredSignatureError:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Token has expired"
#         )
#     except JWTError:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Could not validate credentials"
#         )
    
#     user = await users_collection.find_one({"username": username})
#     if user is None:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="User not found"
#         )
#     return user

# # API Endpoints
# @app.on_event("startup")
# async def startup_db():
#     await users_collection.create_index("username", unique=True)
#     await users_collection.create_index("email", unique=True)

# @app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
# async def register(user: UserRegister):
#     # optional: enforce max password length (not required with bcrypt_sha256)
#     # if len(user.password.encode("utf-8")) > MAX_PASSWORD_BYTES:
#     #     raise HTTPException(
#     #         status_code=400,
#     #         detail=f"Password too long. Maximum {MAX_PASSWORD_BYTES} bytes allowed."
#     #     )

#     existing_user = await users_collection.find_one({
#         "$or": [{"username": user.username}, {"email": user.email}]
#     })
#     if existing_user:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Username or email already registered"
#         )

#     user_dict = {
#         "email": user.email,
#         "username": user.username,
#         "hashed_password": hash_password(user.password),
#         "full_name": user.full_name,
#         "created_at": datetime.utcnow()
#     }
    
#     result = await users_collection.insert_one(user_dict)
    
#     return UserResponse(
#         id=str(result.inserted_id),
#         email=user.email,
#         username=user.username,
#         full_name=user.full_name
#     )

# @app.post("/login", response_model=Token)
# async def login(user_credentials: UserLogin):
#     user = await users_collection.find_one({"username": user_credentials.username})
    
#     if not user or not verify_password(user_credentials.password, user["hashed_password"]):
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Incorrect username or password",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
    
#     access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
#     access_token = create_access_token(
#         data={"sub": user["username"]},
#         expires_delta=access_token_expires
#     )
    
#     return Token(access_token=access_token, token_type="bearer")

# @app.get("/me", response_model=UserResponse)
# async def get_me(current_user: dict = Depends(get_current_user)):
#     return UserResponse(
#         id=str(current_user["_id"]),
#         email=current_user["email"],
#         username=current_user["username"],
#         full_name=current_user.get("full_name")
#     )

# @app.get("/")
# async def root():
#     return {"message": "Authentication API is running"}

# # Run with: uvicorn main:app --reload


from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, field_validator
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
import os
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = "BussTicketBD"
MAX_PASSWORD_LENGTH = 72  # bcrypt limitation

app = FastAPI(title="Authentication API")
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# MongoDB connection
client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]
users_collection = db["users"]

# Pydantic models
class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    
    @field_validator('password')
    @classmethod
    def validate_password_length(cls, v: str) -> str:
        if len(v.encode('utf-8')) > MAX_PASSWORD_LENGTH:
            raise ValueError(f'Password too long. Maximum {MAX_PASSWORD_LENGTH} bytes allowed.')
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long.')
        return v

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: Optional[str] = None

# Helper functions
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    
    user = await users_collection.find_one({"username": username})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user

# API Endpoints
@app.on_event("startup")
async def startup_db():
    await users_collection.create_index("username", unique=True)
    await users_collection.create_index("email", unique=True)

@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserRegister):
    existing_user = await users_collection.find_one({
        "$or": [{"username": user.username}, {"email": user.email}]
    })
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )

    user_dict = {
        "email": user.email,
        "username": user.username,
        "hashed_password": hash_password(user.password),
        "full_name": user.full_name,
        "created_at": datetime.utcnow()
    }
    
    result = await users_collection.insert_one(user_dict)
    
    return UserResponse(
        id=str(result.inserted_id),
        email=user.email,
        username=user.username,
        full_name=user.full_name
    )

@app.post("/login", response_model=Token)
async def login(user_credentials: UserLogin):
    user = await users_collection.find_one({"username": user_credentials.username})
    
    if not user or not verify_password(user_credentials.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]},
        expires_delta=access_token_expires
    )
    
    return Token(access_token=access_token, token_type="bearer")

@app.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user["_id"]),
        email=current_user["email"],
        username=current_user["username"],
        full_name=current_user.get("full_name")
    )

@app.get("/")
async def root():
    return {"message": "Authentication API is running"}