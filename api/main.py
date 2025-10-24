# 文件名: main.py

import os
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Depends
# --- 修正：将 pantic 改为 pydantic ---
from pydantic import BaseModel 
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, Session, declarative_base

# --- 配置 ---
DATABASE_URL = os.environ.get("DATABASE_URL")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

if not DATABASE_URL or not JWT_SECRET_KEY:
    if os.environ.get("RENDER"):
        raise RuntimeError("DATABASE_URL 和 JWT_SECRET_KEY 必须在Render环境中设置!")

engine = create_engine(DATABASE_URL) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()

# --- 数据库模型 ---
class ProductKey(Base):
    __tablename__ = "product_keys"
    id = Column(Integer, primary_key=True, index=True)
    key_string = Column(String, unique=True, index=True, nullable=False)
    max_activations = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)

class Activation(Base):
    __tablename__ = "activations"
    id = Column(Integer, primary_key=True, index=True)
    product_key_id = Column(Integer, ForeignKey("product_keys.id"))
    machine_id = Column(String, unique=True, index=True, nullable=False)
    activation_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# --- API 数据模型 ---
class ActivationRequest(BaseModel):
    product_key: str
    machine_id: str

# --- FastAPI 应用 ---
app = FastAPI()

@app.on_event("startup")
def startup_event():
    if engine:
        Base.metadata.create_all(bind=engine)

def get_db():
    if not SessionLocal:
        raise HTTPException(status_code=500, detail="数据库未配置")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API 核心接口 ---
@app.post("/activate")
def activate_license(request: ActivationRequest, db: Session = Depends(get_db)):
    product_key = db.query(ProductKey).filter(ProductKey.key_string == request.product_key).first()

    if not product_key or not product_key.is_active:
        raise HTTPException(status_code=404, detail="产品密钥无效或已被禁用")

    existing_activation_machine = db.query(Activation).filter(Activation.machine_id == request.machine_id).first()
    if existing_activation_machine:
        pass

    activation_count = db.query(Activation).filter(Activation.product_key_id == product_key.id).count()
    if activation_count >= product_key.max_activations and not existing_activation_machine:
        raise HTTPException(status_code=403, detail="此产品密钥的激活次数已达上限")

    if not existing_activation_machine:
        new_activation = Activation(product_key_id=product_key.id, machine_id=request.machine_id)
        db.add(new_activation)
        db.commit()

    license_payload = {
        "machine_id": request.machine_id,
        "product_key": request.product_key,
        "exp": datetime.now(timezone.utc) + timedelta(days=365 * 10)
    }
    license_jwt = jwt.encode(license_payload, JWT_SECRET_KEY, algorithm="HS256")

    return {"status": "success", "license_key": license_jwt}

@app.get("/")
def read_root():
    return {"message": "授权服务器正在运行"}
